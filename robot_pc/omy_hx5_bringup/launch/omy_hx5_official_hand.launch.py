"""Bring up OMY and its left HX5 without startup motion.

Mock mode uses the vendor hand controllers. Real mode keeps the arm in
ros2_control and reaches the hand in Preset Mode through END ID 210.
"""

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
    Shutdown,
)
from launch.conditions import IfCondition, UnlessCondition
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
        " enable_end_hardware:=", LaunchConfiguration("mock_hand"),
        " end_port:=", LaunchConfiguration("end_port"),
        " end_tool_id:=", LaunchConfiguration("end_tool_id"),
        ' hand_mount_xyz:="', LaunchConfiguration("hand_mount_xyz"), '"',
        ' hand_mount_rpy:="', LaunchConfiguration("hand_mount_rpy"), '"',
    ])
    mock_controller_config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "config",
        "omy_official_hand_controller_manager.yaml",
    ])
    arm_controller_config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "config",
        "arm_only_controller_manager.yaml",
    ])
    official_initial_positions = PathJoinSubstitution([
        FindPackageShare("robotis_hand_bringup"), "config", "hx5_d20",
        "hx5_d20_left_initial_positions.yaml",
    ])

    # The vendor's 20-joint controllers are available only in mock mode.
    # In real Preset Mode, END 210 owns the hand bus via end_preset instead.
    mock_spawner = Node(
        package="controller_manager", executable="spawner",
        arguments=[
            "--controller-ros-args",
            "-r /hand_l_controller/joint_trajectory:="
            "/leader/joint_trajectory_command_broadcaster_left_hand/joint_trajectory",
            "joint_state_broadcaster", "arm_controller", "hand_l_controller",
            "effort_l_controller", "pressure_l_broadcaster",
        ],
        output="screen",
        condition=IfCondition(LaunchConfiguration("mock_hand")),
    )
    real_spawner = Node(
        package="controller_manager", executable="spawner",
        arguments=["joint_state_broadcaster", "arm_controller"],
        output="screen",
        condition=UnlessCondition(LaunchConfiguration("mock_hand")),
    )
    end_preset = Node(
        package="omy_hx5_bringup", executable="omy_hx5_end_preset",
        arguments=["--port", LaunchConfiguration("end_port")],
        output="screen",
        condition=UnlessCondition(LaunchConfiguration("mock_hand")),
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
            return [Shutdown(reason="mock hand controller startup failed")]
        return [official_current, initial_position]

    def after_arm_controllers(event, context):
        if event.returncode != 0:
            return [Shutdown(reason="OMY arm controller startup failed")]
        return [end_preset]

    def after_end_preset(event, context):
        if event.returncode != 0:
            get_logger("omy_hx5_official_hand").error(
                "END 210 / HX5 140 preset bridge exited with an error")
        return [Shutdown(reason="END preset bridge exited")]

    def validate_hardware(context):
        arm = LaunchConfiguration("mock_arm").perform(context).lower()
        hand = LaunchConfiguration("mock_hand").perform(context).lower()
        if arm not in ("true", "false") or hand not in ("true", "false") or arm != hand:
            raise RuntimeError(
                "Use mock_arm:=true mock_hand:=true, or mock_arm:=false mock_hand:=false")
        if arm == "false":
            if (LaunchConfiguration("init_position").perform(context).lower() != "false"
                    or LaunchConfiguration("apply_official_current").perform(context).lower()
                    != "false"):
                raise RuntimeError(
                    "Real END preset mode requires init_position:=false and "
                    "apply_official_current:=false; vendor joint/current commands "
                    "require direct-control mode")
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
            parameters=[{"robot_description": robot_description}, mock_controller_config],
            condition=IfCondition(LaunchConfiguration("mock_hand")),
            output="screen",
        ),
        Node(
            package="controller_manager", executable="ros2_control_node",
            parameters=[{"robot_description": robot_description}, arm_controller_config],
            condition=UnlessCondition(LaunchConfiguration("mock_hand")),
            output="screen",
        ),
        Node(
            package="robot_state_publisher", executable="robot_state_publisher",
            parameters=[{"robot_description": robot_description}], output="screen",
        ),
        RegisterEventHandler(OnProcessExit(
            target_action=mock_spawner, on_exit=after_controllers)),
        RegisterEventHandler(OnProcessExit(
            target_action=real_spawner, on_exit=after_arm_controllers)),
        RegisterEventHandler(OnProcessExit(
            target_action=end_preset, on_exit=after_end_preset)),
        mock_spawner,
        real_spawner,
    ])
