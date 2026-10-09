# OMY Leader → LEAP Hand Teleop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** User PC에서 LEAP Hand v1을 구동하는 `leap_teleop` 패키지를 만든다. 입력은 (1) 키보드 space 토글, (2) OMY leader 그리퍼(`/leader/joint_trajectory`의 `rh_r1_joint`)이며, 입력·변환·출력은 각각 교체 가능해야 한다.

**Architecture:** `Source`(입력) → `Retargeter`(변환, 공통 계약은 16관절 각도 `HandCommand`) → `StaleGuard`(입력 끊김 안전) → `HandDriver`(출력)로 이어지는 50 Hz 루프. LEAP 제어 코드는 기존 `leap-hand` 레포에서 필요한 파일만 이식한다. ROS 2 의존은 `sources/ros2_leader.py` 한 파일에만 둔다. Robot PC용 코드는 별도 레포(`OMY_Tactile_Robot_PC`)이며 이 계획에서는 마지막 조건부 Task 13만 다룬다.

**Tech Stack:** Python 3.12, numpy, PyYAML, dynamixel-sdk, pytest, rclpy (Ubuntu 24.04 + ROS 2 Jazzy, `--system-site-packages` venv)

**Spec:** `docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md`

## Global Constraints

- 코드는 `SHAPE_UP_Tactile/user_pc/`에 둔다. 소스는 `user_pc/src/leap_teleop/`, 테스트는 `user_pc/tests/`.
- 환경: Ubuntu 24.04, ROS 2 Jazzy, `python3 -m venv --system-site-packages .venv`. **numpy 버전을 고정하지 않는다** (시스템 numpy 1.26.4가 `rclpy`와 함께 쓰인다).
- 자동 테스트는 하드웨어·ROS·터미널 없이 통과해야 한다. `rclpy`는 `Ros2LeaderSource.__init__` 안에서만 import한다.
- 이식 파일 첫 줄에 출처를 남긴다: `# Vendored from shinjju1209/leap-hand@ddfabaa (<원본 경로>). Import paths adjusted; logic unchanged.`
- 이식하지 않는 것: MediaPipe, MuJoCo, RL 정책, 부스 앱, 가위바위보, 모델 파일, 개인 보정 데이터.
- 개인 보정 `config/hardware_motors.yaml`은 gitignore, 예시 파일만 추적한다.
- 안전 기본값 유지: 전류 제한 300 mA, 관절 속도 120°/s, 명령 간격 제한 0.1 s, 버스 워치독 500 ms, 예외 시 Torque OFF. 루프 주기는 워치독보다 충분히 짧아야 하므로 기본 50 Hz, 허용 범위 10~200 Hz.
- `HandCommand` = 길이 16 `numpy.ndarray`(float64, 도), `ANGLE_NAMES` 순서, 0 = 편 손.
- fist 초기값(도): 검지/중지/약지 MCP 55 · PIP 60 · DIP 40, 엄지 CMC 35 · MCP 40 · IP 35, side 관절은 0.
- 토픽 `/leader/joint_trajectory`(`trajectory_msgs/JointTrajectory`), 관절 이름 `rh_r1_joint`, `ROS_DOMAIN_ID=30`.
- 모든 커밋 메시지는 `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` 줄로 끝낸다.
- 명령은 별도 표기가 없으면 레포 루트 `/home/hamin/Projects/SHAPE_UP_Tactile`에서 실행한다.

## Review Focus

1. leader 메시지의 `joint_names` 순서가 다르거나 `rh_r1_joint`가 없거나 `points`가 비어 있음 → 값을 만들지 않고(None) 이전 값 유지·stale 처리 (Task 8).
2. leader 그리퍼 값이 측정한 open/closed 범위를 벗어나거나 open·closed가 뒤집힘 → 0~1로 clip, 뒤집힌 매핑도 정상 (Task 8).
3. leader 토픽이 끊김(Robot PC 정지, DDS 문제) → 0.5 s 후 마지막 자세 유지, 3 s 후 open 복귀 (Task 6, 9).
4. 실행 중 예외·Ctrl+C·시작 실패 → Torque OFF와 입력 정리가 항상 수행됨 (Task 9).
5. 모터 보정 파일이 없는데 실물 모드로 실행 → 공칭값(π)으로 조용히 움직이지 않고 거부 (Task 10).

---

### Task 1: 패키지 골격, 관절 이름, `Reading` 타입

**Files:**
- Create: `user_pc/pyproject.toml`
- Create: `user_pc/.gitignore`
- Create: `user_pc/src/leap_teleop/__init__.py`
- Create: `user_pc/src/leap_teleop/hand/__init__.py`
- Create: `user_pc/src/leap_teleop/hand/joints.py`
- Create: `user_pc/src/leap_teleop/types.py`
- Test: `user_pc/tests/test_types.py`

**Interfaces:**
- Produces: `leap_teleop.hand.joints.ANGLE_NAMES: tuple[str, ...]` (길이 16), `leap_teleop.types.HAND_DOF: int` (=16), `leap_teleop.types.Reading(timestamp: float, grasp: float | None = None, hand: np.ndarray | None = None)` (정확히 하나만 값을 가짐, 검증 실패 시 `ValueError`), `leap_teleop.types.Retargeter = Callable[[Reading], np.ndarray]`

- [ ] **Step 1: 골격 파일 작성**

`user_pc/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "leap-teleop"
version = "0.1.0"
description = "LEAP Hand v1 teleoperation from keyboard or OMY leader gripper"
requires-python = ">=3.10"
dependencies = ["numpy", "PyYAML"]

[project.optional-dependencies]
hardware = ["dynamixel-sdk"]
dev = ["pytest"]

[project.scripts]
leap-teleop = "leap_teleop.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`user_pc/.gitignore`:
```
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
*.egg-info/
config/hardware_motors.yaml
```

`user_pc/src/leap_teleop/__init__.py` 와 `user_pc/src/leap_teleop/hand/__init__.py`: 빈 파일.

`user_pc/src/leap_teleop/hand/joints.py`:
```python
"""LEAP Hand v1 joint order shared by every module (0 degrees = open hand)."""

ANGLE_NAMES = (
    "index_mcp_side",
    "index_mcp_flex",
    "index_pip_flex",
    "index_dip_flex",
    "middle_mcp_side",
    "middle_mcp_flex",
    "middle_pip_flex",
    "middle_dip_flex",
    "ring_mcp_side",
    "ring_mcp_flex",
    "ring_pip_flex",
    "ring_dip_flex",
    "thumb_cmc_side",
    "thumb_cmc_flex",
    "thumb_mcp_flex",
    "thumb_ip_flex",
)
```

- [ ] **Step 2: venv 생성과 설치**

```bash
cd user_pc
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"   # 네트워크가 없으면: pip install --no-build-isolation -e ".[dev]"
python -c "import numpy, yaml, dynamixel_sdk; print('ok')"
```
Expected: `ok` (실패하면 `pip install dynamixel-sdk` 후 재확인)

- [ ] **Step 3: 실패하는 테스트 작성**

`user_pc/tests/test_types.py`:
```python
import numpy as np
import pytest

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HAND_DOF, Reading


def test_hand_dof_matches_joint_names():
    assert HAND_DOF == 16
    assert len(ANGLE_NAMES) == HAND_DOF


def test_reading_accepts_grasp():
    reading = Reading(timestamp=1.0, grasp=0.5)
    assert reading.grasp == 0.5
    assert reading.hand is None


def test_reading_accepts_hand_and_copies_it():
    source = np.zeros(16)
    reading = Reading(timestamp=1.0, hand=source)
    source[0] = 99.0
    assert reading.hand[0] == 0.0
    assert reading.grasp is None


def test_reading_requires_exactly_one_of_grasp_or_hand():
    with pytest.raises(ValueError):
        Reading(timestamp=1.0)
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, grasp=0.5, hand=np.zeros(16))


@pytest.mark.parametrize("grasp", [-0.01, 1.01, float("nan")])
def test_reading_rejects_grasp_outside_unit_interval(grasp):
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, grasp=grasp)


def test_reading_rejects_wrong_hand_shape_and_nan():
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, hand=np.zeros(15))
    bad = np.zeros(16)
    bad[3] = float("nan")
    with pytest.raises(ValueError):
        Reading(timestamp=1.0, hand=bad)
```

- [ ] **Step 4: 실패 확인**

Run: `cd user_pc && source .venv/bin/activate && python -m pytest tests/test_types.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.types'`

- [ ] **Step 5: 구현**

`user_pc/src/leap_teleop/types.py`:
```python
"""Shared data contract between sources, retargeters and hand drivers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from leap_teleop.hand.joints import ANGLE_NAMES

HAND_DOF = len(ANGLE_NAMES)


@dataclass(frozen=True)
class Reading:
    """One input sample: either a scalar grasp (0 open .. 1 closed) or a full hand."""

    timestamp: float
    grasp: float | None = None
    hand: np.ndarray | None = None

    def __post_init__(self) -> None:
        if (self.grasp is None) == (self.hand is None):
            raise ValueError("Reading needs exactly one of grasp or hand")
        if self.grasp is not None and not 0.0 <= self.grasp <= 1.0:
            raise ValueError(f"grasp must be in [0, 1], got {self.grasp}")
        if self.hand is not None:
            hand = np.array(self.hand, dtype=np.float64)
            if hand.shape != (HAND_DOF,):
                raise ValueError(f"hand must have shape ({HAND_DOF},), got {hand.shape}")
            if not np.all(np.isfinite(hand)):
                raise ValueError("hand contains NaN or infinity")
            object.__setattr__(self, "hand", hand)


Retargeter = Callable[[Reading], np.ndarray]
```

