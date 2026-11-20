from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from tactile_rec.clock import Clock
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI
from websockets.sync.client import ClientConnection, connect

from policy_runner import wire
from policy_runner.align_obs import ObsAligner, to_request
from policy_runner.chunk import ActionChunk, check_reply
from policy_runner.trace import Trace

ACTION_DIM = 22
MS = 1_000_000


class ServerError(RuntimeError):
    pass


class InferTimeout(TimeoutError):
    pass


class Disconnected(ConnectionError):
    pass


class PolicyClient:
    def __init__(self, endpoint: str, connect_timeout_s: float):
        self.endpoint = endpoint
        self.connect_timeout_s = connect_timeout_s
        self.connection: ClientConnection | None = None
        self.metadata: dict[str, Any] = {}

    @property
    def connected(self) -> bool:
        return self.connection is not None

    def connect(self) -> dict[str, Any]:
        self.close()
        try:
            self.connection = connect(self.endpoint, open_timeout=self.connect_timeout_s,
                                      max_size=None, compression=None, legacy=True)
            self.metadata = wire.unpackb(self.connection.recv(timeout=self.connect_timeout_s))
        except (OSError, TimeoutError, InvalidHandshake, InvalidURI, ConnectionClosed) as error:
            self.close()
            raise Disconnected(f"cannot connect to {self.endpoint}: {error}") from error
        return self.metadata

    def infer(self, obs: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        if self.connection is None:
            self.connect()
        assert self.connection is not None
        try:
            self.connection.send(wire.packb(obs))
            raw = self.connection.recv(timeout=timeout_s)
        except TimeoutError as error:
            self.close()
            raise InferTimeout(f"no reply within {timeout_s * 1000:.0f} ms") from error
        except ConnectionClosed as error:
            self.close()
            raise Disconnected(f"server closed the connection: {error}") from error
        if isinstance(raw, str):
            self.close()
            raise ServerError(raw)
        return wire.unpackb(raw)

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None


class InferenceWorker:
    def __init__(self, client: PolicyClient, aligner: ObsAligner, prompt: str, clock: Clock,
                 timeout_s: float, pred_horizon: int, retry_ns: int, trace: Trace):
        self.client = client
        self.aligner = aligner
        self.prompt = prompt
        self.clock = clock
        self.timeout_s = timeout_s
        self.pred_horizon = pred_horizon
        self.retry_ns = retry_ns
        self.trace = trace
        self.fault = ""
        self.problems: deque[str] = deque(maxlen=10)
        self.last_obs_ages_ms: dict[str, float] = {}
        self.last_rtt_ms: float | None = None
        self.last_infer_ms: float | None = None
        self._wanted: int | None = None
        self._ready: ActionChunk | None = None
        self._chunk_ids = 0
        self._wake = threading.Condition()
        self._stopping = False
        self._thread = threading.Thread(target=self._serve, name="policy-inference", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        with self._wake:
            self._stopping = True
            self._wake.notify_all()
        self._thread.join(timeout=self.timeout_s + 2)
        self.client.close()

    def request(self, now_ns: int) -> None:
        with self._wake:
            self._wanted = now_ns
            self._ready = None
            self._wake.notify_all()

    def take(self, now_ns: int) -> ActionChunk | None:
        with self._wake:
            chunk, self._ready = self._ready, None
            return chunk

    def clear(self) -> None:
        with self._wake:
            self._wanted, self._ready = None, None

    def clear_fault(self) -> None:
        with self._wake:
            self.fault = ""

    def status(self) -> dict[str, Any]:
        return {
            "connected": self.client.connected,
            "rtt_ms": self.last_rtt_ms,
            "infer_ms": self.last_infer_ms,
            "waiting": self._wanted is not None,
            "obs_age_ms": dict(self.last_obs_ages_ms),
        }

    def _next_request(self) -> int | None:
        with self._wake:
            while self._wanted is None and not self._stopping:
                self._wake.wait()
            if self._stopping:
                return None
            wanted, self._wanted = self._wanted, None
            return wanted

    def _serve(self) -> None:
        while (t_obs_ns := self._next_request()) is not None:
            chunk = self._attempt(t_obs_ns)
            with self._wake:
                if chunk is not None and self._wanted is None:
                    self._ready = chunk
                elif chunk is None and self._wanted is None and not self.fault:
                    self._wanted = max(self.clock.now_ns(), t_obs_ns + self.retry_ns)
                    self._wake.wait(self.retry_ns / 1e9)

    def _attempt(self, t_obs_ns: int) -> ActionChunk | None:
        t_obs_ns = max(t_obs_ns, self.clock.now_ns())
        obs = self.aligner.align(t_obs_ns)
        self.last_obs_ages_ms = {name: p.age_ns / MS for name, p in obs.picks.items()}
        self.trace.write("obs", self.clock.now_ns(), obs_id=obs.obs_id, t_obs_ns=obs.t_obs_ns,
                         ok=obs.ok, problems=obs.problems,
                         picks={name: {"seq": p.seq, "t_ns": p.t_ns, "age_ns": p.age_ns}
                                for name, p in obs.picks.items()})
        if not obs.ok:
            self._note(obs.problems[0])
            return None
        self.trace.write("request", self.clock.now_ns(), obs_id=obs.obs_id)
        start = time.monotonic()
        try:
            reply = self.client.infer(to_request(obs, self.prompt), self.timeout_s)
        except (InferTimeout, Disconnected) as error:
            return self._failed(obs.obs_id, start, str(error), fault=False)
        except ServerError as error:
            return self._failed(obs.obs_id, start, f"server error: {last_line(str(error))}",
                                fault=True)
        problems = check_reply(reply, self.pred_horizon, ACTION_DIM)
        if problems:
            return self._failed(obs.obs_id, start, f"bad reply: {problems[0]}", fault=True)
        self.last_rtt_ms = (time.monotonic() - start) * 1000
        self.last_infer_ms = reply.get("server_timing", {}).get("infer_ms")
        self.trace.write("reply", self.clock.now_ns(), obs_id=obs.obs_id, ok=True, problems=[],
                         rtt_ms=self.last_rtt_ms, infer_ms=self.last_infer_ms)
        self._chunk_ids += 1
        return ActionChunk(chunk_id=self._chunk_ids, obs_id=obs.obs_id, t_obs_ns=obs.t_obs_ns,
                           t_reply_ns=self.clock.now_ns(), actions=reply["actions"])

    def _failed(self, obs_id: int, start: float, problem: str, fault: bool) -> None:
        self.trace.write("reply", self.clock.now_ns(), obs_id=obs_id, ok=False,
                         problems=[problem], rtt_ms=(time.monotonic() - start) * 1000,
                         infer_ms=None)
        self._note(problem)
        if fault:
            self.fault = problem
        return None

    def _note(self, problem: str) -> None:
        if not self.problems or self.problems[-1] != problem:
            self.problems.append(problem)


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1] if lines else text
