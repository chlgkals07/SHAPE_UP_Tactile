"""OMY robot-PC follower and left HX5 bringup using the existing END port.

Both hardware interfaces default to mock. Real operation requires explicit
mock_arm:=false mock_hand:=false and a verified OMY-to-HX5 installation.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    mock_arm = LaunchConfiguration("mock_arm")
    mock_hand = LaunchConfiguration("mock_hand")
    mount_xyz = LaunchConfiguration("hand_mount_xyz")
    mount_rpy = LaunchConfiguration("hand_mount_rpy")
    robot_description = Command([
        FindExecutable(name="xacro"), " ",
        PathJoinSubstitution([
            FindPackageShare("omy_hx5_bringup"), "urdf", "omy_f3m_hx5_left.urdf.xacro"
        ]),
        " mock_arm:=", mock_arm,
        " mock_hand:=", mock_hand,
        " end_port:=", LaunchConfiguration("end_port"),
        " end_tool_id:=", LaunchConfiguration("end_tool_id"),
        ' hand_mount_xyz:="', mount_xyz, '"',
        ' hand_mount_rpy:="', mount_rpy, '"',
    ])
    config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "config", "hardware_controller_manager.yaml"
    ])
    leader_launch = PathJoinSubstitution([
        FindPackageShare("open_manipulator_bringup"),
        "launch", "omy_l100_leader_ai.launch.py"
    ])
    hand_args = [
        "--side", "left",
        "--leader-open", LaunchConfiguration("leader_open"),
        "--leader-closed", LaunchConfiguration("leader_closed"),
        "--contact-threshold", LaunchConfiguration("contact_threshold"),
        "--pressure-hard-cap", LaunchConfiguration("pressure_hard_cap"),
    ]
    hand_enabled = LaunchConfiguration("enable_hand_teleop")
    return LaunchDescription([
        DeclareLaunchArgument("mock_arm", default_value="true"),
        DeclareLaunchArgument("mock_hand", default_value="true"),
        DeclareLaunchArgument("end_port", default_value="/dev/ttyAMA4"),
        DeclareLaunchArgument("end_tool_id", default_value="1"),
        DeclareLaunchArgument("hand_mount_xyz", default_value="0 -0.006 0"),
        DeclareLaunchArgument("hand_mount_rpy", default_value="1.57079632679 1.57079632679 0"),
        DeclareLaunchArgument("start_leader", default_value="false"),
        DeclareLaunchArgument("mock_leader", default_value="true"),
        DeclareLaunchArgument("enable_arm_teleop", default_value="false"),
        DeclareLaunchArgument("enable_hand_teleop", default_value="false"),
        DeclareLaunchArgument("hand_dry_run", default_value="true"),
        DeclareLaunchArgument("leader_open", default_value="nan"),
        DeclareLaunchArgument("leader_closed", default_value="nan"),
        DeclareLaunchArgument("contact_threshold", default_value="10.0"),
        DeclareLaunchArgument("pressure_hard_cap", default_value="30.0"),
        Node(
            package="controller_manager", executable="ros2_control_node",
            parameters=[{"robot_description": robot_description}, config], output="screen",
        ),
        Node(
            package="controller_manager", executable="spawner",
            arguments=["joint_state_broadcaster", "arm_controller", "hand_l_controller",
                       "pressure_l_broadcaster"], output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            parameters=[{"robot_description": robot_description}], output="screen",
        ),
        Node(
            package="omy_hx5_bringup", executable="omy_hx5_arm_bridge",
            condition=IfCondition(LaunchConfiguration("enable_arm_teleop")), output="screen",
        ),
        Node(
            package="omy_hx5_bringup", executable="omy_hx5_hand_bridge",
            arguments=hand_args + ["--dry-run"],
            condition=IfCondition(PythonExpression([
                "'", hand_enabled, "' == 'true' and '",
                LaunchConfiguration("hand_dry_run"), "' == 'true'"
            ])),
            output="screen",
        ),
        Node(
            package="omy_hx5_bringup", executable="omy_hx5_hand_bridge",
            arguments=hand_args,
            condition=IfCondition(PythonExpression([
                "'", hand_enabled, "' == 'true' and '",
                LaunchConfiguration("hand_dry_run"), "' == 'false'"
            ])),
            output="screen",
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(leader_launch),
            condition=IfCondition(LaunchConfiguration("start_leader")),
            launch_arguments={
                "use_mock_hardware": LaunchConfiguration("mock_leader"),
            }.items(),
        ),
    ])
