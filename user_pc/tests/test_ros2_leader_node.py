"""Ros2LeaderSource against a fake rclpy: lifecycle and stop behaviour without ROS installed."""

import sys
import threading
import types
from types import SimpleNamespace

import pytest

from leap_teleop.config import LeaderGripperConfig

CFG = LeaderGripperConfig("/leader/joint_trajectory", "rh_r1_joint", 0.0, 1.0)


class FakeNode:
    def __init__(self, events):
        self.events = events
        self.callback = None

    def create_subscription(self, msg_type, topic, callback, qos):
        self.callback = callback

    def destroy_node(self):
        self.events.append("destroy_node")


class FakeExecutor:
    def __init__(self, events):
        self.events = events
        self._stop = threading.Event()

    def add_node(self, node):
        pass

    def spin(self):
        self._stop.wait(timeout=5.0)

    def shutdown(self):
        self.events.append("executor_shutdown")
        self._stop.set()


@pytest.fixture
def fake_rclpy(monkeypatch):
    events = []
    state = {"ok": False, "node": None, "shutdown_raises": False}

    rclpy = types.ModuleType("rclpy")
    rclpy.ok = lambda: state["ok"]

    def init():
        state["ok"] = True

    def shutdown():
        events.append("rclpy_shutdown")
        state["ok"] = False
        if state["shutdown_raises"]:
            raise RuntimeError("rcl_shutdown already called on the given context")

    def create_node(name):
        state["node"] = FakeNode(events)
        return state["node"]

    rclpy.init, rclpy.shutdown, rclpy.create_node = init, shutdown, create_node

    executors = types.ModuleType("rclpy.executors")
    executors.SingleThreadedExecutor = lambda: FakeExecutor(events)
    qos = types.ModuleType("rclpy.qos")
    qos.qos_profile_sensor_data = object()
    trajectory_msgs = types.ModuleType("trajectory_msgs")
    trajectory_msgs_msg = types.ModuleType("trajectory_msgs.msg")
    trajectory_msgs_msg.JointTrajectory = object

    for name, module in {
        "rclpy": rclpy,
        "rclpy.executors": executors,
        "rclpy.qos": qos,
        "trajectory_msgs": trajectory_msgs,
        "trajectory_msgs.msg": trajectory_msgs_msg,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)
    return SimpleNamespace(events=events, state=state)


def make_source(fake_rclpy):
    from leap_teleop.sources.ros2_leader import Ros2LeaderSource

    return Ros2LeaderSource(CFG, clock=lambda: 42.0)


def test_stop_is_requested_once_rclpy_shuts_down(fake_rclpy):
    source = make_source(fake_rclpy)
    assert not source.stop_requested
    fake_rclpy.state["ok"] = False  # what rclpy's own SIGINT handler does
    assert source.stop_requested
    source.close()


def test_incoming_message_becomes_a_timestamped_reading(fake_rclpy):
    source = make_source(fake_rclpy)
    assert source.poll(0.0) is None
    msg = SimpleNamespace(
        joint_names=["joint1", "rh_r1_joint"],
        points=[SimpleNamespace(positions=[0.0, 0.25])],
    )
    fake_rclpy.state["node"].callback(msg)
    reading = source.poll(1.0)
    assert reading.grasp == pytest.approx(0.25)
    assert reading.timestamp == 42.0
    source.close()


def test_close_shuts_down_executor_before_destroying_node_and_context(fake_rclpy):
    source = make_source(fake_rclpy)
    source.close()
    assert fake_rclpy.events == ["executor_shutdown", "destroy_node", "rclpy_shutdown"]


def test_close_survives_rclpy_having_already_shut_down_after_sigint(fake_rclpy):
    source = make_source(fake_rclpy)
    fake_rclpy.state["shutdown_raises"] = True
    source.close()  # must not raise; the hand driver still has to be closed afterwards
    assert fake_rclpy.events == ["executor_shutdown", "destroy_node", "rclpy_shutdown"]
