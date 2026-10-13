#!/usr/bin/env bash
# Show ROBOTIS's left-HX5 RViz markers and 3x3 tactile heatmaps on the User PC.
# Source the same ROS 2/RMW/Zenoh environment as the Robot PC before running.
set -eo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
rviz_config="$repo_root/robot_pc/omy_hx5_bringup/rviz/omy_hx5_left_tactile.rviz"
viz_workspace="${HX5_TACTILE_VIZ_WS:-$HOME/Projects/hx5_tactile_viz_ws}"

if ! command -v ros2 >/dev/null 2>&1 && [[ -f /opt/ros/jazzy/setup.bash ]]; then
  source /opt/ros/jazzy/setup.bash
fi
if [[ -f "$viz_workspace/install/setup.bash" ]]; then
  source "$viz_workspace/install/setup.bash"
fi
set -u

for package in robotis_hand_playground robotis_hand_description open_manipulator_description realsense2_description rviz2; do
  if ! ros2 pkg prefix "$package" >/dev/null 2>&1; then
    printf 'Missing ROS package: %s (source %s/install/setup.bash)\n' "$package" "$viz_workspace" >&2
    exit 1
  fi
done
if ! python3 -c 'import matplotlib, tkinter' >/dev/null 2>&1; then
  printf '%s\n' 'Matplotlib or Tkinter is missing from system Python.' >&2
  exit 1
fi

marker_pid=''
rviz_pid=''
heatmap_pid=''
cleanup() {
  for pid in "$marker_pid" "$rviz_pid" "$heatmap_pid"; do
    if [[ -n "$pid" ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

ros2 run robotis_hand_playground tactile_rviz \
  --ros-args -p hand_side:=left -p topic:=/left_hand/finger_pressures &
marker_pid=$!
rviz2 -d "$rviz_config" &
rviz_pid=$!
ros2 run robotis_hand_playground matplot_visualize_tactile.py \
  --ros-args -p hand_side:=left -p topic:=/left_hand/finger_pressures &
heatmap_pid=$!

wait -n "$marker_pid" "$rviz_pid" "$heatmap_pid"
