# OMY robot PC + left HX5-D20

> The real `omy_hx5_teleop.launch.py` now routes the left HX5 through END ID 210 in Direct Mode. See the [teleop sequence](../docs/hx5-d20-omy-teleop.md) and [Direct Mode preparation](../docs/hx5-d20-omy-direct-hand.md). The older `omy_hx5_hand_live.launch.py` still uses direct ID 140 access and remains blocked on this wiring. The separate Preset launch is unchanged.

[실행 명령어 모음](../docs/hx5-d20-run-commands.md)

[END 210 경유 공식 왼손 20관절 키보드 실행 순서](../docs/hx5-d20-omy-direct-hand.md)

[2026-11-03 bringup 오류와 확인 결과](../docs/field-test/2026-11-03-omy-hx5-errors.md)

[OMY 끝단에서 END 경유 Preset Mode를 시험하는 bringup 순서](../docs/hx5-d20-omy-official-bringup.md)는 별도의 `omy_hx5_official_hand.launch.py`를 사용한다. 기존 텔레옵 launch는 그대로 유지한다.

`omy_hx5_bringup` is a ROS 2 Jazzy overlay for an OMY-F3M follower with a
planned left HX5-D20 in place of the gripper. The real-mode Xacro is configured
to use the OMY END serial port `/dev/ttyAMA4` and the existing tool cable.
Field reads confirmed END 210, the HX5 controller ID 140, and the first motor
ID 141 through the installed cable. The 20-joint Direct Mode bridge is
implemented separately and still needs a live movement check.
The software does not create a separate hand PC or USB serial adapter.

## Data path

`/leader/joint_trajectory` contains `joint1..6` and `rh_r1_joint`. The arm
bridge sends only six arm joints to `/arm_controller/joint_trajectory`. The
hand bridge turns `rh_r1_joint` into a 0..1 grasp ratio and combines it with
`/left_hand/finger_pressures` and measured `/joint_states`. In real mode it
sends 20 joints to the official left-hand trajectory topic; the END Direct
node owns `/dev/ttyAMA4` and forwards goals through END 210. The arm
controller manager owns `/dev/ttyAMA2`. Mock mode retains the former
`/hand_l_controller/joint_trajectory` output. The follower hardware
description omits the gripper's `rh_r1_joint` and DYNAMIXEL ID 7.

The hand model uses the official HX5 rev2 left-hand joint and sensor
definitions: hand controller ID 140, 20 motor IDs and five tactile sensor IDs
in the 141–165 range. END board ID 210 can access the hand through its tool
path; the 20-joint Direct Mode commands still require live validation.

The official AI Worker SH5 configuration places the HX5 joint macro on its
`/dev/follower` bus and runs separate arm, hand, and pressure controllers.
OMY's END tool path has been confirmed to reach ID 140, so the real launch
uses a separate END Direct node instead of AI Worker's direct hand hardware
plugin. The available current under full hand load is still unmeasured.

## Build on the robot PC

Use the OMY ROS 2 Jazzy environment that already contains
`open_manipulator_bringup`, `open_manipulator_description`,
`dynamixel_hardware_interface`, and
`realsense2_description`. Add the hand description, pressure broadcaster,
and this package to a colcon overlay. One possible layout is:

The installed `dynamixel_hardware_interface` must also support the official
HX5 `virtual_dxl` and `virtual_sensor` definitions; a package with the same
name but older driver behavior is insufficient. Compare the Robot PC version
with the official ROBOTIS Hand Jazzy stack before physical bringup.

```bash
# Copy this branch checkout to the robot PC first and set its actual path.
export OMY_HX5_REPO="/path/to/SHAPE_UP_Tactile"
git -C "$OMY_HX5_REPO" submodule update --init third_party/robotis_hand
mkdir -p ~/omy_hx5_ws/src
ln -s "$OMY_HX5_REPO"/robot_pc/omy_hx5_bringup ~/omy_hx5_ws/src/omy_hx5_bringup
ln -s "$OMY_HX5_REPO"/third_party/robotis_hand/robotis_hand_description ~/omy_hx5_ws/src/robotis_hand_description
ln -s "$OMY_HX5_REPO"/third_party/robotis_hand/robotis_hand_pressure_broadcaster ~/omy_hx5_ws/src/robotis_hand_pressure_broadcaster
ln -s "$OMY_HX5_REPO"/third_party/robotis_hand/robotis_hand_playground ~/omy_hx5_ws/src/robotis_hand_playground
if [ ! -d ~/omy_hx5_ws/src/robotis_interfaces ]; then
  git clone --depth 1 --branch jazzy https://github.com/ROBOTIS-GIT/robotis_interfaces.git ~/omy_hx5_ws/src/robotis_interfaces
fi
source /opt/ros/jazzy/setup.bash
source /path/to/omy_ws/install/setup.bash
cd ~/omy_hx5_ws
sudo apt-get update
rosdep install --from-paths src --ignore-src --rosdistro jazzy -y
MAKEFLAGS=-j2 CMAKE_BUILD_PARALLEL_LEVEL=2 colcon build --symlink-install --parallel-workers 1 --packages-up-to omy_hx5_bringup
source install/setup.bash
```

