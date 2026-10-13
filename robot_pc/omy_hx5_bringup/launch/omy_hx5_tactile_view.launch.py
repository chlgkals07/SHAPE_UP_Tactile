"""Visualize left HX5 tactile data without starting any hand controller."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pressure_topic = LaunchConfiguration("pressure_topic")
    rviz_config = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "rviz", "omy_hx5_left_tactile.rviz"
    ])
    return LaunchDescription([
        DeclareLaunchArgument("pressure_topic", default_value="/left_hand/finger_pressures"),
        DeclareLaunchArgument("start_rviz", default_value="true"),
        DeclareLaunchArgument("start_heatmap", default_value="true"),
        Node(
            package="robotis_hand_playground", executable="tactile_rviz",
            name="omy_hx5_left_tactile_markers", output="screen",
            parameters=[{"hand_side": "left", "topic": pressure_topic,
                         "marker_topic": "/tactile_force_markers"}],
        ),
        Node(
            package="rviz2", executable="rviz2", arguments=["-d", rviz_config],
            condition=IfCondition(LaunchConfiguration("start_rviz")), output="screen",
        ),
        Node(
            package="robotis_hand_playground", executable="matplot_visualize_tactile.py",
            name="omy_hx5_left_tactile_heatmap", output="screen",
            parameters=[{"hand_side": "left", "topic": pressure_topic}],
            condition=IfCondition(LaunchConfiguration("start_heatmap")),
        ),
    ])
