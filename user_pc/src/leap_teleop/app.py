"""The control loop: source -> retargeter -> stale guard -> hand driver."""

from __future__ import annotations

import time
from collections.abc import Callable

from leap_teleop.hand.base import HandDriver
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.base import Source
from leap_teleop.types import Retargeter


def run_teleop(
    source: Source,
    retarget: Retargeter,
    guard: StaleGuard,
    driver: HandDriver,
    *,
    rate_hz: float = 50.0,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    log: Callable[[str], None] = print,
) -> None:
    period = 1.0 / rate_hz
    try:
        driver.start()
    except BaseException:
        source.close()
        raise

    last_mode = None
    try:
        while not source.stop_requested:
            tick_start = clock()
            reading = source.poll(tick_start)
            command = retarget(reading) if reading is not None else None
            command_time = reading.timestamp if reading is not None else None
            driver.command(guard.resolve(tick_start, command, command_time))
            if guard.mode != last_mode:
                last_mode = guard.mode
                log(f"[teleop] {guard.mode}")
            sleep(max(0.0, period - (clock() - tick_start)))
    finally:
        try:
            source.close()
        finally:
            driver.close()
