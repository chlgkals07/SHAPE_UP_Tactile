"""Named register addresses used by the GEN3 boards.

Values are taken from the official user manuals and the example scripts that
ship with the sensors. Where the protocol disagrees between the
single-channel Serial Converter Board (which uses 32-bit fin_master
addresses) and the High-Speed Communication Board (which uses 16-bit
register addresses), both forms are exposed.
"""

# ---- High-Speed Communication Board registers ------------------------------

# Read-only metadata
REG_VERSION = 0x0000               # 15 bytes ASCII firmware version
REG_VERSION_LEN = 0x000F

# Sensor status — each byte covers a pair of modules
REG_STATUS_THUMB_INDEX = 0x0010
REG_STATUS_MIDDLE_RING = 0x0011
REG_STATUS_LITTLE_PALM_1_4 = 0x0012
REG_STATUS_PALM_5_8 = 0x0013

REG_DATA_TYPE = 0x0016             # combined data-type configuration
REG_AUTO_PUSH = 0x0017             # 1 = enable auto-push, 0 = disable
REG_TOTAL_ERROR = 0x0023           # error code reported in auto-push frames
REG_SYSTEM_RESET = 0x0022          # write 0x01 to reboot the high-speed board

# Calibration trigger (per official UI default frame "55AA00170200010001E6")
REG_CALIBRATION = 0x0017           # alt usage on some firmwares

# Module resultant-force window: 28 modules x 6 bytes = 168 bytes starting at
# 0x0500. Each module contributes Fx/Fy/Fz as little-endian int16.
REG_MODULE_FORCES_BASE = 0x0500
MODULE_COUNT = 28
MODULE_FORCE_BYTES = 6
MODULE_FORCES_TOTAL_BYTES = MODULE_COUNT * MODULE_FORCE_BYTES  # 168

# Distributed-force point counts live at 0x0030–0x0067, two bytes per module.
REG_DISTRIBUTION_POINTS_BASE = 0x0030

# Per-module distributed-force address ranges (start_addr, end_addr). Each
# region holds the raw distributed-force samples for one module — usable
# bytes per region is `point_count * 3`.
DISTRIBUTION_ADDR_RANGES = {
    "Thumb-Proximal":  (0x1000, 0x11FF),
    "Thumb-Middle":    (0x1200, 0x13FF),
    "Thumb-Tip":       (0x1400, 0x15FF),
    "Thumb-Nail":      (0x1600, 0x17FF),
    "Index-Proximal":  (0x1800, 0x19FF),
    "Index-Middle":    (0x1A00, 0x1BFF),
    "Index-Tip":       (0x1C00, 0x1DFF),
    "Index-Nail":      (0x1E00, 0x1FFF),
    "Middle-Proximal": (0x2000, 0x21FF),
    "Middle-Middle":   (0x2200, 0x23FF),
    "Middle-Tip":      (0x2400, 0x25FF),
    "Middle-Nail":     (0x2600, 0x27FF),
    "Ring-Proximal":   (0x2800, 0x29FF),
    "Ring-Middle":     (0x2A00, 0x2BFF),
    "Ring-Tip":        (0x2C00, 0x2DFF),
    "Ring-Nail":       (0x2E00, 0x2FFF),
    "Little-Proximal": (0x3000, 0x31FF),
    "Little-Middle":   (0x3200, 0x33FF),
    "Little-Tip":      (0x3400, 0x35FF),
    "Little-Nail":     (0x3600, 0x37FF),
    "Palm-1":          (0x3800, 0x38FF),
    "Palm-2":          (0x3900, 0x39FF),
    "Palm-3":          (0x3A00, 0x3AFF),
    "Palm-4":          (0x3B00, 0x3BFF),
    "Palm-5":          (0x3C00, 0x3CFF),
    "Palm-6":          (0x3D00, 0x3DFF),
    "Palm-7":          (0x3E00, 0x3EFF),
    "Palm-8":          (0x3F00, 0x3FFF),
}

