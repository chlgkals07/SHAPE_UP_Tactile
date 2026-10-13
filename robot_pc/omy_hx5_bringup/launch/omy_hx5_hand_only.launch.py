"""Operate only the left HX5 on OMY's END bus; never start arm hardware.

The robot arm must already be in its unpack pose. This launch neither moves
the arm to that pose nor opens its /dev/ttyAMA2 hardware interface.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    hand_dry_run = LaunchConfiguration("hand_dry_run")
    robot_description = Command([
        FindExecutable(name="xacro"), " ",
        PathJoinSubstitution([
            FindPackageShare("omy_hx5_bringup"), "urdf", "omy_f3m_hx5_left.urdf.xacro"
        ]),
        " enable_arm_hardware:=false",
        " mock_hand:=", LaunchConfiguration("mock_hand"),
        " end_port:=", LaunchConfiguration("end_port"),
        " end_tool_id:=", LaunchConfiguration("end_tool_id"),
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
    ]
    return LaunchDescription([
        DeclareLaunchArgument("mock_hand", default_value="true"),
        DeclareLaunchArgument("hand_dry_run", default_value="true"),
        DeclareLaunchArgument("end_port", default_value="/dev/ttyAMA4"),
        DeclareLaunchArgument("end_tool_id", default_value="1"),
        DeclareLaunchArgument("keyboard_topic", default_value="/hx5/keyboard_grasp_trajectory"),
        DeclareLaunchArgument("contact_threshold", default_value="10.0"),
        DeclareLaunchArgument("pressure_hard_cap", default_value="30.0"),
        Node(
            package="controller_manager", executable="ros2_control_node",
            parameters=[{"robot_description": robot_description}, config], output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            parameters=[{"robot_description": robot_description}], output="screen",
        ),
        Node(
            package="controller_manager", executable="spawner",
            arguments=["joint_state_broadcaster", "hand_l_controller", "pressure_l_broadcaster"],
            output="screen",
        ),
        Node(
            package="omy_hx5_bringup", executable="omy_hx5_hand_bridge",
            arguments=hand_args + ["--dry-run"],
            condition=IfCondition(PythonExpression(["'", hand_dry_run, "' == 'true'"])),
            output="screen",
        ),
        Node(
            package="omy_hx5_bringup", executable="omy_hx5_hand_bridge",
            arguments=hand_args,
            condition=IfCondition(PythonExpression(["'", hand_dry_run, "' == 'false'"])),
            output="screen",
        ),
    ])
