"""Pure-Python OMY trigger to HX5-D20 grasp control.

The 20-joint order and thumb opposition direction follow ROBOTIS's
robotis_hand_teleop/hx5_d20_teleop.py. The zero open pose follows the official
bringup. Its keyboard grip uses full joint limits; this continuous trigger
mapping uses a smaller, collision-free endpoint from the official MuJoCo
model. The separate reference_open_pose() describes the tactile example's
posture and is not used by the trigger mapping.

Tactile thresholds apply to baseline-corrected 0..255 sensor counts summed
over nine taxels per finger. They are not forces in newtons.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

FINGER_NAMES = ("thumb", "index", "middle", "ring", "little")
FINGER_COUNT = len(FINGER_NAMES)
TAXELS_PER_FINGER = 9
JOINT_COUNT = 20


def joint_names(side: str) -> tuple[str, ...]:
    """Official trajectory order: thumb first, then index through little."""
    if side not in ("left", "right"):
        raise ValueError("hand_side must be 'left' or 'right'")
    suffix = "l" if side == "left" else "r"
    return tuple(f"finger_{suffix}_joint{index}" for index in range(1, 21))


def reference_open_pose(side: str) -> tuple[float, ...]:
    """Model-safe variant of ROBOTIS tactile controller's open posture."""
    joint_names(side)  # Validate the side.
    thumb = (-0.15, 1.5, 0.0, 0.0) if side == "left" else (0.297, -1.5, 0.0, 0.0)
    return thumb + (0.0, 0.8, 0.0, 0.0) * 4


def _default_open(side: str) -> tuple[float, ...]:
    joint_names(side)
    return (0.0,) * JOINT_COUNT


def _default_span(side: str) -> tuple[float, ...]:
    thumb_direction = -1.0 if side == "left" else 1.0
    # The keyboard teleop puts the left thumb shift joints at -1.57/+1.57
    # before gripping. Interpolate those joints toward an opposing posture
    # rather than leaving them at zero. Full keyboard limits self-contact in
    # the unloaded MuJoCo scene, so use a smaller collision-free endpoint.
    return (
        0.864 * thumb_direction, -0.864 * thumb_direction,
        1.2 * thumb_direction, 1.2 * thumb_direction,
    ) + (0.0, 1.3, 0.78, 0.52) * 4


def _joint_limits(side: str) -> tuple[tuple[float, float], ...]:
    # HX5-D20 rev2 URDF limits. Non-thumb limits are identical on both hands.
    if side == "left":
        thumb = ((-1.57, 1.57), (0.0, 1.57), (-1.57, 0.0), (-1.57, 0.0))
    else:
        thumb = ((-1.57, 1.57), (-1.57, 0.0), (0.0, 1.57), (0.0, 1.57))
    other = ((-0.6, 0.6), (0.0, 2.0), (0.0, 1.57), (0.0, 1.57))
    return thumb + other * 4


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


@dataclass(frozen=True)
class TactileFrame:
    """One already ordered 5 x 9 pressure sample with a monotonic arrival time."""

    timestamp: float
    values: Sequence[Sequence[float]]

    def __post_init__(self) -> None:
        if not _finite(self.timestamp):
            raise ValueError("tactile timestamp must be finite")
        if len(self.values) != FINGER_COUNT:
            raise ValueError("tactile frame needs five fingers")
        rows: list[tuple[float, ...]] = []
        for row in self.values:
            if len(row) != TAXELS_PER_FINGER:
                raise ValueError("each finger needs nine taxels")
            if any(not _finite(value) or not 0.0 <= value <= 255.0 for value in row):
                raise ValueError("taxel values must be finite 0..255 counts")
            rows.append(tuple(float(value) for value in row))
        object.__setattr__(self, "values", tuple(rows))