Replace `/path/to/SHAPE_UP_Tactile` and `/path/to/omy_ws` with the robot
PC's checkout and installed OMY workspace. Check all package prefixes
with `ros2 pkg prefix PACKAGE_NAME` before building. Use the same ROS domain,
RMW, and Zenoh setup as the installed OMY system.

The five-month-old OMY image inspected on the robot contained
`dynamixel_interfaces` but no `robotis_interfaces`. The latter is a separate
official package providing `HandPressures` and `TactileSensor`; download its
Jazzy source into the overlay before building. `rosdep install` also installs
the Matplotlib dependency required by the tactile heatmap. The executable
command sheet uses the actual container paths `/root/ros2_ws` and
`/workspace/omy_ws`.

On 2026-10-13, the actual OMY SNPR44B1050 container rebuilt all five overlay
packages successfully after adding `robotis_interfaces` Jazzy commit
`7a5670cb3fb3f42b479a1fbf17c1e767b43db067` and installing the missing
Matplotlib dependency. This was a build check; no motor-control launch ran.

## Start and inspect

The launch defaults to **mocking both buses** and **disabling teleoperation**.
It can be used for a software-only check without any robot connected:

```bash
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py
ros2 control list_controllers
ros2 topic echo /left_hand/finger_pressures --once
```

### Hand-only remote keyboard at the unpack pose

`omy_hx5_hand_only.launch.py` and `omy_hx5_hand_live.launch.py` use the older
hand hardware plugin. Their mock path is useful for simulation, but their real
path is blocked because that plugin attempts to reach HX5 ID 140 directly on
`/dev/ttyAMA4`. See the [END Direct keyboard procedure](../docs/hx5-d20-omy-direct-hand.md)
for the working cable topology. Do not run it alongside another END owner.

The legacy mock hand-only launch still tests the unpack coordinator: it moves
an emulated arm from the official packed pose to zero over 10 seconds and
requires fresh measured joints before accepting keyboard input. This does not
validate physical unpacking or physical hand motion.

### Real-hardware notes

- The END 210 proxy read has confirmed HX5 controller ID 140, motor ID 141,
  and approximately 23.7 V at the hand. The Preset path moved the index finger.
  Full-load current margin and Direct Mode 20-joint motion remain unverified.
- Only one process may own `/dev/ttyAMA4`. Stop Preset, diagnostics, and any
  old bringup before starting the END Direct launch.
- The END Direct node publishes the hand's 20 measured joints and five tactile
  arrays. Check actual changes on touch and motion; topic frequency alone does
  not prove sensor or motor behavior.
- Measure leader open and closed `rh_r1_joint` positions before enabling
  [leader teleoperation](../docs/hx5-d20-omy-teleop.md). Its pressure thresholds
  are experimental raw counts.
- The separate [OMY/HX5 error record](../docs/field-test/2026-11-03-omy-hx5-errors.md)
  explains why a direct ID 140 ping failed despite successful END proxy reads.

### Tactile visualization on the User PC

The official ROBOTIS `tactile_rviz` and `matplot_visualize_tactile.py` tools
can run beside either OMY/HX5 teleop launch. They subscribe to
`/left_hand/finger_pressures` and publish **no joint commands**. Install
`robotis_hand_playground`, `rviz2`, `python3-matplotlib`, and `python3-tk` in
the User PC ROS 2 environment. Source the same ROS domain/RMW/Zenoh setup
as the Robot PC, then run:

```bash
/path/to/SHAPE_UP_Tactile/user_pc/run_hx5_tactile_viz.sh
```

