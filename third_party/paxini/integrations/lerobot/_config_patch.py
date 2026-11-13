"""Drop-in addition for lerobot/sensors/configs.py.

Append the contents below to that file (after the MLX90393SensorConfig block).
Do NOT replace the file — just add these lines.
"""

# --- begin paste ---
@SensorConfig.register_subclass("paxini")
@dataclass
class PaxiniSensorConfig(SensorConfig):
    """Paxini PX-6AX GEN3 tactile sensor via paxini-sdk."""

    # Serial port the High-Speed Communication Board appears as.
    # Windows: "COM7". macOS: "/dev/cu.usbserial-XXXX". Linux: "/dev/ttyUSB0".
    port: str = "/dev/cu.usbserial-0001"

    # Default 921600 — board's fixed UART rate.
    baud_rate: int = 921_600

    # Number of recent frames kept in the ring buffer (the N in (N, ...)).
    buffer_size: int = 10

    # Which module to read from. None = first active slot reported by the
    # board (works when only one sensor is plugged in).
    module_index: int | None = None

    # Output tensor shape:
    #   "resultant"   -> (N, 3)         resultant Fx Fy Fz per frame
    #   "distributed" -> (N, P, 3)      per-taxel Fx Fy Fz grid
    #   "both"        -> (N, 3 + P*3)   flat concat: resultant + distributed
    output_format: str = "resultant"

    # If True, send the vendor's firmware calibration frame on connect.
    auto_calibrate: bool = True

    # Optional host-side baseline subtraction. 0 disables. If > 0, average
    # that many frames after connect, subtract from all subsequent samples.
    # Useful for trimming the residual ~1 LSB offset left after firmware
    # calibration when you need sub-LSB precision.
    software_baseline_frames: int = 0
# --- end paste ---