- [ ] **Step 6: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_types.py -q`
Expected: PASS (8 passed)

- [ ] **Step 7: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): scaffold leap_teleop package with Reading type

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: LEAP 컨트롤러와 보정 코드 이식

**Files:**
- Create: `user_pc/src/leap_teleop/hand/calibration.py` (이식)
- Create: `user_pc/src/leap_teleop/hand/leap_v1.py` (이식)
- Create: `user_pc/tests/test_hardware_calibration.py` (이식)
- Create: `user_pc/tests/test_leap_v1_controller.py` (이식)
- Create: `user_pc/config/hardware_motors.example.yaml`

**Interfaces:**
- Consumes: `leap_teleop.hand.joints.ANGLE_NAMES` (Task 1)
- Produces: `leap_teleop.hand.calibration.HardwareMotorCalibration` (`nominal()`, `load(path)`, `save(path)`, `sim_to_motor_radians`, `motor_to_sim_radians`), `leap_teleop.hand.leap_v1.LeapHandHardwareController(port, *, baudrate=4_000_000, motor_ids=None, current_limit_milliamps=300, ..., motor_calibration=None, sdk_module=None, clock=None)` — 메서드 `connect() -> dict`, `configure()`, `enable_torque()`, `command_degrees(angles) -> np.ndarray`, `heartbeat()`, `read_feedback()`, `read_health()`, `emergency_stop() -> tuple[int, ...]`, `close() -> tuple[int, ...]`

- [ ] **Step 1: 원본 레포를 고정 commit으로 가져오기**

```bash
rm -rf /tmp/leap-hand-src
git clone --depth 1 https://github.com/shinjju1209/leap-hand.git /tmp/leap-hand-src
git -C /tmp/leap-hand-src rev-parse --short HEAD
```
Expected: `ddfabaa` (다르면 멈추고 사용자에게 알린다. 이식 대상이 바뀌었을 수 있다.)

- [ ] **Step 2: 복사, import 수정, 출처 헤더 추가**

```bash
OLD=/tmp/leap-hand-src
D=user_pc/src/leap_teleop/hand
T=user_pc/tests
cp $OLD/hardware_calibration.py $D/calibration.py
cp $OLD/leap_hand_hardware_controller.py $D/leap_v1.py
cp $OLD/tests/test_hardware_calibration.py $T/test_hardware_calibration.py
cp $OLD/tests/test_leap_hand_hardware_controller.py $T/test_leap_v1_controller.py