The script starts official fingertip arrows/CoP markers in RViz and the
official five-finger 3×3 heatmap. Its RViz fixed frame is
`hx5_d20_left_base`, so the hand can be inspected even while the arm
controller is absent. If this package is also built on the User PC, the
equivalent launch is
`ros2 launch omy_hx5_bringup omy_hx5_tactile_view.launch.py`.
Start visualization while the fingertips are unloaded: each official tool
learns its own baseline from the first ~1 second of samples. The heatmap
shows baseline-corrected, filtered sensor counts; the arrows and CoP are
derived display cues, **not calibrated force vectors in newtons**. Mock hand
hardware publishes zero pressure, so a live mock display stays dark without
a separate synthetic pressure publisher.

With the installed leader available, measure its open and closed
`rh_r1_joint` values first. Launch the real bus path only after verifying the
4-pin pinout, voltage, current budget, tool-bus routing, mechanical adapter,
and an immediate power-off method. The default hand rotation follows the
original OMY gripper's forward direction: HX5 finger `+Z` maps to flange
`-Y`, with the palm rolled 180 degrees downward. The default `0 -0.006 0`
offset comes from the stock gripper mount;
replace `hand_mount_xyz` and, if required, `hand_mount_rpy` with the measured
adapter geometry.

```bash
read -r -p 'measured leader open rh_r1_joint: ' MEASURED_OPEN
read -r -p 'measured leader closed rh_r1_joint: ' MEASURED_CLOSED
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py \
  mock_arm:=false mock_hand:=false start_leader:=true mock_leader:=false \
  enable_arm_teleop:=true enable_hand_teleop:=true hand_dry_run:=true \
  leader_open:="$MEASURED_OPEN" leader_closed:="$MEASURED_CLOSED" \
  hand_mount_xyz:='<X Y Z>' hand_mount_rpy:='<ROLL PITCH YAW>'
```

The first run logs hand calculations but sends no hand trajectory from the
bridge. The real END Direct node checks the 20 motors and publishes hand state;
the arm controller manager has only `joint_state_broadcaster` and
`arm_controller`. Confirm `finger_l_joint1..20` states, pressure frames, and
leader endpoints. Keep the launch alive and switch `command_enabled=true`
with a released leader and unloaded open hand for a low-motion test.
`contact_threshold` and `pressure_hard_cap` launch arguments are raw
pressure-count sums, **not newtons**; their defaults are experimental. Do not
run the official tactile grasp demo at the same time as this hand bridge.

The hand bridge holds its last command when leader, pressure, or joint input
goes stale or the tracking limit is exceeded. Stopping the Python bridge does
not torque off the controller automatically. The robot's emergency stop and
power-off procedure must be available during hardware operation.

## Software verification performed

- The combined OMY/HX5 Xacro expanded in a Jazzy container with official OMY,
  ROBOTIS Hand, and RealSense descriptions. It contains two hardware systems,
  20 left-hand joints, and no gripper command joint.
- The mock launch activated the arm, hand, joint-state, and pressure
  controllers. `test/mock_teleop_probe.py` sent a synthetic seven-joint leader
  stream and observed six arm joints and a 20-joint hand trajectory. Both arm
  target postures tracked within 0.02 rad. The mock index-finger state followed
  open, half, closed, and released triggers at 0.000, 0.650, 1.300, and
  0.000 rad. The left thumb moved into opposition as it curled: joints 1/2
  reached -0.864/+0.864 rad, and joints 3/4 reached -1.200/-1.200 rad.
  The mapping follows the thumb direction and joint groups in ROBOTIS's
  `robotis_hand_teleop/hx5_d20_teleop.py`; its endpoint is reduced from the
  official keyboard `x` grip to avoid self-contact in the unloaded official
  MuJoCo scene. Each finger's joints advance in a fixed ratio under the
  0.5 rad/s speed limit. A 1.3 rad close takes at least 2.6 seconds from
  the open pose. The probe can save the state sequence with
  `--output-json`.
- Python checks cover the scalar grasp logic and official MuJoCo left-hand
  model. These checks do not verify OMY END electrical compatibility or real
  tactile calibration.
- The earlier hand-only implementation expanded to one `OMYHX5EndSystem` with 20 left-hand
  joints and no arm hardware in mock and real configurations. The mock launch
  activated only the hand, pressure, and joint-state controllers. A real
  keyboard client sent open, half, close, and release through a pseudo
  terminal; the mock index `joint6` followed 0, 0.650, 1.300, 0 rad, while
  thumb `joint1/2` reached -0.864/+0.864 rad. The state record is
  `preview/omy_hx5_hand_only_keyboard_mock_states.json`. No serial bus or
  physical hand was involved.
