#!/usr/bin/env bash
# Run the HX5 ROS bridge with ROBOTIS' published ROS 2 Jazzy image.
# This script does not start hand hardware or change host udev/X11 settings.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
docker_args=(
  --rm
  --network host
  --ipc host
  --mount "type=bind,src=${script_dir}/src,dst=/workspace/user_pc_src,readonly"
  --env "ROS_DOMAIN_ID=${ROS_DOMAIN_ID:-30}"
  --env "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-rmw_zenoh_cpp}"
)
if [[ -n "${ZENOH_CONFIG_OVERRIDE:-}" ]]; then
  docker_args+=(--env ZENOH_CONFIG_OVERRIDE)
fi

exec docker run "${docker_args[@]}" --entrypoint /bin/bash \
  robotis/robotis-hand:1.0.2 \
  -c 'source /opt/ros/jazzy/setup.bash && source /root/ros2_ws/install/setup.bash && export PYTHONPATH=/workspace/user_pc_src:${PYTHONPATH:-} && exec python3 -m hx5_teleop.cli "$@"' \
  hx5-teleop "$@"
