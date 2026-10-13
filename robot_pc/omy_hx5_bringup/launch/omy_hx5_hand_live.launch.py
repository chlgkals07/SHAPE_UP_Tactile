"""Run the physical OMY arm and left HX5 hand with live keyboard commands.

The included hand-only launch moves the arm to unpack and keeps it there.
Hand trajectories start only after the arm is ready, measured hand joints and
fresh tactile frames arrive, and the keyboard requests an open hand baseline.
"""

from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    hand_only = PathJoinSubstitution([
        FindPackageShare("omy_hx5_bringup"), "launch", "omy_hx5_hand_only.launch.py"
    ])
    return LaunchDescription([
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(hand_only),
            launch_arguments={
                "mock_arm": "false",
                "mock_hand": "false",
                "hand_dry_run": "false",
            }.items(),
        ),
    ])
