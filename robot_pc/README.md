# OMY robot PC + left HX5-D20

[실행 명령어 모음](../docs/hx5-d20-run-commands.md)

`omy_hx5_bringup` is a ROS 2 Jazzy overlay for an OMY-F3M follower with a
planned left HX5-D20 in place of the gripper. The real-mode Xacro is configured
to use the OMY END serial port `/dev/ttyAMA4` and the existing tool cable.
Whether that cable provides a compatible electrical supply and a transparent
RS-485 path to HX5 controller ID 140 has **not** been established on OMY.
The software does not create a separate hand PC or USB serial adapter.

## Data path

`/leader/joint_trajectory` contains `joint1..6` and `rh_r1_joint`. The arm
bridge sends only six arm joints to `/arm_controller/joint_trajectory`. The
hand bridge turns `rh_r1_joint` into a 0..1 grasp ratio, combines it with
`/left_hand/finger_pressures` and measured `/joint_states`, then sends one
20-joint trajectory to `/hand_l_controller/joint_trajectory`. The controller
manager is configured to own `/dev/ttyAMA2` for the arm and `/dev/ttyAMA4`
for the END board and proposed HX5 path. The gripper's `rh_r1_joint` and DYNAMIXEL ID 7 are absent from the
follower hardware description.

The hand controller uses the official HX5 rev2 left-hand joint and sensor
definitions: hand controller ID 140, 20 virtual motor IDs and five tactile
sensor IDs in the 141–165 range. The OMY END board keeps its stock ID 210 and Tool ID 1 setting by
default; `end_tool_id` is an override after its required value is confirmed.
Whether the END tool path actually passes ID 140 to this hand remains a
physical integration check; mock mode cannot establish it.

The official AI Worker SH5 configuration places the HX5 joint macro on its
`/dev/follower` bus and runs separate arm, hand, and pressure controllers.
This overlay reuses the same left-hand macro and controller interfaces, but
OMY's stock END configuration talks to its gripper as virtual ID 7 through
END board `comm_id=210`. The HX5 macro instead requires a real bus response
from controller ID 140. Copying AI Worker's hand macro does not prove that
OMY's END board forwards packets to ID 140 or supplies enough current.

## Build on the robot PC