MODULE_NAMES = [
    "Thumb-Proximal", "Thumb-Middle", "Thumb-Tip", "Thumb-Nail",
    "Index-Proximal", "Index-Middle", "Index-Tip", "Index-Nail",
    "Middle-Proximal", "Middle-Middle", "Middle-Tip", "Middle-Nail",
    "Ring-Proximal",   "Ring-Middle",  "Ring-Tip",  "Ring-Nail",
    "Little-Proximal", "Little-Middle", "Little-Tip", "Little-Nail",
    "Palm-1", "Palm-2", "Palm-3", "Palm-4",
    "Palm-5", "Palm-6", "Palm-7", "Palm-8",
]


# ---- Single-channel Serial Converter Board (fin_master) ---------------------
#
# These are the addresses used by the official "Read_Single_Sensor_Usb.py"
# and "USB_UI.py" examples. Function codes are 0x7B (read force regions) and
# 0x79 (calibration) in their write-form; the read-form OR'd with 0x80 yields
# 0xFB.

FIN_ADDR_RESULTANT_FORCE = 0x000003F0   # 3 bytes (Fx, Fy, Fz)
FIN_ADDR_DISTRIBUTED_FORCE = 0x0000040E  # distributed-force grid; N = points*3
FIN_ADDR_CALIBRATION = 0x00000003        # write 1-byte value 0x01 to trigger
#
# NOTE on FIN_ADDR_DISTRIBUTED_FORCE: the vendor's two reference programs both
# address the distributed-force region at 0x040E, encoded little-endian as the
# request bytes "0E 04 00 00":
#   - Read_Single_Sensor_Usb.py  -> "55 AA 09 00 01 00 FB 0E 04 00 00 E7 00 03"
#   - USB_UI.py line 179         -> "...FB 0E 04 00 00 {len_lo} {len_hi}"
# The Serial Converter Board exposes no point-count register, so the number of
# distributed-force points must be supplied by the host (USB_UI.py makes the
# operator pick the sensor model and type the byte length by hand).


# ---- Active-modules bitmap layout (protocol PDF §4.6) ----------------------
#
# Registers 0x0010-0x0013 (4 bytes total) describe which of the 28 module slots
# are reporting data. The bit-to-module mapping is dense and contiguous:
#
#   byte 0 (0x0010): bit B in 0..3 = MODULE_NAMES[B]    (Thumb-{Proximal,Middle,Tip,Nail})
#                    bit B in 4..7 = MODULE_NAMES[B]    (Index-{Proximal,Middle,Tip,Nail})
#   byte 1 (0x0011): bit B in 0..3 = MODULE_NAMES[8+B]  (Middle-{Proximal,Middle,Tip,Nail})
#                    bit B in 4..7 = MODULE_NAMES[8+B]  (Ring-{Proximal,Middle,Tip,Nail})
#   byte 2 (0x0012): bit B in 0..3 = MODULE_NAMES[16+B] (Little-{Proximal,Middle,Tip,Nail})
#                    bit B in 4..7 = MODULE_NAMES[16+B] (Palm-{1..4})
#   byte 3 (0x0013): bit B in 0..3 = MODULE_NAMES[24+B] (Palm-{5..8})
#                    bit B in 4..7: unused (28 slots total)
#
# i.e. module_index = byte_index * 8 + bit_index.

def parse_active_modules_bitmap(bitmap_bytes: bytes) -> list:
    """Return a sorted list of active module indices from 0x0010-0x0013."""
    if len(bitmap_bytes) < 4:
        raise ValueError(f"bitmap must be at least 4 bytes, got {len(bitmap_bytes)}")
    active = []
    for byte_idx in range(4):
        b = bitmap_bytes[byte_idx]
        for bit in range(8):
            module_idx = byte_idx * 8 + bit
            if module_idx >= MODULE_COUNT:
                continue
            if b & (1 << bit):
                active.append(module_idx)
    return active


# ---- Data-type combination bits (register 0x0016) --------------------------
#
# bit 0: resultant force included in auto-push payload
# bit 1: distributed force grid included in auto-push payload
# default after power-on: 0x03 (both)
DATA_TYPE_RESULTANT = 0x01
DATA_TYPE_DISTRIBUTED = 0x02
