"""paxini_sdk — cross-platform Python SDK for Paxini PX-6AX GEN3 multidimensional
tactile sensors.

This package wraps the GEN3 communication protocol used by the official
Paxini USB communication boards (Serial Converter Board and High-Speed
Communication Board) so that the sensors can be driven on macOS / Linux / Windows
without the vendor's Windows-only host application.

Quick start:

    from paxini_sdk import list_serial_ports, SingleSensorBoard

    print(list_serial_ports())
    with SingleSensorBoard("/dev/tty.usbserial-XXXX") as board:
        board.calibrate()
        fx, fy, fz = board.read_resultant_force()
        print(fx, fy, fz)

For the high-speed (robotic hand) board:

    from paxini_sdk import HighSpeedHandBoard

    with HighSpeedHandBoard("/dev/tty.usbserial-XXXX") as hand:
        print(hand.read_version())
        for frame in hand.stream_auto_push(duration=5.0):
            print(frame.module_forces)
"""

from .exceptions import (
    PaxiniError,
    FrameError,
    LRCError,
    DeviceError,
    TimeoutError as PaxiniTimeoutError,
)
from .protocol import lrc, build_fin_request, build_simple_request, parse_simple_response
from .transport import SerialTransport, list_serial_ports
from .boards.serial_converter import SingleSensorBoard
from .boards.high_speed import HighSpeedHandBoard, AutoPushFrame

__version__ = "0.1.0"

__all__ = [
    "PaxiniError",
    "FrameError",
    "LRCError",
    "DeviceError",
    "PaxiniTimeoutError",
    "lrc",
    "build_fin_request",
    "build_simple_request",
    "parse_simple_response",
    "SerialTransport",
    "list_serial_ports",
    "SingleSensorBoard",
    "HighSpeedHandBoard",
    "AutoPushFrame",
    "__version__",
]