sed -i 's/^from hand_angles import ANGLE_NAMES$/from leap_teleop.hand.joints import ANGLE_NAMES/' $D/calibration.py $D/leap_v1.py $T/*.py
sed -i 's/^from hardware_calibration import /from leap_teleop.hand.calibration import /' $D/leap_v1.py $T/test_hardware_calibration.py $T/test_leap_v1_controller.py
sed -i 's/^from leap_hand_hardware_controller import/from leap_teleop.hand.leap_v1 import/' $T/test_leap_v1_controller.py

sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (hardware_calibration.py). Import paths adjusted; logic unchanged.' $D/calibration.py
sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (leap_hand_hardware_controller.py). Import paths adjusted; logic unchanged.' $D/leap_v1.py
sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (tests/test_hardware_calibration.py). Import paths adjusted.' $T/test_hardware_calibration.py
sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (tests/test_leap_hand_hardware_controller.py). Import paths adjusted.' $T/test_leap_v1_controller.py

grep -nE "^(from|import) (hand_angles|hardware_calibration|leap_hand)" $D/*.py $T/*.py || echo "no stale imports"
```
Expected: `no stale imports`

- [ ] **Step 3: 이식된 테스트 실행**

Run: `cd user_pc && source .venv/bin/activate && python -m pytest tests/test_hardware_calibration.py tests/test_leap_v1_controller.py -q`
Expected: PASS (원본에서 통과하던 전체 테스트). 원본 테스트가 레포 상대 경로의 파일을 읽어 실패하면 그 경로만 `tmp_path`를 쓰도록 고친다. 로직 수정은 하지 않는다.

- [ ] **Step 4: 예시 보정 파일 생성**

```bash
mkdir -p user_pc/config
cd user_pc && source .venv/bin/activate
python - <<'EOF'
from leap_teleop.hand.calibration import HardwareMotorCalibration
HardwareMotorCalibration.nominal().save("config/hardware_motors.example.yaml")
EOF
head -12 config/hardware_motors.example.yaml
```
Expected: `version: 1` 로 시작하고 `open_motor_radians: 3.14159...`, `sign: 1`이 보인다. 예시 파일에서 개인 장비 값이 섞이지 않은 공칭값임을 확인한다.

- [ ] **Step 5: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): vendor LEAP v1 controller and motor calibration

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `HandDriver` 프로토콜, `LeapHandDriver`, `LogDriver`

**Files:**
- Create: `user_pc/src/leap_teleop/hand/base.py`
- Create: `user_pc/src/leap_teleop/hand/leap_driver.py`
- Create: `user_pc/src/leap_teleop/hand/dry_run.py`
- Test: `user_pc/tests/test_drivers.py`

**Interfaces:**
- Consumes: `LeapHandHardwareController` 메서드 (Task 2)
- Produces: `HandDriver` Protocol (`start() -> None`, `command(angles_degrees: np.ndarray) -> None`, `close() -> None`), `LeapHandDriver(controller)`, `LogDriver(every: int = 25, out: Callable[[str], None] = print)`

- [ ] **Step 1: 실패하는 테스트 작성**

`user_pc/tests/test_drivers.py`:
```python
import numpy as np
import pytest

from leap_teleop.hand.dry_run import LogDriver
from leap_teleop.hand.leap_driver import LeapHandDriver


class FakeController:
    def __init__(self, fail_on=None, failed_ids=()):
        self.calls = []
        self.fail_on = fail_on
        self.failed_ids = failed_ids

    def connect(self):
        self._step("connect")

    def configure(self):
        self._step("configure")

    def enable_torque(self):
        self._step("enable_torque")

    def command_degrees(self, angles):
        self.calls.append(("command", np.asarray(angles).copy()))

    def close(self):
        self.calls.append(("close",))
        return self.failed_ids

    def _step(self, name):
        self.calls.append((name,))
        if self.fail_on == name:
            raise OSError(name)


def test_start_connects_configures_then_enables_torque_in_order():
    controller = FakeController()
    LeapHandDriver(controller).start()
    assert [call[0] for call in controller.calls] == ["connect", "configure", "enable_torque"]


def test_start_failure_closes_controller_and_reraises():
    controller = FakeController(fail_on="configure")
    with pytest.raises(OSError):
        LeapHandDriver(controller).start()
    assert controller.calls[-1] == ("close",)


def test_command_forwards_angles():
    controller = FakeController()
    angles = np.arange(16, dtype=float)
    LeapHandDriver(controller).command(angles)
    name, forwarded = controller.calls[-1]
    assert name == "command"
    np.testing.assert_array_equal(forwarded, angles)


def test_close_reports_motors_that_did_not_acknowledge_torque_off():
    driver = LeapHandDriver(FakeController(failed_ids=(3, 7)))
    with pytest.raises(RuntimeError, match=r"\(3, 7\)"):
        driver.close()


def test_close_is_quiet_when_all_motors_acknowledge():
    LeapHandDriver(FakeController()).close()


def test_log_driver_logs_first_and_every_nth_command():
    lines = []
    driver = LogDriver(every=3, out=lines.append)
    driver.start()
    for _ in range(7):
        driver.command(np.zeros(16))
    driver.close()
    command_lines = [line for line in lines if "cmd" in line]
    assert len(command_lines) == 3  # commands 1, 4 and 7
    assert any("start" in line for line in lines)
    assert any("close" in line for line in lines)
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_drivers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.hand.dry_run'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/hand/base.py`:
```python
"""Output boundary: anything that can move a hand from a 16-angle command."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class HandDriver(Protocol):
    def start(self) -> None:
        """Connect and energize. Must not move the hand away from its current pose."""

    def command(self, angles_degrees: np.ndarray) -> None:
        """Apply a HandCommand (16 degrees, ANGLE_NAMES order, 0 = open)."""

    def close(self) -> None:
        """De-energize and release the device. Safe to call after a failed start."""
```

`user_pc/src/leap_teleop/hand/leap_driver.py`:
```python
"""HandDriver adapter for the vendored LEAP Hand v1 controller."""

from __future__ import annotations

import numpy as np

from leap_teleop.hand.leap_v1 import LeapHandHardwareController


class LeapHandDriver:
    def __init__(self, controller: LeapHandHardwareController) -> None:
        self._controller = controller

    def start(self) -> None:
        try:
            self._controller.connect()
            self._controller.configure()
            self._controller.enable_torque()
        except BaseException:
            self._controller.close()
            raise

    def command(self, angles_degrees: np.ndarray) -> None:
        self._controller.command_degrees(angles_degrees)

    def close(self) -> None:
        failed_ids = self._controller.close()
        if failed_ids:
            raise RuntimeError(
                f"Torque-off was not acknowledged by motor IDs {tuple(failed_ids)}; "
                "cut the 5V supply."
            )
```

`user_pc/src/leap_teleop/hand/dry_run.py`:
```python
"""HandDriver that only logs, for checking the pipeline without hardware."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np


class LogDriver:
    def __init__(self, every: int = 25, out: Callable[[str], None] = print) -> None:
        if every < 1:
            raise ValueError("every must be at least 1")
        self._every = every
        self._out = out
        self._count = 0

    def start(self) -> None:
        self._out("[dry-run] start (no hardware)")

    def command(self, angles_degrees: np.ndarray) -> None:
        if self._count % self._every == 0:
            self._out(f"[dry-run] cmd max={float(np.max(angles_degrees)):.1f} deg")
        self._count += 1

    def close(self) -> None:
        self._out("[dry-run] close")
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_drivers.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add HandDriver protocol, LEAP adapter and dry-run driver

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 설정 로더와 기본 설정 파일

**Files:**
- Create: `user_pc/src/leap_teleop/config.py`
- Create: `user_pc/config/postures.yaml`
- Create: `user_pc/config/leader_gripper.yaml`
- Test: `user_pc/tests/test_config.py`

**Interfaces:**
- Consumes: `ANGLE_NAMES`, `HAND_DOF`
- Produces: `make_posture(changes: Mapping[str, float]) -> np.ndarray`, `load_postures(path) -> tuple[np.ndarray, np.ndarray]` (open, fist), `LeaderGripperConfig(topic: str, joint_name: str, open_value: float, closed_value: float)`, `load_leader_gripper(path) -> LeaderGripperConfig`

- [ ] **Step 1: 설정 파일 작성**

`user_pc/config/postures.yaml`:
```yaml
# 단위: 도. 0 = 편 손. 이름은 leap_teleop.hand.joints.ANGLE_NAMES 와 같아야 한다.
# fist 는 leap-hand@ddfabaa 의 손가락 테스트(leap_hand_hardware_finger_test.py)에서 쓰던
# 보수적인 굽힘 목표다. 실물에서 충분히 닫히지 않으면 조금씩 늘린다.
open: {}
fist:
  index_mcp_flex: 55.0
  index_pip_flex: 60.0
  index_dip_flex: 40.0
  middle_mcp_flex: 55.0
  middle_pip_flex: 60.0
  middle_dip_flex: 40.0
  ring_mcp_flex: 55.0
  ring_pip_flex: 60.0
  ring_dip_flex: 40.0
  thumb_cmc_flex: 35.0
  thumb_mcp_flex: 40.0
  thumb_ip_flex: 35.0
```

`user_pc/config/leader_gripper.yaml`:
```yaml
# Robot PC 의 leader 가 publish 하는 토픽과 그리퍼 관절.
# open_value / closed_value 는 leader 그리퍼를 폈을 때와 쥐었을 때
# `ros2 topic echo /leader/joint_trajectory` 로 읽은 rh_r1_joint 값이다.
# 이 토픽 값에는 reverse_joints 와 offset(0.2)이 이미 적용돼 있다.
# 아래 두 값은 실측 전 임시값이므로 첫 실물 시험에서 반드시 측정해 바꾼다.
topic: /leader/joint_trajectory
joint_name: rh_r1_joint
open_value: 0.0
closed_value: 1.0
```

- [ ] **Step 2: 실패하는 테스트 작성**

`user_pc/tests/test_config.py`:
```python
from pathlib import Path

import numpy as np
import pytest

from leap_teleop.config import (
    LeaderGripperConfig,
    load_leader_gripper,
    load_postures,
    make_posture,
)
from leap_teleop.hand.joints import ANGLE_NAMES

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def test_make_posture_places_values_by_joint_name():
    posture = make_posture({"index_mcp_flex": 55.0})
    assert posture.shape == (16,)
    assert posture[ANGLE_NAMES.index("index_mcp_flex")] == 55.0
    assert np.count_nonzero(posture) == 1


def test_make_posture_rejects_unknown_joint():
    with pytest.raises(ValueError, match="bogus"):
        make_posture({"bogus": 1.0})


def test_load_postures_reads_open_and_fist(tmp_path):
    path = tmp_path / "postures.yaml"
    path.write_text("open: {}\nfist:\n  index_mcp_flex: 10\n")
    open_pose, fist_pose = load_postures(path)
    assert not open_pose.any()
    assert fist_pose[ANGLE_NAMES.index("index_mcp_flex")] == 10.0


def test_load_postures_requires_both_keys(tmp_path):
    path = tmp_path / "postures.yaml"
    path.write_text("open: {}\n")
    with pytest.raises(ValueError, match="fist"):
        load_postures(path)


def test_default_postures_are_the_conservative_finger_test_values():
    open_pose, fist_pose = load_postures(CONFIG_DIR / "postures.yaml")
    assert not open_pose.any()
    expected = {
        "index_mcp_flex": 55.0, "index_pip_flex": 60.0, "index_dip_flex": 40.0,
        "middle_mcp_flex": 55.0, "middle_pip_flex": 60.0, "middle_dip_flex": 40.0,
        "ring_mcp_flex": 55.0, "ring_pip_flex": 60.0, "ring_dip_flex": 40.0,
        "thumb_cmc_flex": 35.0, "thumb_mcp_flex": 40.0, "thumb_ip_flex": 35.0,
    }
    np.testing.assert_array_equal(fist_pose, make_posture(expected))
    for side in ("index_mcp_side", "middle_mcp_side", "ring_mcp_side", "thumb_cmc_side"):
        assert fist_pose[ANGLE_NAMES.index(side)] == 0.0


def test_load_leader_gripper(tmp_path):
    path = tmp_path / "leader.yaml"
    path.write_text(
        "topic: /t\njoint_name: rh_r1_joint\nopen_value: 0.2\nclosed_value: 1.1\n"
    )
    assert load_leader_gripper(path) == LeaderGripperConfig("/t", "rh_r1_joint", 0.2, 1.1)


def test_leader_gripper_rejects_equal_open_and_closed(tmp_path):
    path = tmp_path / "leader.yaml"
    path.write_text("topic: /t\njoint_name: j\nopen_value: 1.0\nclosed_value: 1.0\n")
    with pytest.raises(ValueError, match="differ"):
        load_leader_gripper(path)


def test_default_leader_gripper_file_loads():
    cfg = load_leader_gripper(CONFIG_DIR / "leader_gripper.yaml")
    assert cfg.topic == "/leader/joint_trajectory"
    assert cfg.joint_name == "rh_r1_joint"
```

- [ ] **Step 3: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.config'`

- [ ] **Step 4: 구현**

`user_pc/src/leap_teleop/config.py`:
```python
"""Loaders for the tracked YAML configuration files."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from leap_teleop.hand.joints import ANGLE_NAMES
from leap_teleop.types import HAND_DOF


def make_posture(changes: Mapping[str, float]) -> np.ndarray:
    """Build a HandCommand (degrees, ANGLE_NAMES order) from named joint values."""
    unknown = sorted(set(changes) - set(ANGLE_NAMES))
    if unknown:
        raise ValueError(f"Unknown LEAP Hand joint names: {unknown}")
    posture = np.zeros(HAND_DOF, dtype=np.float64)
    for name, value in changes.items():
        posture[ANGLE_NAMES.index(name)] = float(value)
    return posture


def _load_mapping(path: str | Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_postures(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (open_pose, fist_pose) as HandCommands."""
    data = _load_mapping(path)
    poses = []
    for key in ("open", "fist"):
        if key not in data:
            raise ValueError(f"{path} is missing the '{key}' posture")
        poses.append(make_posture(data[key] or {}))
    return poses[0], poses[1]


@dataclass(frozen=True)
class LeaderGripperConfig:
    topic: str
    joint_name: str
    open_value: float
    closed_value: float


def load_leader_gripper(path: str | Path) -> LeaderGripperConfig:
    data = _load_mapping(path)
    try:
        cfg = LeaderGripperConfig(
            topic=str(data["topic"]),
            joint_name=str(data["joint_name"]),
            open_value=float(data["open_value"]),
            closed_value=float(data["closed_value"]),
        )
    except KeyError as missing:
        raise ValueError(f"{path} is missing {missing}") from None
    if cfg.open_value == cfg.closed_value:
        raise ValueError("open_value and closed_value must differ")
    return cfg
```

- [ ] **Step 5: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_config.py -q`
Expected: PASS (9 passed)

- [ ] **Step 6: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add posture and leader gripper config loaders

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `ScalarPostureRetargeter`

**Files:**
- Create: `user_pc/src/leap_teleop/retarget/__init__.py` (빈 파일)
- Create: `user_pc/src/leap_teleop/retarget/scalar_posture.py`
- Test: `user_pc/tests/test_scalar_posture.py`

**Interfaces:**
- Consumes: `Reading` (Task 1), `make_posture` (Task 4)
- Produces: `ScalarPostureRetargeter(open_pose: np.ndarray, fist_pose: np.ndarray)`, 호출 `retargeter(reading: Reading) -> np.ndarray` (새 배열, `Retargeter` 계약 충족)

- [ ] **Step 1: 실패하는 테스트 작성**

`user_pc/tests/test_scalar_posture.py`:
```python
import numpy as np
import pytest

from leap_teleop.config import make_posture
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.types import Reading


def make_retargeter():
    open_pose = np.zeros(16)
    fist_pose = make_posture({"index_mcp_flex": 60.0, "thumb_ip_flex": 30.0})
    return ScalarPostureRetargeter(open_pose, fist_pose), open_pose, fist_pose


def test_grasp_zero_is_open_and_one_is_fist():
    retargeter, open_pose, fist_pose = make_retargeter()
    np.testing.assert_array_equal(retargeter(Reading(0.0, grasp=0.0)), open_pose)
    np.testing.assert_array_equal(retargeter(Reading(0.0, grasp=1.0)), fist_pose)


def test_grasp_half_is_halfway():
    retargeter, _, fist_pose = make_retargeter()
    np.testing.assert_allclose(retargeter(Reading(0.0, grasp=0.5)), fist_pose / 2.0)


def test_returned_array_is_a_copy():
    retargeter, open_pose, _ = make_retargeter()
    out = retargeter(Reading(0.0, grasp=0.0))
    out[0] = 99.0
    np.testing.assert_array_equal(retargeter(Reading(0.0, grasp=0.0)), open_pose)


def test_hand_reading_is_rejected():
    retargeter, _, _ = make_retargeter()
    with pytest.raises(ValueError, match="grasp"):
        retargeter(Reading(0.0, hand=np.zeros(16)))


def test_constructor_rejects_wrong_shapes():
    with pytest.raises(ValueError):
        ScalarPostureRetargeter(np.zeros(15), np.zeros(16))
    with pytest.raises(ValueError):
        ScalarPostureRetargeter(np.zeros(16), np.zeros(17))
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_scalar_posture.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.retarget'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/retarget/scalar_posture.py`:
```python
"""Map a scalar grasp (0 open .. 1 fist) onto a HandCommand by linear interpolation."""

from __future__ import annotations

import numpy as np

from leap_teleop.types import HAND_DOF, Reading


class ScalarPostureRetargeter:
    def __init__(self, open_pose: np.ndarray, fist_pose: np.ndarray) -> None:
        self._open = np.array(open_pose, dtype=np.float64)
        self._fist = np.array(fist_pose, dtype=np.float64)
        for name, pose in (("open_pose", self._open), ("fist_pose", self._fist)):
            if pose.shape != (HAND_DOF,):
                raise ValueError(f"{name} must have shape ({HAND_DOF},), got {pose.shape}")

    def __call__(self, reading: Reading) -> np.ndarray:
        if reading.grasp is None:
            raise ValueError("ScalarPostureRetargeter needs a grasp reading")
        return self._open + reading.grasp * (self._fist - self._open)
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_scalar_posture.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add scalar-to-posture retargeter

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `StaleGuard` (입력 끊김 안전)

**Files:**
- Create: `user_pc/src/leap_teleop/safety.py`
- Test: `user_pc/tests/test_safety.py`

**Interfaces:**
- Produces: `StaleGuard(open_command: np.ndarray, stale_timeout: float = 0.5, release_timeout: float = 3.0)`, 메서드 `resolve(now: float, command: np.ndarray | None, command_time: float | None) -> np.ndarray`, 속성 `mode: str` (`"waiting"`, `"live"`, `"hold"`, `"release"`). 규칙: `command`가 없으면 open(`waiting`); 나이 ≤ `stale_timeout`이면 command(`live`); ≤ `release_timeout`이면 마지막 출력 유지(`hold`); 그 이상이면 open(`release`). 생성자는 `0 < stale_timeout <= release_timeout`이 아니면 `ValueError`.

- [ ] **Step 1: 실패하는 테스트 작성**

`user_pc/tests/test_safety.py`:
```python
import numpy as np
import pytest

from leap_teleop.safety import StaleGuard

OPEN = np.zeros(16)
FIST = np.full(16, 50.0)


def test_no_reading_yet_outputs_open_and_waits():
    guard = StaleGuard(OPEN)
    np.testing.assert_array_equal(guard.resolve(0.0, None, None), OPEN)
    assert guard.mode == "waiting"


def test_fresh_reading_passes_through():
    guard = StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0)
    np.testing.assert_array_equal(guard.resolve(1.0, FIST, 0.9), FIST)
    assert guard.mode == "live"


def test_stale_reading_holds_last_output_then_releases_to_open():
    guard = StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0)
    guard.resolve(1.0, FIST, 1.0)  # live
    np.testing.assert_array_equal(guard.resolve(1.6, FIST, 1.0), FIST)
    assert guard.mode == "hold"
    np.testing.assert_array_equal(guard.resolve(4.1, FIST, 1.0), OPEN)
    assert guard.mode == "release"


def test_recovers_when_fresh_reading_returns():
    guard = StaleGuard(OPEN)
    guard.resolve(0.0, FIST, 0.0)
    guard.resolve(5.0, FIST, 0.0)
    assert guard.mode == "release"
    np.testing.assert_array_equal(guard.resolve(5.1, FIST, 5.1), FIST)
    assert guard.mode == "live"


def test_old_first_reading_without_history_releases_instead_of_holding():
    guard = StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0)
    np.testing.assert_array_equal(guard.resolve(2.0, FIST, 1.0), OPEN)
    assert guard.mode == "release"


def test_outputs_are_copies():
    guard = StaleGuard(OPEN)
    out = guard.resolve(0.0, None, None)
    out[0] = 99.0
    assert guard.resolve(0.0, None, None)[0] == 0.0


@pytest.mark.parametrize("stale,release", [(0.0, 1.0), (-1.0, 1.0), (2.0, 1.0)])
def test_invalid_timeouts_are_rejected(stale, release):
    with pytest.raises(ValueError):
        StaleGuard(OPEN, stale_timeout=stale, release_timeout=release)
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_safety.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.safety'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/safety.py`:
```python
"""Keep the hand safe when the input goes quiet."""

from __future__ import annotations

import numpy as np


class StaleGuard:
    """live -> hold last output -> release to open, based on the age of the input."""

    def __init__(
        self,
        open_command: np.ndarray,
        stale_timeout: float = 0.5,
        release_timeout: float = 3.0,
    ) -> None:
        if not 0.0 < stale_timeout <= release_timeout:
            raise ValueError("need 0 < stale_timeout <= release_timeout")
        self._open = np.array(open_command, dtype=np.float64)
        self._stale = float(stale_timeout)
        self._release = float(release_timeout)
        self._last: np.ndarray | None = None
        self.mode = "waiting"

    def resolve(
        self, now: float, command: np.ndarray | None, command_time: float | None
    ) -> np.ndarray:
        if command is None or command_time is None:
            self.mode = "waiting"
            return self._open.copy()
        age = now - command_time
        if age <= self._stale:
            self.mode = "live"
            self._last = np.array(command, dtype=np.float64)
            return self._last.copy()
        if age <= self._release and self._last is not None:
            self.mode = "hold"
            return self._last.copy()
        self.mode = "release"
        self._last = self._open.copy()
        return self._open.copy()
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_safety.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add stale-input guard (live/hold/release)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: `Source` 기반 클래스와 `KeyboardSource`

**Files:**
- Create: `user_pc/src/leap_teleop/sources/__init__.py` (빈 파일)
- Create: `user_pc/src/leap_teleop/sources/base.py`
- Create: `user_pc/src/leap_teleop/sources/keyboard.py`
- Test: `user_pc/tests/test_keyboard_source.py`

**Interfaces:**
- Consumes: `Reading` (Task 1)
- Produces: `Source` ABC (`poll(now: float) -> Reading | None`, 속성 `stop_requested: bool` 기본 False, `close() -> None` 기본 no-op), `KeyboardSource(read_key: Callable[[], str | None] | None = None)` (space로 grasp 0↔1 토글, `q`/`Q`로 `stop_requested=True`, 다른 키 무시, 한 번의 `poll`에서 쌓인 키를 모두 처리), `TerminalKeyReader(stream=None)` (tty가 아니면 `RuntimeError`, 호출 시 키 한 글자 또는 `None`, `close()`로 터미널 복원)

- [ ] **Step 1: 실패하는 테스트 작성**

`user_pc/tests/test_keyboard_source.py`:
```python
import io

import pytest

from leap_teleop.sources.keyboard import KeyboardSource, TerminalKeyReader


def scripted(keys):
    iterator = iter(keys)
    return lambda: next(iterator, None)


def test_first_poll_is_open_with_the_given_timestamp():
    source = KeyboardSource(read_key=scripted([]))
    reading = source.poll(12.5)
    assert reading.grasp == 0.0
    assert reading.timestamp == 12.5


def test_space_toggles_between_open_and_closed():
    source = KeyboardSource(read_key=scripted([" ", None, " ", None]))
    assert source.poll(0.0).grasp == 1.0
    assert source.poll(0.1).grasp == 0.0


def test_all_pending_keys_are_applied_in_one_poll():
    source = KeyboardSource(read_key=scripted([" ", " ", " ", None]))
    assert source.poll(0.0).grasp == 1.0


def test_q_requests_stop_in_either_case():
    for key in ("q", "Q"):
        source = KeyboardSource(read_key=scripted([key, None]))
        assert not source.stop_requested
        source.poll(0.0)
        assert source.stop_requested


def test_other_keys_are_ignored():
    source = KeyboardSource(read_key=scripted(["x", "\n", None]))
    assert source.poll(0.0).grasp == 0.0
    assert not source.stop_requested


def test_terminal_reader_refuses_a_non_tty_stream():
    with pytest.raises(RuntimeError, match="TTY"):
        TerminalKeyReader(stream=io.StringIO())
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_keyboard_source.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.sources'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/sources/base.py`:
```python
"""Input boundary: anything that can say what the hand should do right now."""

from __future__ import annotations

from abc import ABC, abstractmethod

from leap_teleop.types import Reading


class Source(ABC):
    @abstractmethod
    def poll(self, now: float) -> Reading | None:
        """Return the latest reading, or None if nothing has arrived yet."""

    @property
    def stop_requested(self) -> bool:
        return False

    def close(self) -> None:
        """Release any resources (terminal, ROS node). Default: nothing to do."""
```

`user_pc/src/leap_teleop/sources/keyboard.py`:
```python
"""Space-bar toggle between an open and a closed hand."""

from __future__ import annotations

import os
import select
import sys
from collections.abc import Callable

from leap_teleop.sources.base import Source
from leap_teleop.types import Reading


class TerminalKeyReader:
    """Non-blocking single-key reads from an interactive terminal (cbreak mode)."""

    def __init__(self, stream=None) -> None:
        import termios
        import tty

        self._stream = stream if stream is not None else sys.stdin
        if not self._stream.isatty():
            raise RuntimeError("The keyboard source needs an interactive terminal (stdin is not a TTY)")
        self._termios = termios
        self._fd = self._stream.fileno()
        self._saved = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)

    def __call__(self) -> str | None:
        if select.select([self._fd], [], [], 0)[0]:
            return os.read(self._fd, 1).decode(errors="ignore")
        return None

    def close(self) -> None:
        self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._saved)


class KeyboardSource(Source):
    def __init__(self, read_key: Callable[[], str | None] | None = None) -> None:
        self._read_key = read_key if read_key is not None else TerminalKeyReader()
        self._grasp = 0.0
        self._stop = False

    def poll(self, now: float) -> Reading:
        while (key := self._read_key()) is not None:
            if key == " ":
                self._grasp = 1.0 - self._grasp
            elif key in ("q", "Q"):
                self._stop = True
        return Reading(timestamp=now, grasp=self._grasp)

    @property
    def stop_requested(self) -> bool:
        return self._stop

    def close(self) -> None:
        closer = getattr(self._read_key, "close", None)
        if closer is not None:
            closer()
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_keyboard_source.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add Source base class and space-toggle keyboard source

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: `Ros2LeaderSource`

**Files:**
- Create: `user_pc/src/leap_teleop/sources/ros2_leader.py`
- Test: `user_pc/tests/test_ros2_leader.py`

**Interfaces:**
- Consumes: `Source`, `Reading`, `LeaderGripperConfig`
- Produces: 순수 함수 `grasp_from_trajectory(joint_names: Sequence[str], points_positions: Sequence[Sequence[float]], cfg: LeaderGripperConfig) -> float | None` (이름으로 `cfg.joint_name` 인덱스를 찾아 첫 point의 값을 `(v - open) / (closed - open)`로 정규화해 0~1로 clip; 관절이 없거나 points가 비었거나 값이 짧거나 NaN/inf면 `None`), `Ros2LeaderSource(cfg: LeaderGripperConfig, clock: Callable[[], float] = time.monotonic)` (`Source` 구현; 수신 시각을 `Reading.timestamp`로 사용; `close()`가 노드와 executor를 정리)

- [ ] **Step 1: 실패하는 테스트 작성 (순수 함수만)**

`user_pc/tests/test_ros2_leader.py`:
```python
import pytest

from leap_teleop.config import LeaderGripperConfig
from leap_teleop.sources.ros2_leader import grasp_from_trajectory

CFG = LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0)
NAMES = ["joint1", "joint2", "joint3", "joint4", "joint5", "joint6", "rh_r1_joint"]


def test_reads_the_gripper_joint_by_name():
    positions = [[9.0, 9.0, 9.0, 9.0, 9.0, 9.0, 0.25]]
    assert grasp_from_trajectory(NAMES, positions, CFG) == pytest.approx(0.25)


def test_does_not_depend_on_joint_order():
    names = ["rh_r1_joint", "joint1"]
    assert grasp_from_trajectory(names, [[0.75, 9.0]], CFG) == pytest.approx(0.75)


def test_values_outside_the_measured_range_are_clipped():
    assert grasp_from_trajectory(["rh_r1_joint"], [[1.4]], CFG) == 1.0
    assert grasp_from_trajectory(["rh_r1_joint"], [[-0.3]], CFG) == 0.0


def test_inverted_open_and_closed_values_still_work():
    inverted = LeaderGripperConfig("/t", "rh_r1_joint", 1.0, 0.0)
    assert grasp_from_trajectory(["rh_r1_joint"], [[0.25]], inverted) == pytest.approx(0.75)


def test_offset_range_is_normalised():
    cfg = LeaderGripperConfig("/t", "rh_r1_joint", 0.2, 1.2)
    assert grasp_from_trajectory(["rh_r1_joint"], [[0.7]], cfg) == pytest.approx(0.5)


def test_missing_joint_returns_none():
    assert grasp_from_trajectory(["joint1"], [[0.5]], CFG) is None


def test_empty_points_returns_none():
    assert grasp_from_trajectory(NAMES, [], CFG) is None


def test_too_short_positions_returns_none():
    assert grasp_from_trajectory(NAMES, [[0.1, 0.2]], CFG) is None


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_value_returns_none(bad):
    assert grasp_from_trajectory(["rh_r1_joint"], [[bad]], CFG) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_ros2_leader.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.sources.ros2_leader'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/sources/ros2_leader.py`:
```python
"""Grasp input from the OMY leader gripper (rh_r1_joint on /leader/joint_trajectory).

rclpy is imported inside Ros2LeaderSource.__init__ so the rest of the package, and the
pure function below, work and test without ROS installed.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence

from leap_teleop.config import LeaderGripperConfig
from leap_teleop.sources.base import Source
from leap_teleop.types import Reading


def grasp_from_trajectory(
    joint_names: Sequence[str],
    points_positions: Sequence[Sequence[float]],
    cfg: LeaderGripperConfig,
) -> float | None:
    """Normalise the leader gripper joint of the first trajectory point to 0 (open)..1 (closed)."""
    if cfg.joint_name not in joint_names or not points_positions:
        return None
    index = list(joint_names).index(cfg.joint_name)
    positions = points_positions[0]
    if index >= len(positions):
        return None
    value = float(positions[index])
    if not math.isfinite(value):
        return None
    grasp = (value - cfg.open_value) / (cfg.closed_value - cfg.open_value)
    return min(1.0, max(0.0, grasp))


class Ros2LeaderSource(Source):
    def __init__(
        self, cfg: LeaderGripperConfig, clock: Callable[[], float] = time.monotonic
    ) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from trajectory_msgs.msg import JointTrajectory

        self._cfg = cfg
        self._clock = clock
        self._rclpy = rclpy
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init()
        self._node = rclpy.create_node("leap_teleop_leader_source")
        self._lock = threading.Lock()
        self._latest: Reading | None = None
        # Best-effort QoS matches both reliable and best-effort publishers.
        self._node.create_subscription(
            JointTrajectory, cfg.topic, self._on_message, qos_profile_sensor_data
        )
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._thread.start()

    def _on_message(self, msg) -> None:
        points = [list(point.positions) for point in msg.points[:1]]
        grasp = grasp_from_trajectory(list(msg.joint_names), points, self._cfg)
        if grasp is None:
            return
        reading = Reading(timestamp=self._clock(), grasp=grasp)
        with self._lock:
            self._latest = reading

    def poll(self, now: float) -> Reading | None:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._executor.shutdown()
        self._node.destroy_node()
        if self._owns_context and self._rclpy.ok():
            self._rclpy.shutdown()
        self._thread.join(timeout=1.0)
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_ros2_leader.py -q`
Expected: PASS (11 passed)

- [ ] **Step 5: ROS 노드 부분 수동 스모크 (ROS가 있는 User PC)**

실제 leader 없이 가짜 publisher로 확인한다.
```bash
source /opt/ros/jazzy/setup.bash
cd user_pc && source .venv/bin/activate
export ROS_DOMAIN_ID=30
python - <<'EOF' &
import time
from leap_teleop.config import load_leader_gripper
from leap_teleop.sources.ros2_leader import Ros2LeaderSource
src = Ros2LeaderSource(load_leader_gripper("config/leader_gripper.yaml"))
for _ in range(30):
    print(src.poll(time.monotonic()))
    time.sleep(0.2)
src.close()
EOF
sleep 1
ros2 topic pub -r 10 /leader/joint_trajectory trajectory_msgs/msg/JointTrajectory \
  "{joint_names: [joint1, joint2, joint3, joint4, joint5, joint6, rh_r1_joint], points: [{positions: [0,0,0,0,0,0,0.5]}]}" &
sleep 4; kill %2; wait
```
Expected: 처음엔 `None`, publisher 시작 후 `Reading(... grasp=0.5, ...)`가 출력된다.

- [ ] **Step 6: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add ROS 2 leader gripper source

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 제어 루프 `run_teleop`

**Files:**
- Create: `user_pc/src/leap_teleop/app.py`
- Test: `user_pc/tests/test_app.py`

**Interfaces:**
- Consumes: `Source`, `Retargeter`, `StaleGuard`, `HandDriver`
- Produces: `run_teleop(source, retarget, guard, driver, *, rate_hz: float = 50.0, clock=time.monotonic, sleep=time.sleep, log=print) -> None`. 동작: `driver.start()`가 실패하면 `source.close()` 후 예외를 다시 던지고 `driver.close()`는 호출하지 않는다. 시작 후에는 `source.stop_requested`가 참이 될 때까지 매 주기 `poll → retarget → guard.resolve → driver.command`를 하고, 예외·종료 때 항상 `source.close()` 다음 `driver.close()`를 호출한다. `guard.mode`가 바뀔 때만 `log`를 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`user_pc/tests/test_app.py`:
```python
import numpy as np
import pytest

from leap_teleop.app import run_teleop
from leap_teleop.config import make_posture
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.base import Source
from leap_teleop.types import Reading

OPEN = np.zeros(16)
FIST = make_posture({"index_mcp_flex": 60.0})


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeSource(Source):
    def __init__(self, grasp_at, silent_after=None, stop_at=1.0):
        self._grasp_at = grasp_at
        self._silent_after = silent_after
        self._stop_at = stop_at
        self._now = 0.0
        self.closed = False

    def poll(self, now):
        self._now = now
        if self._silent_after is not None and now >= self._silent_after:
            return None
        return Reading(timestamp=now, grasp=self._grasp_at(now))

    @property
    def stop_requested(self):
        return self._now >= self._stop_at

    def close(self):
        self.closed = True


class FakeDriver:
    def __init__(self, clock, fail_start=False):
        self._clock = clock
        self._fail_start = fail_start
        self.started = False
        self.closed = False
        self.commands = []

    def start(self):
        if self._fail_start:
            raise OSError("no hand")
        self.started = True

    def command(self, angles):
        self.commands.append((self._clock(), np.array(angles)))

    def close(self):
        self.closed = True


def run(source, clock, driver, **kwargs):
    run_teleop(
        source,
        ScalarPostureRetargeter(OPEN, FIST),
        StaleGuard(OPEN, stale_timeout=0.5, release_timeout=3.0),
        driver,
        rate_hz=10.0,
        clock=clock,
        sleep=clock.sleep,
        log=lambda _line: None,
        **kwargs,
    )


def test_grasp_changes_reach_the_driver_and_everything_is_closed():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 0.0 if t < 0.5 else 1.0, stop_at=1.0)
    run(source, clock, driver)
    assert driver.started and driver.closed and source.closed
    np.testing.assert_array_equal(driver.commands[0][1], OPEN)
    np.testing.assert_array_equal(driver.commands[-1][1], FIST)


def test_silent_source_holds_then_releases_to_open():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 1.0, silent_after=0.3, stop_at=4.0)
    run(source, clock, driver)
    at_one_and_a_half = [cmd for t, cmd in driver.commands if abs(t - 1.5) < 0.05][0]
    np.testing.assert_array_equal(at_one_and_a_half, FIST)  # hold
    np.testing.assert_array_equal(driver.commands[-1][1], OPEN)  # released


def test_no_reading_at_all_keeps_the_hand_open():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 1.0, silent_after=0.0, stop_at=0.5)
    run(source, clock, driver)
    assert all(not cmd.any() for _, cmd in driver.commands)


def test_error_in_the_loop_still_closes_source_and_driver():
    clock = FakeClock()
    driver = FakeDriver(clock)

    class Exploding(FakeSource):
        def poll(self, now):
            raise RuntimeError("boom")

    source = Exploding(lambda t: 0.0)
    with pytest.raises(RuntimeError, match="boom"):
        run(source, clock, driver)
    assert source.closed and driver.closed


def test_failed_start_closes_source_but_not_driver():
    clock = FakeClock()
    driver = FakeDriver(clock, fail_start=True)
    source = FakeSource(lambda t: 0.0)
    with pytest.raises(OSError, match="no hand"):
        run(source, clock, driver)
    assert source.closed
    assert not driver.closed
    assert driver.commands == []


def test_mode_changes_are_logged_once_each():
    clock = FakeClock()
    driver = FakeDriver(clock)
    source = FakeSource(lambda t: 1.0, silent_after=0.3, stop_at=4.0)
    lines = []
    run_teleop(
        source,
        ScalarPostureRetargeter(OPEN, FIST),
        StaleGuard(OPEN, 0.5, 3.0),
        driver,
        rate_hz=10.0,
        clock=clock,
        sleep=clock.sleep,
        log=lines.append,
    )
    assert [line.split()[-1] for line in lines] == ["live", "hold", "release"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_app.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.app'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/app.py`:
```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_app.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add teleop control loop

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: CLI `leap-teleop`

**Files:**
- Create: `user_pc/src/leap_teleop/cli.py`
- Test: `user_pc/tests/test_cli.py`

**Interfaces:**
- Consumes: 앞선 모든 모듈
- Produces: `build_parser() -> argparse.ArgumentParser`, `build_source(args) -> Source`, `build_driver(args) -> HandDriver`, `main(argv: Sequence[str] | None = None) -> int`. 옵션: `--source {keyboard,leader}`(기본 keyboard), `--port`(기본 `/dev/ttyUSB0`), `--motor-calibration-file`(기본 `config/hardware_motors.yaml`), `--postures`(기본 `config/postures.yaml`), `--leader-gripper`(기본 `config/leader_gripper.yaml`), `--rate`(기본 50, 10~200), `--stale-timeout`(0.5), `--release-timeout`(3.0), `--current-limit`(300), `--dry-run`. 설정·검증 오류는 `error: ...`를 stderr에 쓰고 종료 코드 2를 반환한다. `--dry-run`이 아닐 때 보정 파일이 없으면 터미널·하드웨어를 건드리기 전에 거부한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`user_pc/tests/test_cli.py`:
```python
import io
from pathlib import Path

import pytest

from leap_teleop import cli
from leap_teleop.sources.base import Source

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
BASE = [
    "--postures", str(CONFIG_DIR / "postures.yaml"),
    "--leader-gripper", str(CONFIG_DIR / "leader_gripper.yaml"),
]


class StoppedSource(Source):
    @property
    def stop_requested(self):
        return True

    def poll(self, now):
        return None


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.source == "keyboard"
    assert args.port == "/dev/ttyUSB0"
    assert args.rate == 50.0
    assert args.current_limit == 300
    assert args.dry_run is False


@pytest.mark.parametrize("rate", ["5", "500"])
def test_rate_outside_watchdog_safe_range_is_rejected(rate, capsys):
    code = cli.main(BASE + ["--dry-run", "--rate", rate])
    assert code == 2
    assert "rate" in capsys.readouterr().err


def test_hardware_mode_refuses_to_run_without_motor_calibration(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "build_source", lambda args: pytest.fail("touched the terminal"))
    missing = tmp_path / "nope.yaml"
    code = cli.main(BASE + ["--motor-calibration-file", str(missing)])
    assert code == 2
    err = capsys.readouterr().err
    assert "calibrate_motors" in err


def test_keyboard_source_without_a_terminal_is_a_clean_error(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO())
    code = cli.main(BASE + ["--dry-run", "--source", "keyboard"])
    assert code == 2
    assert "TTY" in capsys.readouterr().err


def test_dry_run_starts_and_closes_the_log_driver(monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_source", lambda args: StoppedSource())
    code = cli.main(BASE + ["--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[dry-run] start" in out
    assert "[dry-run] close" in out
```

- [ ] **Step 2: 실패 확인**

Run: `cd user_pc && python -m pytest tests/test_cli.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'leap_teleop.cli'`

- [ ] **Step 3: 구현**

`user_pc/src/leap_teleop/cli.py`:
```python
"""Command line entry point: `leap-teleop`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from leap_teleop.app import run_teleop
from leap_teleop.config import load_leader_gripper, load_postures
from leap_teleop.hand.base import HandDriver
from leap_teleop.retarget.scalar_posture import ScalarPostureRetargeter
from leap_teleop.safety import StaleGuard
from leap_teleop.sources.base import Source


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="leap-teleop",
        description="Drive a LEAP Hand v1 from the keyboard or the OMY leader gripper.",
    )
    parser.add_argument("--source", choices=("keyboard", "leader"), default="keyboard")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="LEAP Hand serial port")
    parser.add_argument(
        "--motor-calibration-file", type=Path, default=Path("config/hardware_motors.yaml")
    )
    parser.add_argument("--postures", type=Path, default=Path("config/postures.yaml"))
    parser.add_argument("--leader-gripper", type=Path, default=Path("config/leader_gripper.yaml"))
    parser.add_argument("--rate", type=float, default=50.0, help="control loop Hz (10-200)")
    parser.add_argument("--stale-timeout", type=float, default=0.5)
    parser.add_argument("--release-timeout", type=float, default=3.0)
    parser.add_argument("--current-limit", type=int, default=300, help="motor current limit in mA")
    parser.add_argument("--dry-run", action="store_true", help="log targets, do not touch hardware")
    return parser


def build_source(args: argparse.Namespace) -> Source:
    if args.source == "leader":
        from leap_teleop.sources.ros2_leader import Ros2LeaderSource

        return Ros2LeaderSource(load_leader_gripper(args.leader_gripper))
    from leap_teleop.sources.keyboard import KeyboardSource

    return KeyboardSource()


def build_driver(args: argparse.Namespace) -> HandDriver:
    if args.dry_run:
        from leap_teleop.hand.dry_run import LogDriver

        return LogDriver()
    from leap_teleop.hand.leap_driver import LeapHandDriver
    from leap_teleop.hand.leap_v1 import LeapHandHardwareController

    controller = LeapHandHardwareController(
        args.port,
        current_limit_milliamps=args.current_limit,
        motor_calibration=args.motor_calibration_file,
    )
    return LeapHandDriver(controller)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not 10.0 <= args.rate <= 200.0:
            raise ValueError("rate must be between 10 and 200 Hz (the bus watchdog is 500 ms)")
        open_pose, fist_pose = load_postures(args.postures)
        if not args.dry_run and not args.motor_calibration_file.exists():
            raise FileNotFoundError(
                f"{args.motor_calibration_file} not found. Run "
                "`python -m leap_teleop.tools.calibrate_motors` first; refusing to use nominal zeros."
            )
        guard = StaleGuard(open_pose, args.stale_timeout, args.release_timeout)
        retarget = ScalarPostureRetargeter(open_pose, fist_pose)
        driver = build_driver(args)
        source = build_source(args)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    try:
        run_teleop(source, retarget, guard, driver, rate_hz=args.rate)
    except KeyboardInterrupt:
        print("interrupted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `cd user_pc && python -m pytest tests/test_cli.py -q`
Expected: PASS (6 passed). 이어서 전체: `python -m pytest -q` → 모두 PASS.

- [ ] **Step 5: 터미널 스모크 (하드웨어 없이)**

```bash
cd user_pc && source .venv/bin/activate
leap-teleop --dry-run
```
Expected: `[dry-run] start`와 `[teleop] live`가 보이고 `space`를 누르면 `[dry-run] cmd max=...`의 값이 0에서 60으로 바뀐다 (25번째 명령마다 출력). `q`로 종료하면 `[dry-run] close`가 나오고 터미널이 정상 입력 상태(echo 유지)로 돌아온다.

- [ ] **Step 6: Commit**

```bash
git add user_pc
git commit -m "feat(user_pc): add leap-teleop CLI with dry-run and calibration guard

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 11: 실물 bring-up 도구 이식

스펙 5절의 `scripts/` 대신 패키지 내부 `leap_teleop/tools/`로 둔다 (`python -m`으로 실행하고 테스트에서 import할 수 있게 하기 위한 조정, 스펙에도 반영한다).

**Files:**
- Create: `user_pc/src/leap_teleop/tools/__init__.py` (빈 파일)
- Create: `user_pc/src/leap_teleop/tools/check_hardware.py` (이식)
- Create: `user_pc/src/leap_teleop/tools/calibrate_motors.py` (이식)
- Create: `user_pc/src/leap_teleop/tools/joint_test.py` (이식)
- Create: `user_pc/tests/test_joint_test_tool.py` (이식)
- Modify: `docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md` (폴더 구조의 `scripts/` → `src/leap_teleop/tools/`)

**Interfaces:**
- Consumes: `LeapHandHardwareController`, `HardwareMotorCalibration`, `ANGLE_NAMES`
- Produces: `python -m leap_teleop.tools.check_hardware`, `python -m leap_teleop.tools.calibrate_motors`, `python -m leap_teleop.tools.joint_test`

- [ ] **Step 1: 복사와 import 수정**

```bash
OLD=/tmp/leap-hand-src
test "$(git -C $OLD rev-parse --short HEAD)" = ddfabaa || echo "WRONG COMMIT"
D=user_pc/src/leap_teleop/tools
T=user_pc/tests
mkdir -p $D && touch $D/__init__.py
cp $OLD/leap_hand_hardware_check.py $D/check_hardware.py
cp $OLD/leap_hand_motor_calibration.py $D/calibrate_motors.py
cp $OLD/leap_hand_joint_test.py $D/joint_test.py
cp $OLD/tests/test_leap_hand_joint_test.py $T/test_joint_test_tool.py

sed -i 's/^from hand_angles import ANGLE_NAMES$/from leap_teleop.hand.joints import ANGLE_NAMES/' $D/*.py $T/test_joint_test_tool.py
sed -i 's/^from hardware_calibration import /from leap_teleop.hand.calibration import /' $D/*.py
sed -i 's/^from leap_hand_hardware_controller import/from leap_teleop.hand.leap_v1 import/' $D/*.py $T/test_joint_test_tool.py
sed -i 's/^from leap_hand_joint_test import/from leap_teleop.tools.joint_test import/' $T/test_joint_test_tool.py
sed -i 's#calibration/hardware_motors.yaml#config/hardware_motors.yaml#g' $D/*.py

sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (leap_hand_hardware_check.py). Import paths adjusted; logic unchanged.' $D/check_hardware.py
sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (leap_hand_motor_calibration.py). Import paths adjusted; default path changed to config/.' $D/calibrate_motors.py
sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (leap_hand_joint_test.py). Import paths adjusted; logic unchanged.' $D/joint_test.py
sed -i '1i # Vendored from shinjju1209/leap-hand@ddfabaa (tests/test_leap_hand_joint_test.py). Import paths adjusted.' $T/test_joint_test_tool.py

grep -rnE "^(from|import) (hand_angles|hardware_calibration|leap_hand)" $D $T || echo "no stale imports"
```
Expected: `no stale imports`

- [ ] **Step 2: 테스트와 import 확인**

```bash
cd user_pc && source .venv/bin/activate
python -m pytest tests/test_joint_test_tool.py -q
python -m leap_teleop.tools.check_hardware --help
python -m leap_teleop.tools.calibrate_motors --help
python -m leap_teleop.tools.joint_test --help
```
Expected: 테스트 PASS, 세 `--help`가 오류 없이 사용법을 출력한다. 하나라도 `if __name__ == "__main__"` 블록이 없어 아무것도 출력하지 않으면 원본의 `main` 함수 이름을 확인해 그 파일 끝에 `if __name__ == "__main__":\n    raise SystemExit(main())`를 추가한다.

- [ ] **Step 3: 스펙 폴더 구조 수정**

스펙 5절 트리에서 `scripts/` 블록(`check_hardware.py`, `calibrate_motors.py`, `joint_test.py`)을 `src/leap_teleop/tools/` 아래로 옮기고 한 줄 설명 `# python -m leap_teleop.tools.<name>`을 단다. 6절 이식표의 `scripts/...` 경로도 `tools/...`로 고친다.

- [ ] **Step 4: 전체 테스트와 Commit**

```bash
cd user_pc && python -m pytest -q
cd .. && git add user_pc docs/superpowers/specs
git commit -m "feat(user_pc): vendor LEAP bring-up tools under leap_teleop.tools

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Expected: 전체 PASS

---

### Task 12: 실물 시험 절차 문서

**Files:**
- Create: `user_pc/README.md`
- Modify: `README.md` (루트, 한 줄 링크 추가)

**Interfaces:**
- Consumes: Task 1~11의 명령
- Produces: 내일 실물 시험에서 따라 할 순서

- [ ] **Step 1: `user_pc/README.md` 작성**

````markdown
# leap_teleop (User PC)

LEAP Hand v1을 키보드 또는 OMY leader 그리퍼로 구동한다. 설계: `../docs/superpowers/specs/2026-10-08-leap-omy-teleop-design.md`

## 설치
```bash
cd user_pc
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q          # 하드웨어 없이 전부 통과해야 한다
```

## 실물 시험 순서 (건너뛰지 않는다)
> 5V 전원을 즉시 차단할 수 있어야 한다. 시험 중 손가락 주변에 손·케이블을 두지 않는다. LEAP Hand v1(16모터) 전용이다.

1. 포트 권한과 지연 설정 (`/dev/ttyUSB0`)
   ```bash
   sudo usermod -aG dialout $USER   # 이후 재로그인, 또는 임시로: sudo chmod 666 /dev/ttyUSB0
   echo 1 | sudo tee /sys/bus/usb-serial/devices/ttyUSB0/latency_timer
   ```
2. Torque OFF 연결 진단 (ID 0~15, 오류 0 확인)
   ```bash
   python -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0
   ```
3. 편 손 영점 기록 (손을 편 자세로 고정하고 `RECORD` 입력) → `config/hardware_motors.yaml` 생성 (gitignore됨)
   ```bash
   python -m leap_teleop.tools.calibrate_motors --port /dev/ttyUSB0
   ```
4. 단일 관절 ±5° 저속 시험. 반대로 움직이는 관절은 `config/hardware_motors.yaml`에서 `sign: -1`로 고친다. 사용법은 `python -m leap_teleop.tools.joint_test --help`.
5. 파이프라인만 확인 (하드웨어 없음): `leap-teleop --dry-run`
6. 키보드로 실물 구동: `leap-teleop` — `space`로 open/fist 토글, `q`로 종료
   - 첫 동작이 너무 작거나 크면 `config/postures.yaml`의 `fist` 값을 조금씩 조정한다.

## leader 그리퍼로 구동
1. Robot PC에서 텔레옵(또는 leader만) 실행. User PC 쪽:
   ```bash
   source /opt/ros/jazzy/setup.bash
   export ROS_DOMAIN_ID=30
   ros2 topic echo /leader/joint_trajectory --field points[0].positions
   ```
2. leader 그리퍼를 편 상태와 쥔 상태에서 7번째 값(`rh_r1_joint`)을 읽어 `config/leader_gripper.yaml`의 `open_value` / `closed_value`에 넣는다.
3. 실행
   ```bash
   leap-teleop --source leader
   ```
   토픽이 0.5초 끊기면 마지막 자세를 유지하고, 3초 끊기면 손이 열린다.

## 문제 해결
- `error: ... not found. Run calibrate_motors`: 3단계를 먼저 한다 (공칭 영점으로 움직이지 않는다).
- `Missing or unresponsive DYNAMIXEL IDs`: 5V 전원, USB 케이블, Dynamixel Wizard가 포트를 점유 중인지 확인한다.
- 토픽이 안 보임: 두 PC가 같은 네트워크인지, 양쪽 `ROS_DOMAIN_ID=30`인지 확인한다.
````

- [ ] **Step 2: 루트 `README.md`에 링크 추가**

루트 `README.md` 끝에 다음 한 줄을 추가한다 (기존 내용은 건드리지 않는다).
```markdown

- [`user_pc/`](user_pc/README.md): LEAP Hand 텔레옵 구현 (키보드 / OMY leader 그리퍼)
```

- [ ] **Step 3: Commit**

```bash
git add user_pc/README.md README.md
git commit -m "docs: add LEAP teleop bring-up procedure

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 13 (조건부): Robot PC 레포의 `omy_leap_bringup` 패키지

**실행 조건:** 그리퍼를 제거한 상태에서 공식 `ros2 launch open_manipulator_bringup omy_ai.launch.py`가 실패한 것을 확인한 경우에만 실행한다. 공식 launch가 정상이면 이 Task는 건너뛰고, 레포 README의 상태 줄만 "불필요 확인"으로 고친다.

**Files (레포 `/home/hamin/Projects/OMY_Tactile_Robot_PC`):**
- Create: `omy_leap_bringup/package.xml`, `setup.py`, `setup.cfg`, `resource/omy_leap_bringup`, `omy_leap_bringup/__init__.py`
- Create: `omy_leap_bringup/urdf/omy_f3m_no_gripper.urdf.xacro`
- Create: `omy_leap_bringup/config/hardware_controller_manager.yaml`
- Create: `omy_leap_bringup/launch/follower_no_gripper.launch.py`, `omy_ai_no_gripper.launch.py`
- Modify: `README.md` (상태 줄)

**Interfaces:**
- Consumes: Robot PC 컨테이너에 설치된 `open_manipulator_description`, `open_manipulator_bringup`
- Produces: `ros2 launch omy_leap_bringup omy_ai_no_gripper.launch.py` — 팔은 실제 하드웨어, `OMYF3MEndUnitSystem`만 mock

- [ ] **Step 1: 패키지 골격 작성**

```bash
cd /home/hamin/Projects/OMY_Tactile_Robot_PC
P=omy_leap_bringup
mkdir -p $P/urdf $P/config $P/launch $P/resource $P/$P
touch $P/resource/$P $P/$P/__init__.py
```

`omy_leap_bringup/package.xml`:
```xml
<?xml version="1.0"?>
<package format="3">
  <name>omy_leap_bringup</name>
  <version>0.1.0</version>
  <description>OMY F3M follower bringup without the gripper (end unit mocked) for LEAP Hand teleop.</description>
  <maintainer email="chlgkals0730@gmail.com">SHAPE-UP Tactile</maintainer>
  <license>Apache-2.0</license>
  <exec_depend>open_manipulator_bringup</exec_depend>
  <exec_depend>open_manipulator_description</exec_depend>
  <exec_depend>controller_manager</exec_depend>
  <exec_depend>robot_state_publisher</exec_depend>
  <exec_depend>xacro</exec_depend>
  <test_depend>python3-pytest</test_depend>
  <export>
    <build_type>ament_python</build_type>
  </export>
</package>
```

`omy_leap_bringup/setup.cfg`:
```ini
[develop]
script_dir=$base/lib/omy_leap_bringup
[install]
install_scripts=$base/lib/omy_leap_bringup
```

`omy_leap_bringup/setup.py`:
```python
from glob import glob

from setuptools import find_packages, setup

package_name = 'omy_leap_bringup'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/urdf', glob('urdf/*.xacro')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='SHAPE-UP Tactile',
    maintainer_email='chlgkals0730@gmail.com',
    description='OMY F3M follower bringup without the gripper (end unit mocked).',
    license='Apache-2.0',
)
```

- [ ] **Step 2: 공식 파일을 복사해 최소 수정**

```bash
SUB=/home/hamin/Projects/SHAPE_UP_Tactile/third_party/open_manipulator
P=omy_leap_bringup
cp $SUB/open_manipulator_description/urdf/omy_f3m/omy_f3m.urdf.xacro $P/urdf/omy_f3m_no_gripper.urdf.xacro
cp $SUB/open_manipulator_bringup/config/omy_f3m_follower_ai/hardware_controller_manager.yaml $P/config/hardware_controller_manager.yaml
cp $SUB/open_manipulator_bringup/launch/omy_f3m_follower_ai.launch.py $P/launch/follower_no_gripper.launch.py
cp $SUB/open_manipulator_bringup/launch/omy_ai.launch.py $P/launch/omy_ai_no_gripper.launch.py

python3 - <<'EOF'
from pathlib import Path

def patch(path, old, new):
    p = Path(path)
    s = p.read_text()
    assert s.count(old) == 1, f"{path}: pattern found {s.count(old)} times:\n{old}"
    p.write_text(s.replace(old, new))

P = "omy_leap_bringup"

# 1) URDF: only the end-unit (gripper) system uses mock hardware.
patch(
    f"{P}/urdf/omy_f3m_no_gripper.urdf.xacro",
    '''  <xacro:omy_f3m_end_unit_system
    name="OMYF3MEndUnitSystem" prefix="$(arg prefix)" use_sim="$(arg use_sim)"
    use_mock_hardware="$(arg use_mock_hardware)"''',
    '''  <!-- Gripper removed (LEAP Hand mounted): keep rh_r1_joint as a mocked virtual joint. -->
  <xacro:omy_f3m_end_unit_system
    name="OMYF3MEndUnitSystem" prefix="$(arg prefix)" use_sim="$(arg use_sim)"
    use_mock_hardware="true"''',
)

# 2) follower launch: use our URDF and controller config.
patch(
    f"{P}/launch/follower_no_gripper.launch.py",
    '''            FindPackageShare('open_manipulator_description'),
            'urdf',
            'omy_f3m',
            'omy_f3m.urdf.xacro',''',
    '''            FindPackageShare('omy_leap_bringup'),
            'urdf',
            'omy_f3m_no_gripper.urdf.xacro',''',
)
patch(
    f"{P}/launch/follower_no_gripper.launch.py",
    '''    controller_manager_config = PathJoinSubstitution([
        FindPackageShare('open_manipulator_bringup'),
        'config',
        'omy_f3m_follower_ai',
        'hardware_controller_manager.yaml',
    ])''',
    '''    controller_manager_config = PathJoinSubstitution([
        FindPackageShare('omy_leap_bringup'),
        'config',
        'hardware_controller_manager.yaml',
    ])''',
)

# 3) omy_ai launch: start our follower instead of the official one.
patch(
    f"{P}/launch/omy_ai_no_gripper.launch.py",
    '''            'launch',
            'open_manipulator_bringup',
            'omy_f3m_follower_ai.launch.py',''',
    '''            'launch',
            'omy_leap_bringup',
            'follower_no_gripper.launch.py',''',
)
print("patched")
EOF
```
Expected: `patched` (패턴이 정확히 한 번 일치하지 않으면 assert로 중단된다. 원본 버전이 달라진 것이므로 서브모듈 commit과 비교해 패턴을 맞춘다.)

- [ ] **Step 3: 정적 검증 (open_manipulator_description이 설치된 환경: Robot PC 컨테이너)**

```bash
cd /home/hamin/Projects/OMY_Tactile_Robot_PC/omy_leap_bringup
source /opt/ros/jazzy/setup.bash
xacro urdf/omy_f3m_no_gripper.urdf.xacro > /tmp/omy_no_gripper.urdf
grep -c "mock_components/GenericSystem" /tmp/omy_no_gripper.urdf
grep -c "dynamixel_hardware_interface/DynamixelHardware" /tmp/omy_no_gripper.urdf
check_urdf /tmp/omy_no_gripper.urdf | head -3
python3 -m py_compile launch/*.py
```
Expected: 첫 번째 `1`(end unit만 mock), 두 번째 `1`(팔 시스템은 실제 하드웨어), `check_urdf`가 `robot name is: ...`, 컴파일 오류 없음.

- [ ] **Step 4: 빌드와 실행 시험 (Robot PC 컨테이너, 그리퍼 제거 상태)**

레포를 Robot PC에 clone하고 컨테이너의 워크스페이스(`ros2 pkg prefix open_manipulator_bringup`로 위치 확인)에서 이 패키지만 빌드한다.
```bash
colcon build --packages-select omy_leap_bringup
source install/setup.bash
ros2 launch omy_leap_bringup omy_ai_no_gripper.launch.py
```
Expected: `arm_controller`와 `joint_state_broadcaster`가 active가 되고, leader를 움직이면 follower 팔이 따라온다. 별도 터미널에서 `ros2 control list_controllers`로 두 컨트롤러가 `active`인지 확인한다. 실패하면 사용 로그와 함께 중계 노드(6관절 follower) 대안을 스펙 3절 기준으로 다시 논의한다.

- [ ] **Step 5: README 상태 줄 갱신과 Commit/Push**

README의 `## 상태` 문단을 "`omy_leap_bringup` 추가됨. 사용법: `ros2 launch omy_leap_bringup omy_ai_no_gripper.launch.py`"로 고친 뒤:
```bash
git add -A
git commit -m "feat: add omy_leap_bringup (follower with mocked end unit)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git push
```

---

## Self-Review 기록

- **스펙 커버리지:** 1절 목표 → Task 7·8·9·10; 3절 그리퍼 → Task 13; 4절 경계 3곳 → Task 3·5·7; 5절 구조 → Task 1~12; 6절 이식 → Task 2·11 (fist 값은 Task 4); 7절 소스 → Task 7·8; 8절 안전 → Task 6·9·10 (기존 컨트롤러 안전장치는 Task 2로 유지, `--dry-run`은 Task 10); 9절 설정/Git → Task 1·2; 10절 환경 → Task 1; 11절 테스트 → 각 Task; 12절 순서 → Task 12.
- **스펙 대비 편차:** `scripts/` → `src/leap_teleop/tools/` (Task 11에서 스펙도 수정). 스펙 8절의 "시작 시 open 기준 점프 금지"는 컨트롤러 `enable_torque()`가 현재 위치를 목표로 시드하고 속도 제한을 적용하는 기존 동작에 의존한다 (Task 2의 이식 테스트가 이를 검증).
- **타입 일관성:** `Reading`, `Retargeter`, `StaleGuard.resolve(now, command, command_time)`, `HandDriver.start/command/close`, `LeaderGripperConfig` 필드명이 Task 간 일치함을 확인했다.