- The updated hand-only implementation uses two mock systems under one
  controller manager. `test/mock_unpack_hold_check.py` seeds the mock arm at
  the official packed posture, verifies motion to zero while hand commands
  are blocked, and then switches dry-run to live without restarting the arm.
  A pseudo-terminal drives the real keyboard client through open/half/close/
  release while all six arm joints remain at zero. An unrelated seven-joint
  leader stream has no effect. The readiness/fault tests cover action failure,
  stale states, posture departure, and rejection of live enable before unpack.
  Both the packed fixture and production launch passed. Records:
  `preview/omy_hx5_unpack_hold_packed_mock_states.json` and
  `preview/omy_hx5_unpack_hold_launch_mock_states.json`.
- The official `tactile_rviz` node received synthetic thumb/index taxel
  pressure on a test topic and published five left-fingertip arrow markers
  and five CoP markers; only the two touched fingers were visible. The
  official Matplotlib heatmap rendered the same 3×3 input in a headless test:
  `preview/omy_hx5_official_heatmap_synthetic.png`. Both tests use synthetic
  counts rather than physical HX5 readings.

## Official left-hand simulation tools

The `third_party/robotis_hand` Jazzy submodule supplies the official HX5-D20
rev2 left-hand URDF, Gazebo configuration, meshes, and MuJoCo MJCF. ROBOTIS's
`robotis/robotis-hand:1.0.2` Docker image supplies ROS 2 Jazzy, Gazebo Sim 8,
`gz_ros2_control`, RViz, and MoveIt. On this development PC, the standalone
official checkout is `/home/jiwoo/Projects/robotis_hand`; its `.venv` has
MuJoCo 3.12.0 installed. To recreate that Python environment:

```bash
# Use a Python installation with venv/pip support. On this development PC:
/home/jiwoo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv /home/jiwoo/Projects/robotis_hand/.venv
/home/jiwoo/Projects/robotis_hand/.venv/bin/python -m pip install 'mujoco==3.12.0'
```

The official left-hand Gazebo launch is:

```bash
cd /path/to/robotis_hand
./docker/container.sh start
./docker/container.sh enter
ros2 launch robotis_hand_bringup hx5_d20_left_gazebo.launch.py
```

For MuJoCo, load
`robotis_hand_description/mujoco/hx5_d20_rev2/scene_left.xml` with that
virtual environment's Python. The official model loaded with 20 joints and
20 actuators and stepped for 100 simulation steps on this PC. A headless
Gazebo run spawned the left-hand URDF and activated `HX5LeftSystem`,
`joint_state_broadcaster`, and `hand_l_controller`. These are standalone
hand simulation checks; they do not simulate this repository's combined OMY
and HX5 hardware bus or calibrated fingertip pressure feedback.

## Combined OMY/HX5 model preview

`preview/omy_f3m_hx5_left.urdf` is the expanded snapshot of
`urdf/omy_f3m_hx5_left.urdf.xacro`. It has 38 links, 37 joints, and two
`ros2_control` systems. The HX5 mount maps the hand's finger `+Z` to the
OMY flange's `-Y`, matching the stock gripper's forward direction, while
turning the palm downward by 180 degrees about that axis.
`preview/omy_f3m_hx5_left_mujoco.png` shows MuJoCo renders of the combined
zero-position model. For the render only, mesh visuals were used in place of
collision shapes so the displayed arm and hand match the URDF meshes. The
render is a geometry check, not a physical fit or dynamics validation.

`preview/omy_hx5_teleop_mock_states.json` records the four ROS mock joint
states, and `preview/omy_hx5_teleop_mock_replay.png` shows those states
replayed kinematically in MuJoCo. The mock pressure broadcaster supplied
zero-valued readings, so this run verifies trigger-driven motion and controller
routing, not contact force or grasp quality. The pure tactile-controller tests
cover synthetic pressure responses separately.

`preview/omy_hx5_thumb_opposition_teleop_states.json` records the updated
open/half/closed/released mock sequence. The official hand MuJoCo trigger
cycle has no self-contact at the tested commands. The comparison image
`preview/hx5_official_teleop_thumb_comparison.png` shows the prior grip,
ROBOTIS's keyboard `x` grip, and the new continuous trigger endpoint.
`preview/omy_hx5_thumb_opposition_floor_pick.gif` replays the updated OMY
floor-pick attempt. Its free-box diagnostic still does not lift the box;
these previews do not establish physical grasp performance.
