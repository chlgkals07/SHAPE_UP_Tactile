#!/usr/bin/env bash
# One-shot, hardware-free check with ROBOTIS's published left-hand Gazebo launch.
set -euo pipefail

tools_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="${tools_dir}/../src"

docker run --rm --network none \
  --env QT_QPA_PLATFORM=offscreen \
  --env LIBGL_ALWAYS_SOFTWARE=1 \
  --env RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
  --env ROS_DOMAIN_ID=230 \
  --mount "type=bind,src=${source_dir},dst=/workspace/user_pc_src,readonly" \
  --mount "type=bind,src=${tools_dir}/hx5_gazebo_probe.py,dst=/workspace/hx5_gazebo_probe.py,readonly" \
  --entrypoint /bin/bash robotis/robotis-hand:1.0.2 -c '
set -eo pipefail
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
set -u
export PYTHONPATH=/workspace/user_pc_src:${PYTHONPATH:-}
export PYTHONDONTWRITEBYTECODE=1

# The official launch also starts GUI clients. Keep its source untouched and
# run a server-only copy inside this disposable container.
sed -e "s/ -v 1/ -s -v 1/" -e "/^        rviz,$/d" \
  /root/ros2_ws/install/robotis_hand_bringup/share/robotis_hand_bringup/launch/hx5_d20_left_gazebo.launch.py \
  > /tmp/hx5_d20_left_headless.launch.py

timeout --signal=TERM --kill-after=3s 45s \
  ros2 launch /tmp/hx5_d20_left_headless.launch.py > /tmp/hx5_launch.log 2>&1 &
launch_pid=$!
cleanup() {
  kill "$launch_pid" 2>/dev/null || true
  wait "$launch_pid" 2>/dev/null || true
}
trap cleanup EXIT

sleep 8
if ! python3 /workspace/hx5_gazebo_probe.py; then
  tail -50 /tmp/hx5_launch.log
  exit 1
fi
grep -E "Configured and activated (hand_l_controller|joint_state_broadcaster)" /tmp/hx5_launch.log || true
'