Use the OMY ROS 2 Jazzy environment that already contains
`open_manipulator_bringup`, `open_manipulator_description`,
`dynamixel_hardware_interface`, `robotis_interfaces`, and
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
source /opt/ros/jazzy/setup.bash
source /path/to/omy_ws/install/setup.bash
cd ~/omy_hx5_ws
colcon build --packages-up-to omy_hx5_bringup
source install/setup.bash
```

Replace `/path/to/SHAPE_UP_Tactile` and `/path/to/omy_ws` with the robot
PC's checkout and installed OMY workspace. Check all package prefixes
with `ros2 pkg prefix PACKAGE_NAME` before building. Use the same ROS domain,
RMW, and Zenoh setup as the installed OMY system.

## Start and inspect

The launch defaults to **mocking both buses** and **disabling teleoperation**.
It can be used for a software-only check without any robot connected:

```bash
ros2 launch omy_hx5_bringup omy_hx5_teleop.launch.py
ros2 control list_controllers
ros2 topic echo /left_hand/finger_pressures --once
```

### Hand-only remote keyboard at the unpack pose

`omy_hx5_hand_only.launch.py` moves the arm to ROBOTIS's unpack posture and
keeps its controller active while only the hand is teleoperated. One controller
manager owns `OMYF3MSystem` on `/dev/ttyAMA2` and `OMYHX5EndSystem` on
`/dev/ttyAMA4`. No leader process or arm teleoperation bridge starts.

The unpack coordinator accepts the official packed posture
`[0, 0, -2.61799, -0.52360, 0, 0]` or an already unpacked arm, then sends
`[0, 0, 0, 0, 0, 0]` to `/arm_controller/follow_joint_trajectory` over 10 seconds.
It requires action success and fresh measured joints within 0.01 rad of the
target for 0.5 seconds before publishing `/hx5/arm_unpack_ready=true`.
The hand bridge waits for this heartbeat before collecting its tactile baseline
or commanding. If the action fails, joint states go stale, or the arm departs
from the held posture by more than 0.05 rad, readiness is latched false.

On the Robot PC, start with the default mock arm/hand and dry-run bridge:

```bash
ros2 launch omy_hx5_bringup omy_hx5_hand_only.launch.py
ros2 control list_controllers
ros2 control list_hardware_components
```

The expected active controllers are `joint_state_broadcaster`, `arm_controller`,
`hand_l_controller`, and `pressure_l_broadcaster`. To exercise the mock hand,
set `hand_dry_run:=false`. `mock_arm` and `mock_hand` must both be true for
simulation or both false for physical operation; mixed modes are rejected.
For a physical connection, first verify the END cable pinout, voltage,
current budget, termination, ID 140 packet routing, Tool ID behavior, and
hand mount. The real hardware plugin pings, reboots, configures, and may enable
torque during initialization. `hand_dry_run:=true` only stops the Python bridge
from publishing trajectories; it does **not** make hardware initialization
read-only or torque-free. After the electrical and bus path are confirmed, run
`mock_arm:=false mock_hand:=false hand_dry_run:=true`: **the real arm moves to
unpack even though the hand bridge is dry-run**. Inspect all 26 joint states,
five pressure sensors, and the driver communication state. The Xacro's real mode selects
`dynamixel_hardware_interface/DynamixelHardware` on `/dev/ttyAMA4`; that
software setting does not establish physical END-to-HX5 compatibility.
After the dry run, keep the same launch alive to preserve arm torque. On the
User PC keyboard, press `z` and keep the client running with the hand unloaded
and near open. From another sourced Robot PC terminal, enable hand commands:

```bash
ros2 topic echo /hx5/arm_unpack_ready --once
ros2 param set /hx5_left_omy_teleop command_enabled true
```

This switch rejects an unready arm, stale inputs, a closed keyboard request,
or a hand away from open. It discards calculated dry-run targets and collects
a new tactile baseline before sending commands seeded from measured joints.
`command_enabled=false` stops new hand trajectories while the arm continues
holding. Closing the keyboard does not stop the arm controller. Stopping the
whole launch can torque off the arm; support it before shutting down.
Do not run this launch alongside the full OMY/HX5 launch or another command
publisher for the same hand controller.

### Real-hardware audit points

- The first blocking check is electrical: identify the actual four-pin
  connector, polarity, supply voltage/current limit, RS-485 pair, and HX5
  termination before applying power. AI Worker's published four-pin swap is
  specific to its wiring and cannot certify OMY's connector.
- The next blocking check is bus reachability. The driver opens
  `/dev/ttyAMA4` at 4 Mbps and pings HX5 controller ID 140 directly. OMY's
  original gripper was virtual ID 7 under END ID 210; END `Tool ID=1` and
  its SyncTable settings have not been demonstrated to route HX5 packets.
  The HX5 macro appears before the END GPIO in this Xacro, so the inspected
  driver pings ID 140 before it initializes ID 210. If END routing needs its
  settings applied first, this order is another startup failure path. If ID
  140 cannot answer, hardware initialization fails before a hand controller
  can be activated. Do not change `Tool ID` by guesswork.
- Check the Robot PC's installed driver for `virtual_dxl` and
  `virtual_sensor` support, all required ROS packages, and exclusive access
  to the END serial device. A second OMY bringup process must not open the
  same port.
- After communication is established, inspect ID 140 status, all 20
  measured joints, and each of the five 3×3 tactile arrays while touching
  one finger at a time. A broadcaster can publish fresh timestamps around
  unchanged or invalid hardware values, so topic frequency alone does not
  prove tactile feedback. The grasp thresholds are experimental raw counts.
- The hand-only launch moves the arm once and then holds it. Do not run the
  original `omy_3m_unpack.launch.py` alongside it: that launch also owns the
  END port and a controller manager. For the full seven-joint leader path, measure the actual open and
  closed `rh_r1_joint` values and confirm that the robot uses the same ROS
  domain, RMW, and Zenoh transport as the leader.

### Read-only ID 140 ping on the Robot PC

Only do this **after** confirming the exact OMY four-pin pinout, polarity,
voltage, and current capacity for the HX5. Keep the hand clear of objects and
stop every OMY/HX5 `ros2_control` bringup that might own `/dev/ttyAMA4`.
Do not use `mock_hand:=false` as a ping test: that launch reboots, configures,
and activates hardware. This check uses the official DYNAMIXEL SDK's Protocol
2.0 `ping`, which requests an ID/model response without sending a joint goal.

The Python SDK is not installed in the `robotis/robotis-hand:1.0.2` image by
default. On the Robot PC, prepare an isolated Python environment once:

```bash
python3 -m venv ~/omy-hx5-ping-venv
~/omy-hx5-ping-venv/bin/python -m pip install 'dynamixel-sdk==4.1.0'
```

If `venv` reports `ensurepip is not available` on an Ubuntu host, run
`sudo apt-get install python3-venv` and retry the first command. Inside a
root-owned Docker container, use `apt-get install python3-venv` instead.

With the verified electrical connection powered and the serial port free,
run this from the Robot PC terminal. It checks END ID 210 for comparison and
then HX5 controller ID 140; the latter is the required result:

```bash
~/omy-hx5-ping-venv/bin/python - <<'PY'
from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler

