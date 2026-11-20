from __future__ import annotations

import threading
import time
from typing import Any

from tactile_rec.hub import Hub

from policy_runner.align_obs import ObsAligner
from policy_runner.commands.dry_run import DryRunCommand
from policy_runner.commands.hand_udp import HandUdpCommand
from policy_runner.config import RunnerConfig
from policy_runner.executor import Executor
from policy_runner.inference import Disconnected, InferenceWorker, PolicyClient
from policy_runner.trace import Trace


class StartError(RuntimeError):
    pass


class Runner:
    def __init__(self, cfg: RunnerConfig, hub: Hub | None = None):
        self.cfg = cfg
        self.hub = hub or Hub(cfg.rig)
        self.clock = self.hub.clock
        self.trace_path = cfg.trace_dir / f"{time.strftime('%Y-%m-%d_%H%M%S')}.jsonl"
        self.trace = Trace(self.trace_path)
        self.aligner = ObsAligner(self.hub, cfg.cameras, cfg.max_age_ms, cfg.max_skew_ms)
        self.client = PolicyClient(cfg.endpoint, cfg.connect_timeout_s)
        self.worker = InferenceWorker(self.client, self.aligner, cfg.prompt, self.clock,
                                      cfg.infer_timeout_s, cfg.manifest.pred_horizon, cfg.dt_ns,
                                      self.trace)
        self.dry_run = DryRunCommand()
        self.commands: list[Any] = [self.dry_run]
        if cfg.mode == "hand":
            self.commands.append(HandUdpCommand(*cfg.hand_udp, cfg.rig.dataset.arm_dof))
        self.executor = Executor(cfg.dt_ns, cfg.exec_horizon, cfg.limits, self.worker,
                                 lambda: self.aligner.measured(self.clock.now_ns()),
                                 self.commands, self.trace)
        self._stopping = threading.Event()
        self._ticker = threading.Thread(target=self._tick_forever, name="policy-ticks",
                                        daemon=True)
        self.started = False
        self.server_manifest: dict[str, Any] = {}

    def start(self) -> None:
        try:
            metadata = self.client.connect()
        except Disconnected as error:
            raise StartError(str(error)) from error
        self.server_manifest = metadata.get("manifest") or {}
        if not self.server_manifest:
            raise StartError("server metadata has no manifest")
        differences = self.cfg.manifest.differences(self.server_manifest)
        if differences:
            raise StartError("manifest differs from the server: " + "; ".join(differences))
        self.hub.start()
        self.worker.start()
        self._ticker.start()
        self.started = True

    def stop(self) -> None:
        self._stopping.set()
        if self.started:
            self._ticker.join(timeout=2)
            self.executor.disarm(self.clock.now_ns())
            self.worker.stop()
            self.started = False
        self.client.close()
        self.hub.stop()
        for command in self.commands:
            command.close()
        self.trace.close()

    def arm(self) -> None:
        self.executor.arm(self.clock.now_ns())

    def disarm(self) -> None:
        self.executor.disarm(self.clock.now_ns())
        self.worker.clear()

    def reset(self) -> None:
        self.worker.clear()
        self.worker.clear_fault()
        self.executor.reset(self.clock.now_ns())

    def status(self) -> dict[str, Any]:
        now_ns = self.clock.now_ns()
        executor = self.executor.status(now_ns)
        health = self.hub.health()
        obs_age_ms = self.worker.last_obs_ages_ms
        problems = list(self.worker.problems)
        if executor["problem"] and executor["problem"] not in problems:
            problems.append(executor["problem"])
        return {
            "state": executor["state"],
            "mode": self.cfg.mode,
            "endpoint": self.cfg.endpoint,
            "checkpoint": self.cfg.manifest.checkpoint,
            "server_checkpoint": self.server_manifest.get("checkpoint"),
            "prompt": self.cfg.prompt,
            "streams": {
                name: {**health[name].to_json(), "obs_age_ms": obs_age_ms.get(name),
                       "max_age_ms": self.cfg.max_age_ms[name]}
                for name in self.cfg.required_streams
            },
            "infer": self.worker.status(),
            "chunk": executor["chunk"],
            "sent": self.dry_run.status(),
            "problems": problems[-10:],
            "trace": str(self.trace_path),
        }

    def _tick_forever(self) -> None:
        dt_ns = self.cfg.dt_ns
        next_ns = self.clock.now_ns()
        while not self._stopping.is_set():
            now_ns = self.clock.now_ns()
            if now_ns < next_ns:
                self._stopping.wait((next_ns - now_ns) / 1e9)
                continue
            self.executor.tick(now_ns)
            next_ns += dt_ns * ((now_ns - next_ns) // dt_ns + 1)
