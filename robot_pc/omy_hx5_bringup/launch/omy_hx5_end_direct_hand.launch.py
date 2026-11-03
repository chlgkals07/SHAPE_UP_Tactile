"""Real OMY arm plus HX5 20-joint Direct Mode bridge through END 210.

Requires a successful `omy_hx5_end_direct_prepare --apply` beforehand.
This launch does not move the arm or hand on startup.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler, Shutdown
from launch.event_handlers import OnProcessExit
from launch.substitutions import Command, FindExecutable, LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    description = Command([
        FindExecutable(name="xacro"), " ",
        PathJoinSubstitution([
            FindPackageShare("omy_hx5_bringup"), "urdf", "omy_f3m_hx5_left.urdf.xacro"
        ]),
        " enable_arm_hardware:=true mock_arm:=false mock_hand:=false",
        " enable_end_hardware:=false",
        ' hand_mount_xyz:="', LaunchConfiguration("hand_mount_xyz"), '"',
        ' hand_mount_rpy:="', LaunchConfiguration("hand_mount_rpy"), '"',
    ])
    arm_config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "config", "arm_only_controller_manager.yaml"
    ])
    spawner = Node(
        package="controller_manager", executable="spawner",
        arguments=["joint_state_broadcaster", "arm_controller"], output="screen")
    direct = Node(
        package="omy_hx5_bringup", executable="omy_hx5_end_direct",
        arguments=["--port", LaunchConfiguration("end_port")], output="screen")

    def after_arm(event, context):
        if event.returncode:
            return [Shutdown(reason="OMY arm controller startup failed")]
        return [direct]

    def after_direct(event, context):
        return [Shutdown(reason=f"HX5 END direct bridge exited ({event.returncode})")]

    return LaunchDescription([
        DeclareLaunchArgument("end_port", default_value="/dev/ttyAMA4"),
        DeclareLaunchArgument("hand_mount_xyz", default_value="0 -0.006 0"),
        DeclareLaunchArgument("hand_mount_rpy", default_value="1.57079632679 1.57079632679 0"),
        Node(package="controller_manager", executable="ros2_control_node",
             parameters=[{"robot_description": description}, arm_config], output="screen"),
        Node(package="robot_state_publisher", executable="robot_state_publisher",
             parameters=[{"robot_description": description}], output="screen"),
        RegisterEventHandler(OnProcessExit(target_action=spawner, on_exit=after_arm)),
        RegisterEventHandler(OnProcessExit(target_action=direct, on_exit=after_direct)),
        spawner,
    ])
