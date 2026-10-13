"""Unpack and hold the OMY arm, then teleoperate only the left HX5.

One controller manager owns the arm and END bus. No leader or arm teleoperation
bridge starts. Real mode moves the arm once, even when hand_dry_run is true.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction, RegisterEventHandler
from launch.logging import get_logger
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    hand_dry_run = LaunchConfiguration("hand_dry_run")
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
    config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "config", "hand_only_controller_manager.yaml"
    ])
    hand_args = [
        "--side", "left",
        "--leader-topic", LaunchConfiguration("keyboard_topic"),
        "--leader-open", "0.0",
        "--leader-closed", "1.0",
        "--contact-threshold", LaunchConfiguration("contact_threshold"),
        "--pressure-hard-cap", LaunchConfiguration("pressure_hard_cap"),
        "--arm-ready-topic", "/hx5/arm_unpack_ready",
    ]
    spawner = Node(
        package="controller_manager", executable="spawner",
        arguments=["joint_state_broadcaster", "arm_controller", "hand_l_controller",
                   "pressure_l_broadcaster"], output="screen",
    )
    unpack = Node(
        package="omy_hx5_bringup", executable="omy_hx5_unpack_and_hold",
        parameters=[{
            "unpack_duration": ParameterValue(LaunchConfiguration("arm_unpack_duration"),
                                              value_type=float),
        }], output="screen",
    )
    hand_dry = Node(
        package="omy_hx5_bringup", executable="omy_hx5_hand_bridge",
        arguments=hand_args + ["--dry-run"],
        condition=IfCondition(PythonExpression(["'", hand_dry_run, "' == 'true'"])),
        output="screen",
    )
    hand_live = Node(
        package="omy_hx5_bringup", executable="omy_hx5_hand_bridge",
        arguments=hand_args,
        condition=IfCondition(PythonExpression(["'", hand_dry_run, "' == 'false'"])),
        output="screen",
    )

    def after_controllers(event, context):
        if event.returncode != 0:
            get_logger("omy_hx5_hand_only").error(
                "Controller startup failed; unpack and hand bridge not started")
            return []
        return [unpack, hand_dry, hand_live]

    def validate_hardware(context):
        arm = LaunchConfiguration("mock_arm").perform(context).lower()
        hand = LaunchConfiguration("mock_hand").perform(context).lower()
        if arm not in ("true", "false") or hand not in ("true", "false") or arm != hand:
            raise RuntimeError("Use mock_arm:=true mock_hand:=true for simulation, or "
                               "mock_arm:=false mock_hand:=false for physical unpack/hold")
        return []

    return LaunchDescription([
        DeclareLaunchArgument("mock_arm", default_value="true"),
        DeclareLaunchArgument("mock_hand", default_value="true"),
        DeclareLaunchArgument("hand_dry_run", default_value="true"),
        DeclareLaunchArgument("arm_unpack_duration", default_value="10.0"),
        DeclareLaunchArgument("end_port", default_value="/dev/ttyAMA4"),
        DeclareLaunchArgument("end_tool_id", default_value="1"),
        DeclareLaunchArgument("hand_mount_xyz", default_value="0 -0.006 0"),
        DeclareLaunchArgument("hand_mount_rpy", default_value="1.57079632679 1.57079632679 0"),
        DeclareLaunchArgument("keyboard_topic", default_value="/hx5/keyboard_grasp_trajectory"),
        DeclareLaunchArgument("contact_threshold", default_value="10.0"),
        DeclareLaunchArgument("pressure_hard_cap", default_value="30.0"),
        OpaqueFunction(function=validate_hardware),
        Node(
            package="controller_manager", executable="ros2_control_node",
            parameters=[{"robot_description": robot_description}, config], output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            parameters=[{"robot_description": robot_description}], output="screen",
        ),
        RegisterEventHandler(OnProcessExit(target_action=spawner,
                                          on_exit=after_controllers)),
        spawner,
    ])
