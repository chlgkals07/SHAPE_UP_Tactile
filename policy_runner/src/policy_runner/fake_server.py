from __future__ import annotations

import itertools
import threading
import time
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any

import numpy as np
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import Server, ServerConnection, serve

from policy_runner import wire

PRED_HORIZON = 50
STALL_S = 30.0


@dataclass
class Faults:
    error_every: int = 0
    stall_first_ms: float = 0.0
    stall_every: int = 0
    drop_every: int = 0
    delay_ms: float = 0.0
    nan_every: int = 0
    bad_shape_every: int = 0


def every(n: int, count: int) -> bool:
    return n > 0 and count % n == 0


def hold_actions(state: np.ndarray, faults: Faults, count: int) -> np.ndarray:
    actions = np.tile(np.asarray(state, dtype=np.float32), (PRED_HORIZON, 1))
    if every(faults.nan_every, count):
        actions[PRED_HORIZON // 2, 0] = np.nan
    if every(faults.bad_shape_every, count):
        actions = actions[:, :-1]
    return actions


def healthz(connection: ServerConnection, request: Any):
    if request.path == "/healthz":
        return connection.respond(HTTPStatus.OK, "OK\n")
    return None


@dataclass
class FakeServer:
    metadata: dict[str, Any]
    faults: Faults
    server: Server | None = None
    thread: threading.Thread | None = None
    stopping: threading.Event = field(default_factory=threading.Event)
    _counter: itertools.count = field(default_factory=lambda: itertools.count(1))
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def port(self) -> int:
        assert self.server is not None
        return int(self.server.socket.getsockname()[1])

    def next_count(self) -> int:
        with self._lock:
            return next(self._counter)

    def handle(self, connection: ServerConnection) -> None:
        try:
            connection.send(wire.packb(self.metadata))
            for raw in connection:
                if not self.answer(connection, raw):
                    return
        except ConnectionClosed:
            return

    def answer(self, connection: ServerConnection, raw: Any) -> bool:
        count = self.next_count()
        faults = self.faults
        if count == 1 and faults.stall_first_ms:
            self.stopping.wait(faults.stall_first_ms / 1000)
        if every(faults.stall_every, count):
            self.stopping.wait(STALL_S)
            return False
        if every(faults.drop_every, count):
            connection.close()
            return False
        self.stopping.wait(faults.delay_ms / 1000)
        start = time.monotonic()
        try:
            if every(faults.error_every, count):
                raise RuntimeError(f"injected error on request {count}")
            obs = wire.unpackb(raw)
            reply = {"actions": hold_actions(obs["state"], faults, count)}
        except Exception:
            connection.send(traceback.format_exc())
            connection.close()
            return False
        reply["server_timing"] = {"infer_ms": (time.monotonic() - start) * 1000}
        connection.send(wire.packb(reply))
        return True

    def stop(self) -> None:
        self.stopping.set()
        if self.server is not None:
            self.server.shutdown()
        if self.thread is not None:
            self.thread.join(timeout=5)


def start(host: str = "127.0.0.1", port: int = 8000, metadata: dict[str, Any] | None = None,
          **faults: Any) -> FakeServer:
    fake = FakeServer(metadata=metadata or {}, faults=Faults(**faults))
    fake.server = serve(fake.handle, host, port, process_request=healthz, max_size=None,
                        compression=None)
    fake.thread = threading.Thread(target=fake.server.serve_forever, name="fake-policy-server",
                                   daemon=True)
    fake.thread.start()
    return fake
