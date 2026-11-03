# source 해서 쓰는 단축 함수 (User PC). ~/.bashrc에 한 줄 추가:
#   source <repo>/user_pc/scripts/leap_aliases.sh
# 바꿀 값은 셸에서 export: LEAP_ROS_DISTRO(기본 jazzy), OMY_ROBOT_IP(기본 10.42.0.241), LEAP_MANUS_WS
# LEAP_NO_ZENOH=1 : zenoh 설정을 건너뛴다 (팔 없이 Manus 단독일 때. Manus 노드 셸도 같은 설정이어야 한다)
_LEAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

# ROS + zenoh + PYTHONPATH. 이미 한 셸에서는 다시 해도 된다.
leap_env() {
  source "/opt/ros/${LEAP_ROS_DISTRO:-jazzy}/setup.bash"
  [ -n "$LEAP_MANUS_WS" ] && source "$LEAP_MANUS_WS/install/setup.bash"   # manus_ros2_msgs
  if [ -z "$LEAP_NO_ZENOH" ]; then
    export ROS_DOMAIN_ID=30 RMW_IMPLEMENTATION=rmw_zenoh_cpp
    export ZENOH_CONFIG_OVERRIDE="mode=\"client\";connect/endpoints=[\"tcp/${OMY_ROBOT_IP:-10.42.0.241}:7447\"]"
  else
    # 같은 셸에서 전에 zenoh로 leap_env를 했어도 기본 RMW로 되돌린다
    unset ROS_DOMAIN_ID RMW_IMPLEMENTATION ZENOH_CONFIG_OVERRIDE
  fi
  export PYTHONPATH="$_LEAP_DIR/src:$PYTHONPATH"
  cd "$_LEAP_DIR"
}

# 2단계: leader 그리퍼 -> LEAP. 인자는 그대로 전달 (예: leap_leader --dry-run)
leap_leader() { leap_env && python3 -m leap_teleop.cli --source leader --safe-pose fist "$@"; }
# 3~4단계: Manus -> LEAP (기본 엄지 IK, --thumb affine 으로 바꿀 수 있다)
leap_manus() { leap_env && python3 -m leap_teleop.cli --source manus --safe-pose fist "$@"; }
# 5단계: 위 + Cyclo 기록용 /leap/* 발행
leap_record() { leap_manus --publish "$@"; }
# 도구
leap_check()    { leap_env && python3 -m leap_teleop.tools.check_hardware --port /dev/ttyUSB0 "$@"; }
leap_glovecal() { leap_env && python3 -m leap_teleop.tools.calibrate_manus "$@"; }
leap_topics()   { leap_env && ros2 topic list -t | grep -E 'leap|joint_states|leader|manus'; }
