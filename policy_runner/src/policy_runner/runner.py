from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
from tactile_rec import features
from tactile_rec.hub import Hub
from tactile_rec.streams.specs import HAND_MODES

from policy_runner.align_obs import ObsAligner
from policy_runner.chunk import check_reply
from policy_runner.commands.dry_run import DryRunCommand
from policy_runner.commands.hand_udp import HandUdpCommand
from policy_runner.config import RunnerConfig
from policy_runner.executor import Executor
from policy_runner.inference import (
    ACTION_DIM,
    Disconnected,
    InferenceWorker,
    InferTimeout,
    PolicyClient,
    ServerError,
)
from policy_runner.trace import Trace

MS = 1_000_000


class StartError(RuntimeError):
    pass


def synthetic_request(cfg: RunnerConfig, hub: Hub) -> dict:
    images = {}
    for name in cfg.cameras:
        meta = hub.streams[name].spec.meta
        shape = features.oriented_shape(int(meta["height"]), int(meta["width"]),
                                        int(meta["rotation_deg"]))
        images[name] = np.zeros(shape, dtype=np.uint8)
    return {"state": np.zeros(ACTION_DIM, dtype=np.float32), "images": images,
            "prompt": cfg.prompt}


def finite_max(values: np.ndarray) -> float | None:
    values = values[np.isfinite(values)]
    return float(values.max()) if values.size else None


class Runner:
    def __init__(self, cfg: RunnerConfig, hub: Hub | None = None):
        self.cfg = cfg
        self.hub = hub or Hub(cfg.rig)
        self.clock = self.hub.clock
        self.trace_path = cfg.trace_dir / f"{time.strftime('%Y-%m-%d_%H%M%S')}.jsonl"
        self.trace = Trace(self.trace_path)
        self.aligner = ObsAligner(self.hub, cfg.cameras, cfg.max_age_ms, cfg.max_skew_ms)
        self.client = PolicyClient(cfg.endpoint, cfg.connect_timeout_s, cfg.manifest)
        self.worker = InferenceWorker(self.client, self.aligner, cfg.prompt, self.clock,
                                      cfg.infer_timeout_s, cfg.manifest.pred_horizon, cfg.dt_ns,
                                      cfg.max_failures, int(cfg.obs_fail_after_ms * MS),
                                      self.trace)
        self.dry_run = DryRunCommand()
        self.commands: list[Any] = [self.dry_run]
        if cfg.mode == "hand":
            self.commands.append(HandUdpCommand(*cfg.hand_udp, cfg.rig.dataset.arm_dof))
        self.executor = Executor(cfg.dt_ns, cfg.exec_horizon, self.worker, self.commands,
                                 self.trace)
        self._stopping = threading.Event()
        self._ticker = threading.Thread(target=self._tick_forever, name="policy-ticks",
                                        daemon=True)
        self.started = False
        self.warmup_ms: float | None = None

    def start(self) -> None:
        try:
            self.client.connect()
        except (Disconnected, ServerError) as error:
            raise StartError(str(error)) from error
        self.warmup_ms = self.warm_up()
        self.hub.start()
        self.worker.start()
        self._ticker.start()
        self.started = True

    def warm_up(self) -> float:
        start = time.monotonic()
        try:
            reply = self.client.infer(synthetic_request(self.cfg, self.hub),
                                      self.cfg.warmup_timeout_s)
        except (InferTimeout, Disconnected, ServerError) as error:
            raise StartError(f"warm-up request failed: {error}") from error
        problems = check_reply(reply, self.cfg.manifest.pred_horizon, ACTION_DIM)
        if problems:
            raise StartError(f"warm-up reply: {problems[0]}")
        return (time.monotonic() - start) * 1000

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

    def hand_status(self, now_ns: int) -> dict[str, Any]:
        sample = self.hub.streams[self.cfg.rig.dataset.hand].latest()
        if sample is None:
            return {"mode": None, "age_ms": None, "limited_deg": None, "lag_deg": None}
        data = sample.data
        code = int(data["mode"])
        return {
            "mode": HAND_MODES[code] if 0 <= code < len(HAND_MODES) else "unknown",
            "age_ms": (now_ns - sample.t_recv_ns) / MS,
            "limited_deg": finite_max(np.abs(data["cmd"] - data["sent"])),
            "lag_deg": finite_max(np.abs(data["sent"] - data["pos"])),
        }

    def status(self) -> dict[str, Any]:
        now_ns = self.clock.now_ns()
        executor = self.executor.status(now_ns)
        health = self.hub.health()
        infer = self.worker.status()
        obs_age_ms = infer["obs_age_ms"]
        problems = infer.pop("problems")
        if executor["problem"] and executor["problem"] not in problems:
            problems.append(executor["problem"])
        return {
            "state": executor["state"],
            "mode": self.cfg.mode,
            "endpoint": self.cfg.endpoint,
            "checkpoint": self.cfg.manifest.checkpoint,
            "server_checkpoint": (self.client.metadata.get("manifest") or {}).get("checkpoint"),
            "prompt": self.cfg.prompt,
            "warmup_ms": self.warmup_ms,
            "streams": {
                name: {**health[name].to_json(), "obs_age_ms": obs_age_ms.get(name),
                       "max_age_ms": self.cfg.max_age_ms[name]}
                for name in self.cfg.required_streams
            },
            "infer": infer,
            "chunk": executor["chunk"],
            "ticks": executor["ticks"],
            "hand": self.hand_status(now_ns),
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
            self.executor.tick(now_ns, next_ns)
            next_ns += dt_ns * ((now_ns - next_ns) // dt_ns + 1)