port = PortHandler('/dev/ttyAMA4')
packet = PacketHandler(2.0)
try:
    if not port.openPort():
        raise SystemExit('Cannot open /dev/ttyAMA4; check path, permissions, and other owners')
except OSError as exc:
    raise SystemExit(f'Cannot open /dev/ttyAMA4: {exc}') from None

hand_replied = False
try:
    if not port.setBaudRate(4_000_000):
        raise SystemExit('Cannot set /dev/ttyAMA4 to 4 Mbps')
    for device_id in (210, 140):
        model, result, error = packet.ping(port, device_id)
        if result != COMM_SUCCESS:
            print(f'ID {device_id}: no reply: {packet.getTxRxResult(result)}')
        elif error:
            print(f'ID {device_id}: device error: {packet.getRxPacketError(error)}')
        else:
            print(f'ID {device_id}: ping OK, model number {model}')
            if device_id == 140:
                hand_replied = True
except OSError as exc:
    raise SystemExit(f'Serial communication failed: {exc}') from None
finally:
    port.closePort()

if not hand_replied:
    raise SystemExit('HX5 ID 140 did not reply; do not start real hand bringup')
PY
```

`ID 140: ping OK` establishes only that this serial path reaches the hand
controller at 4 Mbps. It does not validate supply current, motor torque,
tactile data, or safe motion. If ID 210 replies but ID 140 does not, the END
board is reachable while the hand path remains unresolved. If neither replies,
check the selected port, permissions, power, and baud rate before changing any
IDs or Tool settings. The current [ROBOTIS SDK ping example](https://github.com/ROBOTIS-GIT/DynamixelSDK/blob/main/python/tests/protocol2_0/ping.py)
uses the same `PortHandler` and `PacketHandler(2.0)` calls.

On the remote User PC, source ROS 2 Jazzy, use the same ROS domain/RMW/Zenoh
connection as the Robot PC, then run:

```bash
python3 /path/to/SHAPE_UP_Tactile/user_pc/omy_hx5_keyboard.py
```

The remote keyboard publishes only `rh_r1_joint=0..1` on
`/hx5/keyboard_grasp_trajectory`; it does not publish six arm angles. Like
ROBOTIS's official Hand keyboard, `x` requests all-close and `z` requests
all-open. `]` increases closure and `[` decreases it by 10% per press;
`--step` changes that fraction. For initial physical motion, use the small
incremental keys. Press `z` and wait for the hand to reach open before
`ESC` exits. The client republishes its target at 20 Hz so the hand bridge's
leader timeout does not interrupt a commanded motion. Losing the client holds
the last hand target; quitting does not torque off the hand.

The Robot PC bridge still waits for an unloaded open-hand tactile baseline
and measured hand joints before it publishes a command. Its pressure limits
use raw sensor counts and are not calibrated grasp forces.

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
bridge; the real hardware plugin still performs its initialization writes. Confirm
the active controllers, `finger_l_joint1..20` states, pressure frames, and
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
