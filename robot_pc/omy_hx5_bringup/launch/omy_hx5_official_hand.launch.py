"""Bring up the vendor left-hand controllers on OMY's END bus before teleop.

The vendor standalone launch assumes a USB adapter and owns its serial port.
This launch uses the combined OMY/HX5 description so the arm power path, END
board and hand are managed by one controller manager. It starts no OMY teleop
bridge and makes the vendor's initial motion/current command opt-in.
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.logging import get_logger
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    robot_description = Command([
        FindExecutable(name="xacro"), " ",
        PathJoinSubstitution([
            FindPackageShare("omy_hx5_bringup"), "urdf", "omy_f3m_hx5_left.urdf.xacro"
        ]),
        " enable_arm_hardware:=true",
        " mock_arm:=", LaunchConfiguration("mock_arm"),
        " mock_hand:=", LaunchConfiguration("mock_hand"),
        " end_port:=", LaunchConfiguration("end_port"),
        " end_tool_id:=", LaunchConfiguration("end_tool_id"),
        ' hand_mount_xyz:="', LaunchConfiguration("hand_mount_xyz"), '"',
        ' hand_mount_rpy:="', LaunchConfiguration("hand_mount_rpy"), '"',
    ])
    controller_config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "config",
        "omy_official_hand_controller_manager.yaml",
    ])
    official_initial_positions = PathJoinSubstitution([
        FindPackageShare("robotis_hand_bringup"), "config", "hx5_d20",
        "hx5_d20_left_initial_positions.yaml",
    ])

    # Keep the official hand controller's input topic so ROBOTIS's keyboard
    # and example-motion nodes work without modification. This launch must
    # never run alongside the OMY teleop or standalone hand bringup.
    spawner = Node(
        package="controller_manager", executable="spawner",
        arguments=[
            "--controller-ros-args",
            "-r /hand_l_controller/joint_trajectory:="
            "/leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory",
            "joint_state_broadcaster", "arm_controller", "hand_l_controller",
            "effort_l_controller", "pressure_l_broadcaster",
        ],
        output="screen",
    )
    initial_position = Node(
        package="robotis_hand_bringup", executable="joint_trajectory_executor",
        parameters=[official_initial_positions], output="screen",
        condition=IfCondition(LaunchConfiguration("init_position")),
    )
    official_current = ExecuteProcess(
        cmd=[
            "ros2", "topic", "pub", "-r", "50", "-t", "50", "-p", "50",
            "/effort_l_controller/commands", "std_msgs/msg/Float64MultiArray",
            "data: [" + ", ".join(["300.0"] * 20) + "]",
        ],
        output="screen",
        condition=IfCondition(LaunchConfiguration("apply_official_current")),
    )

    def after_controllers(event, context):
        if event.returncode != 0:
            get_logger("omy_hx5_official_hand").error(
                "Controller startup failed; official initial motion/current not started")
            return []
        return [official_current, initial_position]

    def validate_hardware(context):
        arm = LaunchConfiguration("mock_arm").perform(context).lower()
        hand = LaunchConfiguration("mock_hand").perform(context).lower()
        if arm not in ("true", "false") or hand not in ("true", "false") or arm != hand:
            raise RuntimeError(
                "Use mock_arm:=true mock_hand:=true, or mock_arm:=false mock_hand:=false")
        if arm == "false":
            raise RuntimeError(
                "The official direct-ID hand driver cannot reach ID 140 behind "
                "OMY END ID 210. Use omy_hx5_end_proxy_probe first; physical "
                "motion is blocked until an END proxy control path is verified.")
        return []

    return LaunchDescription([
        DeclareLaunchArgument("mock_arm", default_value="true"),
        DeclareLaunchArgument("mock_hand", default_value="true"),
        DeclareLaunchArgument("end_port", default_value="/dev/ttyAMA4"),
        DeclareLaunchArgument("end_tool_id", default_value="1"),
        DeclareLaunchArgument("hand_mount_xyz", default_value="0 -0.006 0"),
        DeclareLaunchArgument("hand_mount_rpy", default_value="1.57079632679 1.57079632679 0"),
        DeclareLaunchArgument("init_position", default_value="false"),
        DeclareLaunchArgument("apply_official_current", default_value="false"),
        OpaqueFunction(function=validate_hardware),
        Node(
            package="controller_manager", executable="ros2_control_node",
            parameters=[{"robot_description": robot_description}, controller_config],
            output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            parameters=[{"robot_description": robot_description}], output="screen",
        ),
        RegisterEventHandler(OnProcessExit(
            target_action=spawner, on_exit=after_controllers)),
        spawner,
    ])
