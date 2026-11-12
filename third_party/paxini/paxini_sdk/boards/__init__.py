"""High-level board classes."""

from .serial_converter import SingleSensorBoard
from .high_speed import HighSpeedHandBoard, AutoPushFrame

__all__ = ["SingleSensorBoard", "HighSpeedHandBoard", "AutoPushFrame"]