@dataclass(frozen=True)
class Hx5CoreConfig:
    hand_side: str = "left"
    open_positions: tuple[float, ...] | None = None
    closing_spans: tuple[float, ...] | None = None
    baseline_frames: int = 30
    baseline_grasp_max: float = 0.05
    baseline_open_tolerance_rad: float = 0.1
    tactile_timeout_s: float = 0.25
    contact_threshold: float = 10.0
    thumb_contact_ratio: float = 2.0
    pressure_hard_cap: float = 30.0
    reactive_ratio: float = 1.1
    pressure_deadband: float = 2.0
    pressure_ema_alpha: float = 0.2
    contact_loss_fraction: float = 0.25
    saturation_taxel: float = 255.0
    pressure_gain_per_count_s: float = 0.01
    max_close_adjust_per_s: float = 0.1
    max_open_adjust_per_s: float = 0.2
    max_joint_speed_rad_s: float = 0.5
    max_control_dt_s: float = 0.1

    def __post_init__(self) -> None:
        limits = _joint_limits(self.hand_side) if self.hand_side in ("left", "right") else None
        if limits is None:
            raise ValueError("hand_side must be 'left' or 'right'")
        opened = tuple(_default_open(self.hand_side) if self.open_positions is None else self.open_positions)
        spans = tuple(_default_span(self.hand_side) if self.closing_spans is None else self.closing_spans)
        if len(opened) != JOINT_COUNT or len(spans) != JOINT_COUNT:
            raise ValueError("open_positions and closing_spans must each have 20 values")
        expected = _default_span(self.hand_side)
        for index, (open_pos, span, (low, high), direction) in enumerate(
            zip(opened, spans, limits, expected)
        ):
            if not _finite(open_pos) or not _finite(span):
                raise ValueError(f"joint {index + 1} pose values must be finite")
            if direction == 0.0 and span != 0.0 or direction != 0.0 and span * direction < 0.0:
                raise ValueError(f"joint {index + 1} closing span has the wrong direction")
            if not low <= open_pos <= high or not low <= open_pos + span <= high:
                raise ValueError(f"joint {index + 1} pose exceeds HX5-D20 model limits")
        object.__setattr__(self, "open_positions", opened)
        object.__setattr__(self, "closing_spans", spans)
        if not isinstance(self.baseline_frames, int) or isinstance(self.baseline_frames, bool) or self.baseline_frames < 1:
            raise ValueError("baseline_frames must be a positive integer")
        positive = (
            "baseline_open_tolerance_rad", "tactile_timeout_s", "contact_threshold",
            "thumb_contact_ratio", "pressure_hard_cap", "reactive_ratio",
            "saturation_taxel", "pressure_gain_per_count_s", "max_close_adjust_per_s",
            "max_open_adjust_per_s", "max_joint_speed_rad_s", "max_control_dt_s",
        )
        if any(not _finite(getattr(self, key)) or getattr(self, key) <= 0.0 for key in positive):
            raise ValueError("control rates and positive thresholds must be finite and positive")
        if not 0.0 <= self.baseline_grasp_max < 1.0:
            raise ValueError("baseline_grasp_max must be in [0, 1)")
        if not _finite(self.pressure_deadband) or self.pressure_deadband < 0.0:
            raise ValueError("pressure_deadband must be nonnegative")
        if not _finite(self.pressure_ema_alpha) or not 0.0 < self.pressure_ema_alpha <= 1.0:
            raise ValueError("pressure_ema_alpha must be in (0, 1]")
        if not _finite(self.contact_loss_fraction) or not 0.0 <= self.contact_loss_fraction < 1.0:
            raise ValueError("contact_loss_fraction must be in [0, 1)")
        if self.pressure_hard_cap <= self.contact_threshold * self.thumb_contact_ratio:
            raise ValueError("pressure_hard_cap must exceed every contact threshold")
        if self.reactive_ratio < 1.0 or self.saturation_taxel > 255.0:
            raise ValueError("reactive_ratio or saturation_taxel is outside its range")


