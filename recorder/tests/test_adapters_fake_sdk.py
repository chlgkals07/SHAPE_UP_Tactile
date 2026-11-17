"""The device adapters run against stand-ins for their SDKs.

This executes the adapters' own open / read / close code, which no other test does. The
stand-ins only mirror the calls the adapters make: they say nothing about whether the real
SDKs behave that way. That still has to be checked on the devices.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from conftest import PLACES_A

from tactile_rec.clock import FakeClock
from tactile_rec.streams.arm_zenoh import ArmZenohStream, use_client_mode
from tactile_rec.streams.paxini import PaxiniStream
from tactile_rec.streams.realsense import RealSenseStream
from tactile_rec.types import NO_TIME, STATUS_ERROR

MS = 1_000_000


def module(monkeypatch, name, **members):
    made = ModuleType(name)
    for key, member in members.items():
        setattr(made, key, member)
    monkeypatch.setitem(sys.modules, name, made)
    return made


# ---- Paxini ------------------------------------------------------------------------------------


class FrameError(Exception):
    pass


class BoardTimeout(Exception):
    pass


class Board:
    """Four modules in the order the board reports them; frames are whatever the test queues."""

    opened: list[Board] = []

    def __init__(self, port, baudrate):
        self.port, self.baudrate = port, baudrate
        self.calls: list[str] = []
        self.frames: list[object] = []
        self.transport = SimpleNamespace(read_auto_push_frame=self._read)
        Board.opened.append(self)

    def _read(self, timeout):
        if not self.frames:
            raise BoardTimeout
        return self.frames.pop(0)

    def open(self):
        self.calls.append("open")

    def close(self):
        self.calls.append("close")

    def read_version(self):
        return "1.2.3"

    def read_auto_push_config(self):
        return SimpleNamespace(
            active_modules=[0, 1, 2, 3], point_counts={0: 52, 1: 25, 2: 52, 3: 25},
            has_resultant=True, has_distributed=True,
        )

    def enable_auto_push(self):
        self.calls.append("push on")

    def disable_auto_push(self):
        self.calls.append("push off")

    def calibrate(self):
        self.calls.append("calibrate")


@pytest.fixture
def paxini(monkeypatch):
    Board.opened = []
    names = {0: "Thumb-Tip", 1: "Thumb-Middle", 2: "Index-Tip", 3: "Index-Middle"}
    module(
        monkeypatch, "paxini_sdk", HighSpeedHandBoard=Board,
        registers=SimpleNamespace(MODULE_NAMES=names),
        sensor_registry=SimpleNamespace(
            find_by_point_count=lambda n: SimpleNamespace(vendor_part_code=f"PX-{n}")
        ),
    )
    module(monkeypatch, "paxini_sdk.exceptions", FrameError=FrameError, TimeoutError=BoardTimeout)

    def parse_auto_push(raw):
        if raw == "garbage":
            raise FrameError("checksum")
        return SimpleNamespace(valid_data=raw[0], error_code=raw[1])

    module(monkeypatch, "paxini_sdk.protocol", parse_auto_push=parse_auto_push)
    cfg = {"port": "/dev/ttyACM0", "baudrate": 921600, "hz": 90, "required": True,
           "places": PLACES_A}
    stream = PaxiniStream("tactile_a", cfg, FakeClock())
    stream._open()
    return stream


def test_paxini_open_reads_the_layout_and_starts_the_push_stream(paxini):
    board = paxini._board
    assert (board.port, board.baudrate) == ("/dev/ttyACM0", 921600)
    assert board.calls == ["open", "push on"]
    assert [m.place for m in paxini.layout.modules] == [
        "thumb_tip", "thumb_pad", "index_tip", "index_pad"
    ]
    assert paxini.spec.fields["payload"].shape == (paxini.layout.payload_size,)
    assert paxini.spec.meta["firmware"] == "1.2.3"
    assert paxini.spec.meta["layout"]["modules"][0]["model"] == "PX-52"
    paxini._close()
    assert board.calls[-2:] == ["push off", "close"] and paxini._board is None


def test_paxini_open_with_a_sensor_on_the_wrong_connector_closes_the_port(monkeypatch, paxini):
    wrong = dict(PLACES_A)
    wrong["Ring-Tip"] = wrong.pop("Index-Tip")
    cfg = {"port": "/dev/ttyACM1", "baudrate": 921600, "hz": 90, "required": True,
           "places": wrong}
    stream = PaxiniStream("tactile_b", cfg, FakeClock())
    with pytest.raises(ValueError, match="do not match"):
        stream._open()
    assert Board.opened[-1].calls == ["open", "close"]  # not left open for the retry


def test_paxini_frames_become_samples_and_bad_ones_are_counted(paxini):
    size = paxini.layout.payload_size
    good = bytes(range(256)) * (size // 256 + 1)
    paxini._board.frames = [
        (good[:size], 0), "garbage", (good[: size - 3], 0), (good[:size], 7),
    ]
    paxini._read_once()
    first = paxini.latest()
    assert first.data["payload"].shape == (size,) and first.data["payload"][5] == 5
    assert first.t_recv_ns == paxini.clock.now_ns()
    paxini._read_once()  # FrameError
    paxini._read_once()  # three bytes short
    paxini._read_once()  # complete, but the board reports error code 7
    paxini._read_once()  # nothing more: the SDK's timeout is not an error
    assert paxini.health().count == 2 and int(paxini.latest().data["error_code"]) == 7
    assert paxini.counters() == {"subscriber_errors": 0, "bad_frames": 2, "device_errors": 1}

    paxini.clock.set_ns(paxini.clock.now_ns() + 1000 * MS)
    paxini._board.frames = [(good[: size - 3], 0)]
    paxini._read_once()  # only bad frames for a second: the stream says why
    health = paxini.health()
    assert health.status == STATUS_ERROR and "payload bytes" in health.message


def test_paxini_zero_is_run_between_two_frames(paxini):
    paxini.zero()
    paxini._read_once()
    assert paxini._board.calls[-3:] == ["push off", "calibrate", "push on"]
    assert paxini.wait_zero(0.01)["ok"] and paxini.health().count == 0


# ---- RealSense ---------------------------------------------------------------------------------


class Frame:
    def __init__(self, number, domain, value=0):
        self.number, self.domain, self.value = number, domain, value

    def get_data(self):
        return np.full((48, 64, 3), self.value, dtype=np.uint8)

    def get_frame_timestamp_domain(self):
        return self.domain

    def get_timestamp(self):
        return 1_700_000_000_000.0 + self.number  # ms

    def get_frame_number(self):
        return self.number


@pytest.fixture
def realsense(monkeypatch):
    log = SimpleNamespace(calls=[], options=[], frames=[])
    info = SimpleNamespace(serial_number="serial", name="name", usb_type_descriptor="usb")
    option = SimpleNamespace(enable_auto_exposure="auto", exposure="exposure")
    sensor = SimpleNamespace(
        supports=lambda _option: True, set_option=lambda *pair: log.options.append(pair)
    )
    device = SimpleNamespace(
        get_info=lambda key: {"serial": "335122272125", "name": "D405", "usb": "3.2"}[key],
        supports=lambda _key: True, query_sensors=lambda: [sensor],
    )

    class Config:
        def enable_device(self, serial):
            log.calls.append(("device", serial))

        def enable_stream(self, *args):
            log.calls.append(("stream", *args))

    class Pipeline:
        def start(self, _config):
            log.calls.append(("start",))
            return SimpleNamespace(get_device=lambda: device)

        def stop(self):
            log.calls.append(("stop",))

        def wait_for_frames(self, _timeout_ms):
            frame = log.frames.pop(0)
            return SimpleNamespace(get_color_frame=lambda: frame)

    module(
        monkeypatch, "pyrealsense2", pipeline=Pipeline, config=Config, camera_info=info,
        option=option, stream=SimpleNamespace(color="color"), format=SimpleNamespace(bgr8="bgr8"),
    )
    return log


def camera(serial="335122272125", exposure_us=0):
    cfg = {"width": 64, "height": 48, "fps": 30, "serial": serial, "rotation_deg": 90,
           "exposure_us": exposure_us, "required": True}
    return RealSenseStream("cam_wrist", cfg, FakeClock())


def test_realsense_opens_the_configured_serial_and_fixes_exposure_when_asked(realsense):
    stream = camera(exposure_us=8000)
    stream._open()
    assert realsense.calls == [
        ("device", "335122272125"), ("stream", "color", 64, 48, "bgr8", 30), ("start",)
    ]
    assert realsense.options == [("auto", 0), ("exposure", 8000.0)]
    assert stream.spec.meta["serial"] == "335122272125" and stream.spec.meta["model"] == "D405"
    assert stream.spec.meta["usb"] == "3.2"
    stream._close()
    assert realsense.calls[-1] == ("stop",) and stream._pipeline is None


def test_realsense_without_a_serial_takes_whatever_is_found_and_keeps_auto_exposure(realsense):
    stream = camera(serial="")
    stream._open()
    assert realsense.calls[0][0] == "stream" and realsense.options == []
    assert stream.spec.meta["serial"] == "335122272125"  # the one it got, for the record


def test_realsense_frames_keep_only_a_host_clock_timestamp(realsense):
    stream = camera()
    stream._open()
    realsense.frames = [Frame(10, 2, value=9), None, Frame(12, 0)]
    stream._read_once()
    first = stream.latest()
    assert first.data["image"].shape == (48, 64, 3) and first.data["image"][0, 0, 0] == 9
    assert first.t_src_ns == 1_700_000_000_010 * MS and first.src_seq == 10
    stream._read_once()  # a frameset without colour: skipped
    stream._read_once()
    assert stream.latest().t_src_ns == NO_TIME  # hardware counter: not a time we can use
    assert stream.health().count == 2 and stream.health().missed == 1  # frame 11 never came


# ---- arm over zenoh ----------------------------------------------------------------------------


@pytest.fixture
def zenoh(monkeypatch):
    made = []

    class Subscriber:
        def __init__(self, **kwargs):
            self.kwargs, self.closed = kwargs, False
            made.append(self)

        def close(self):
            self.closed = True

    module(monkeypatch, "zenoh_ros2_sdk", ROS2Subscriber=Subscriber)
    return made


def arm(message="joint_state"):
    cfg = {"message": message, "topic": "/joint_states", "joints": ["joint1", "joint2"],
           "hz": 100, "router": "10.42.0.241:7447", "domain_id": 30, "required": True}
    return ArmZenohStream("arm_state", cfg, FakeClock())


def test_arm_subscribes_with_the_configured_router_and_closes(zenoh):
    stream = arm()
    stream._open()
    [subscriber] = zenoh
    assert subscriber.kwargs["topic"] == "/joint_states"
    assert subscriber.kwargs["msg_type"] == "sensor_msgs/msg/JointState"
    assert (subscriber.kwargs["router_ip"], subscriber.kwargs["router_port"]) == (
        "10.42.0.241", 7447
    )
    assert subscriber.kwargs["domain_id"] == 30
    stream._close()
    assert subscriber.closed and stream._subscriber is None


def test_arm_opens_the_sdk_session_as_a_zenoh_client(monkeypatch, zenoh):
    # A peer session receives nothing from the Robot PC container (field 2026-11-17).
    monkeypatch.setenv("ZENOH_CONFIG_OVERRIDE", "")  # setenv so the change is undone after
    arm()._open()
    assert os.environ["ZENOH_CONFIG_OVERRIDE"] == 'mode="client"'


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("", 'mode="client"'),
        ('scouting/multicast/enabled=false', 'mode="client";scouting/multicast/enabled=false'),
        ('mode="peer"', 'mode="peer"'),  # a mode the user set on purpose is kept
    ],
)
def test_client_mode_is_added_unless_a_mode_is_already_set(before, after):
    env = {"ZENOH_CONFIG_OVERRIDE": before} if before else {}
    use_client_mode(env)
    assert env["ZENOH_CONFIG_OVERRIDE"] == after


def test_arm_messages_become_samples_and_a_missing_joint_is_an_error(zenoh):
    stream = arm()
    stream._open()
    deliver = zenoh[0].kwargs["callback"]
    stamp = SimpleNamespace(sec=1_700_000_000, nanosec=5)
    deliver(SimpleNamespace(
        name=["joint2", "joint1", "gripper"], position=[0.2, 0.1, 0.9], velocity=[], effort=[],
        header=SimpleNamespace(stamp=stamp),
    ))
    sample = stream.latest()
    assert sample.data["pos"].tolist() == [0.1, 0.2]  # in the configured order
    assert sample.t_src_ns == 1_700_000_000 * 1_000_000_000 + 5
    deliver(SimpleNamespace(name=["joint1"], position=[0.1], velocity=[], effort=[],
                            header=SimpleNamespace(stamp=stamp)))
    assert stream.health().count == 1 and stream.counters()["bad_messages"] == 1
    assert stream.health().status == STATUS_ERROR and "joint2" in stream.health().message