class Hx5GraspCore:
    """One position command per step; no ROS or device I/O.

    Call initialize() with all 20 measured joints before stepping or publishing.
    Collect the tactile baseline with an unloaded, open hand and released trigger.
    Contact caps each finger independently. The slow pressure regulator may add
    closure only up to the leader's current request; release always wins.
    """

    def __init__(self, config: Hx5CoreConfig | None = None) -> None:
        self.config = config or Hx5CoreConfig()
        self.joint_names = joint_names(self.config.hand_side)
        self._limits = _joint_limits(self.config.hand_side)
        self._command: tuple[float, ...] | None = None
        self._last_step_time: float | None = None
        self._last_frame_time: float | None = None
        self._baseline_sum = [[0.0] * TAXELS_PER_FINGER for _ in range(FINGER_COUNT)]
        self._baseline: tuple[tuple[float, ...], ...] | None = None
        self._baseline_samples = 0
        self._ema = [[0.0] * TAXELS_PER_FINGER for _ in range(FINGER_COUNT)]
        self._pressure_sums = [0.0] * FINGER_COUNT
        self._saturated = [False] * FINGER_COUNT
        self._contacted = [False] * FINGER_COUNT
        self._faulted = [False] * FINGER_COUNT
        self._pressure_targets = [0.0] * FINGER_COUNT
        self._caps = [1.0] * FINGER_COUNT

    @property
    def baseline_ready(self) -> bool:
        return self._baseline is not None

    @property
    def baseline_samples(self) -> int:
        return self._baseline_samples

    @property
    def pressure_sums(self) -> tuple[float, ...]:
        return tuple(self._pressure_sums)

    @property
    def contacted(self) -> tuple[bool, ...]:
        return tuple(self._contacted)

    @property
    def faulted(self) -> tuple[bool, ...]:
        return tuple(self._faulted)

    @property
    def command(self) -> tuple[float, ...]:
        if self._command is None:
            raise RuntimeError("initialize with measured joint positions before commanding")
        return self._command

    def initialize(self, current_positions: Sequence[float], now: float) -> None:
        """Seed the command from measured joint states, without moving the hand."""
        if self._command is not None:
            raise RuntimeError("core is already initialized")
        if not _finite(now):
            raise ValueError("initial time must be finite")
        if len(current_positions) != JOINT_COUNT:
            raise ValueError("initialize needs all 20 joint positions")
        positions = tuple(float(value) for value in current_positions)
        bounded = []
        for index, (position, (low, high)) in enumerate(zip(positions, self._limits)):
            # Gazebo's unconstrained solver reports numerical noise near zero
            # (about 1e-10 rad on joints whose upper limit is exactly zero).
            # Accept only this tiny boundary error; reject actual out-of-range
            # postures and seed commands strictly inside the model limits.
            if not _finite(position) or not low - 1e-6 <= position <= high + 1e-6:
                raise ValueError(f"joint {index + 1} measured position is invalid or outside model limits")
            bounded.append(max(low, min(high, position)))
        self._command = tuple(bounded)
        self._last_step_time = float(now)

    def _near_open(self) -> bool:
        assert self._command is not None
        cfg = self.config
        return all(
            abs(position - opened) <= cfg.baseline_open_tolerance_rad
            for position, opened, span in zip(self._command, cfg.open_positions, cfg.closing_spans)
            if span != 0.0
        )

    def _update_tactile(self, frame: TactileFrame, grasp: float | None) -> None:
        cfg = self.config
        for finger in range(FINGER_COUNT):
            self._saturated[finger] = any(
                value >= cfg.saturation_taxel for value in frame.values[finger]
            )
            if self._saturated[finger]:
                self._faulted[finger] = True
        if self._baseline is None:
            if (
                grasp is None or grasp > cfg.baseline_grasp_max or not self._near_open()
                or any(self._saturated)
            ):
                return
            for finger in range(FINGER_COUNT):
                for taxel in range(TAXELS_PER_FINGER):
                    self._baseline_sum[finger][taxel] += frame.values[finger][taxel]
            self._baseline_samples += 1
            if self._baseline_samples == cfg.baseline_frames:
                self._baseline = tuple(
                    tuple(value / self._baseline_samples for value in row)
                    for row in self._baseline_sum
                )
            return

        alpha = cfg.pressure_ema_alpha
        for finger in range(FINGER_COUNT):
            for taxel in range(TAXELS_PER_FINGER):
                adjusted = max(0.0, frame.values[finger][taxel] - self._baseline[finger][taxel])
                previous = self._ema[finger][taxel]
                self._ema[finger][taxel] = (1.0 - alpha) * previous + alpha * adjusted
            summed = sum(self._ema[finger])
            self._pressure_sums[finger] = (1.0 - alpha) * self._pressure_sums[finger] + alpha * summed
            if self._contacted[finger] and self._pressure_sums[finger] < (
                cfg.contact_threshold * (cfg.thumb_contact_ratio if finger == 0 else 1.0)
                * cfg.contact_loss_fraction
            ):
                self._faulted[finger] = True

    def _progress(self, finger: int) -> float:
        assert self._command is not None
        start = finger * 4
        positions = self._command[start:start + 4]
        opened = self.config.open_positions[start:start + 4]
        spans = self.config.closing_spans[start:start + 4]
        denominator = sum(value * value for value in spans)
        if denominator == 0.0:
            return 0.0
        projected = sum((position - base) * span for position, base, span in zip(positions, opened, spans)) / denominator
        return min(1.0, max(0.0, projected))

    def step(
        self,
        grasp: float | None,
        tactile: TactileFrame | None,
        now: float,
        *,
        motion_enabled: bool = True,
    ) -> tuple[float, ...]:
        """Return a bounded 20-joint command (radians, official joint order).

        Invalid/missing leader or tactile input never permits further closure.
        Repeated tactile timestamps do not accumulate baseline or EMA twice.
        """
        if self._command is None or self._last_step_time is None:
            raise RuntimeError("initialize with measured joint positions before stepping")
        if not _finite(now) or now < self._last_step_time:
            raise ValueError("step time must be finite and monotonic")
        if tactile is not None and not isinstance(tactile, TactileFrame):
            raise TypeError("tactile must be a validated TactileFrame or None")
        if not isinstance(motion_enabled, bool):
            raise TypeError("motion_enabled must be a bool")
        cfg = self.config
        leader_ok = _finite(grasp) and 0.0 <= grasp <= 1.0
        leader_value = float(grasp) if leader_ok else None
        dt = min(now - self._last_step_time, cfg.max_control_dt_s)
        self._last_step_time = float(now)

        bad_frame = False
        new_frame = False
        if tactile is not None:
            if tactile.timestamp > now or now - tactile.timestamp > cfg.tactile_timeout_s or (
                self._last_frame_time is not None and tactile.timestamp < self._last_frame_time
            ):
                bad_frame = True
            elif self._last_frame_time is None or tactile.timestamp > self._last_frame_time:
                self._last_frame_time = tactile.timestamp
                new_frame = True
                self._update_tactile(tactile, leader_value)
        tactile_ok = (
            not bad_frame and self.baseline_ready and self._last_frame_time is not None
            and 0.0 <= now - self._last_frame_time <= cfg.tactile_timeout_s
        )

        if leader_value is not None and leader_value <= cfg.baseline_grasp_max:
            self._contacted = [False] * FINGER_COUNT
            self._pressure_targets = [0.0] * FINGER_COUNT
            self._caps = [1.0] * FINGER_COUNT
            if tactile_ok and new_frame:
                for finger in range(FINGER_COUNT):
                    threshold = cfg.contact_threshold * (
                        cfg.thumb_contact_ratio if finger == 0 else 1.0
                    )
                    if not self._saturated[finger] and self._pressure_sums[finger] < threshold * 0.5:
                        self._faulted[finger] = False

        # Before the ROS bridge is active, pressure may be calibrated but no
        # position target has been published. Preserve the measured seed so
        # baseline collection cannot build up a hidden motion command.
        if not motion_enabled:
            return self._command

        next_command = list(self._command)
        for finger in range(FINGER_COUNT):
            current_progress = self._progress(finger)
            pressure = self._pressure_sums[finger]
            threshold = cfg.contact_threshold * (cfg.thumb_contact_ratio if finger == 0 else 1.0)
            if tactile_ok and new_frame and leader_value is not None and leader_value > cfg.baseline_grasp_max:
                if not self._contacted[finger] and not self._faulted[finger] and pressure >= threshold:
                    self._contacted[finger] = True
                    self._caps[finger] = min(current_progress, leader_value)
                    self._pressure_targets[finger] = min(cfg.pressure_hard_cap, max(threshold, pressure * cfg.reactive_ratio))

            if self._contacted[finger]:
                if leader_value is not None:
                    self._caps[finger] = min(self._caps[finger], leader_value)
                if tactile_ok and leader_value is not None and not self._faulted[finger]:
                    error = self._pressure_targets[finger] - pressure
                    if pressure >= cfg.pressure_hard_cap:
                        self._caps[finger] = max(0.0, current_progress - cfg.max_open_adjust_per_s * dt)
                    elif error < -cfg.pressure_deadband:
                        change = min(-error * cfg.pressure_gain_per_count_s, cfg.max_open_adjust_per_s) * dt
                        self._caps[finger] = max(0.0, self._caps[finger] - change)
                    elif error > cfg.pressure_deadband:
                        change = min(error * cfg.pressure_gain_per_count_s, cfg.max_close_adjust_per_s) * dt
                        self._caps[finger] = min(leader_value, self._caps[finger] + change)

            target_progress = current_progress if leader_value is None else leader_value
            if self._contacted[finger]:
                target_progress = min(target_progress, self._caps[finger])
            may_close = tactile_ok and leader_value is not None and not self._faulted[finger]
            if not may_close:
                target_progress = min(target_progress, current_progress)

            desired = list(self._command[finger * 4:finger * 4 + 4])
            for local_joint in range(4):
                index = finger * 4 + local_joint
                span = cfg.closing_spans[index]
                if span == 0.0:
                    continue  # Side joints are not driven by one trigger.
                current = self._command[index]
                target = cfg.open_positions[index] + target_progress * span
                if not may_close and (target - current) * span > 0.0:
                    target = current
                low, high = self._limits[index]
                desired[local_joint] = max(low, min(high, target))

            # Scale one finger's four joint deltas together. Independent speed
            # clipping distorts the thumb opposition path during release and
            # causes transient self-contact in the official MuJoCo model.
            largest_delta = max(
                abs(target - current)
                for target, current in zip(desired, self._command[finger * 4:finger * 4 + 4])
            )
            max_step = cfg.max_joint_speed_rad_s * dt
            scale = min(1.0, max_step / largest_delta) if largest_delta else 1.0
            for local_joint, target in enumerate(desired):
                index = finger * 4 + local_joint
                current = self._command[index]
                next_command[index] = current + scale * (target - current)

        self._command = tuple(next_command)
        return self._command
