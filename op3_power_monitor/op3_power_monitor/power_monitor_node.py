#!/usr/bin/env python3
# Copyright 2024 OP3 Developer
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
OP3 Power Monitor Node
======================
Subscribes passively to existing ROBOTIS OP3 ROS2 topics to track and
report voltage and current from every component in the system.

Based on the official ROBOTIS OP3 Framework Architecture (Read-Write Tutorial):
  /robotis/present_joint_states  -> published by robotis_controller inside op3_manager
  /robotis/status                -> published by open_cr_module (voltage text)
  /robotis/open_cr/button        -> published by open_cr_module (button events)

Subscribed Topics
-----------------
/robotis/status                 (robotis_controller_msgs/StatusMsg)
    Parses battery voltage from text, e.g. "Present Volt : 11.5V"

/robotis/present_joint_states   (sensor_msgs/JointState)
    Reads position[], velocity[], effort[] per joint.

    NOTE on effort[]:
    According to the official OP3 Read-Write Tutorial, the framework
    publishes "present_effort" which comes from the 'present_current_item_name'
    register. In the DEFAULT OP3.robot config, only 'present_position' is
    listed as a bulkread item — so effort[] will be 0 unless you add
    'present_current' to each joint's BULK READ ITEMS in OP3.robot.

    To enable real current reading, change in OP3.robot:
      present_position, position_p_gain, ...
    to:
      present_position, present_current, position_p_gain, ...
    then rebuild op3_manager.

/robotis/open_cr/button         (std_msgs/String)
    Listens for button presses from OpenCR. Logged for awareness.

Published Topics
----------------
/op3/power/battery_voltage      (std_msgs/Float32)   — Volts
/op3/power/battery_status       (std_msgs/String)    — "OK" | "LOW" | "CRITICAL" | "UNKNOWN"
/op3/power/joint_loads          (sensor_msgs/JointState) — effort/current per joint
/op3/power/summary              (std_msgs/String)    — JSON snapshot at 1 Hz

Usage
-----
    # Requires op3_manager to be running (as shown in official OP3 launch files)
    ros2 launch op3_read_write_demo op3_read_write.launch.xml
    # Then in another terminal:
    ros2 run op3_power_monitor power_monitor_node

    # Or test without hardware:
    ros2 topic pub --once /robotis/status robotis_controller_msgs/msg/StatusMsg \\
      "{type: 1, module_name: 'SENSOR', status_msg: 'Present Volt : 11.5V'}"
"""

import json
import math
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy

from std_msgs.msg import Float32, Float32MultiArray, String
from sensor_msgs.msg import JointState
from robotis_controller_msgs.msg import StatusMsg


# ---------------------------------------------------------------------------
# Constants — from OP3.robot and Dynamixel XM430-W350 e-manual
# ---------------------------------------------------------------------------

# Joint names exactly as defined in OP3.robot (20 Dynamixel XM430-W350)
OP3_JOINT_NAMES: List[str] = [
    'r_sho_pitch', 'l_sho_pitch',
    'r_sho_roll',  'l_sho_roll',
    'r_el',        'l_el',
    'r_hip_yaw',   'l_hip_yaw',
    'r_hip_roll',  'l_hip_roll',
    'r_hip_pitch', 'l_hip_pitch',
    'r_knee',      'l_knee',
    'r_ank_pitch', 'l_ank_pitch',
    'r_ank_roll',  'l_ank_roll',
    'head_pan',    'head_tilt',
]

# XM430-W350: current conversion factor from Dynamixel e-manual
# 1 unit = 2.69 mA. Only valid when present_current is in bulk-read items.
XM430_CURRENT_UNIT_A: float = 0.00269  # A per raw unit

# XM430-W350: present_input_voltage register (address 144)
# 1 unit = 0.1V. Range: 9.5V ~ 16.0V (from control table)
XM430_VOLTAGE_UNIT_V: float = 0.1  # V per raw unit

# XM430-W350: nominal operating voltage
XM430_NOMINAL_VOLTAGE_V: float = 12.0

# Estimated voltage drop per servo from battery bus (wire resistance etc.)
# Real hardware may vary; adjust via parameter
ESTIMATED_WIRE_DROP_V: float = 0.05

# Battery thresholds — matches open_cr_module.cpp (warns below 11V)
VOLTAGE_OK_V: float = 11.5
VOLTAGE_LOW_V: float = 11.0

# Name of the op3_manager node (used for connection checking, same as read_write.cpp)
OP3_MANAGER_NAME: str = '/op3_manager'

# Regex to extract voltage from StatusMsg text: "Present Volt : 11.5V"
VOLTAGE_PATTERN = re.compile(r'[Pp]resent\s+[Vv]olt\s*:\s*([\d.]+)\s*V', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class JointPowerData:
    name: str
    position_rad: float = 0.0
    velocity_rad_s: float = 0.0
    effort_raw: float = 0.0
    # Voltage at this servo's input pin (from present_input_voltage register)
    # All servos share the same power bus, so this is ≈ battery voltage
    # minus small wire resistance drops.
    input_voltage_V: Optional[float] = None
    # Below fields only populated if present_current is in OP3.robot bulk-read
    current_A: Optional[float] = None
    estimated_power_W: Optional[float] = None

    def to_dict(self) -> dict:
        d = {
            'position_rad': round(self.position_rad, 4),
            'velocity_rad_s': round(self.velocity_rad_s, 4),
            'effort_raw': round(self.effort_raw, 4),
        }
        if self.input_voltage_V is not None:
            d['input_voltage_V'] = round(self.input_voltage_V, 2)
        if self.current_A is not None:
            d['current_A'] = round(self.current_A, 4)
        if self.estimated_power_W is not None:
            d['estimated_power_W'] = round(self.estimated_power_W, 3)
        return d


@dataclass
class PowerSnapshot:
    timestamp: float
    battery_voltage_V: Optional[float]
    battery_status: str
    manager_connected: bool
    current_data_available: bool
    joints: Dict[str, JointPowerData] = field(default_factory=dict)

    @property
    def total_effort_abs(self) -> float:
        return sum(abs(j.effort_raw) for j in self.joints.values())

    @property
    def total_estimated_power_W(self) -> Optional[float]:
        values = [j.estimated_power_W for j in self.joints.values()
                  if j.estimated_power_W is not None]
        return sum(values) if values else None

    @property
    def avg_joint_voltage_V(self) -> Optional[float]:
        """Average of all per-joint input voltages (should be ≈ battery voltage)."""
        values = [j.input_voltage_V for j in self.joints.values()
                  if j.input_voltage_V is not None]
        return sum(values) / len(values) if values else None

    @property
    def min_joint_voltage_V(self) -> Optional[float]:
        """Minimum of all per-joint input voltages (detects weak connections)."""
        values = [j.input_voltage_V for j in self.joints.values()
                  if j.input_voltage_V is not None]
        return min(values) if values else None

    @property
    def max_joint_voltage_V(self) -> Optional[float]:
        values = [j.input_voltage_V for j in self.joints.values()
                  if j.input_voltage_V is not None]
        return max(values) if values else None

    def to_dict(self) -> dict:
        d = {
            'timestamp': round(self.timestamp, 3),
            'manager_connected': self.manager_connected,
            'current_data_available': self.current_data_available,
            'battery': {
                'voltage_V': self.battery_voltage_V,
                'status': self.battery_status,
            },
            'voltage_summary': {
                'battery_total_V': self.battery_voltage_V,
                'avg_joint_input_V': round(self.avg_joint_voltage_V, 2) if self.avg_joint_voltage_V else None,
                'min_joint_input_V': round(self.min_joint_voltage_V, 2) if self.min_joint_voltage_V else None,
                'max_joint_input_V': round(self.max_joint_voltage_V, 2) if self.max_joint_voltage_V else None,
            },
            'joints': {name: jd.to_dict() for name, jd in self.joints.items()},
            'totals': {
                'total_effort_abs': round(self.total_effort_abs, 3),
            },
        }
        pw = self.total_estimated_power_W
        if pw is not None:
            d['totals']['estimated_total_power_W'] = round(pw, 3)
        return d


# ---------------------------------------------------------------------------
# Main Node
# ---------------------------------------------------------------------------

class PowerMonitorNode(Node):
    """
    Passive ROS2 power monitoring node for ROBOTIS OP3.

    Follows the same topic structure as the official read_write_demo:
    - Reads /robotis/present_joint_states (published by robotis_controller)
    - Reads /robotis/status (published by open_cr_module for voltage)
    - Checks for /op3_manager before processing (same pattern as read_write.cpp)
    """

    def __init__(self) -> None:
        super().__init__('op3_power_monitor')

        self._declare_parameters()

        # --- State ---
        self._battery_voltage: Optional[float] = None
        self._battery_status: str = 'UNKNOWN'
        self._manager_connected: bool = False
        self._current_data_available: bool = False  # True only if effort[] has non-zero values
        self._joint_data: Dict[str, JointPowerData] = {
            name: JointPowerData(name=name) for name in OP3_JOINT_NAMES
        }
        self._last_joint_msg_time: Optional[float] = None
        self._last_voltage_msg_time: Optional[float] = None
        self._print_counter: int = 0
        self._warned_no_current: bool = False

        # --- QoS profiles (matches robotis_controller publish QoS) ---
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
            durability=DurabilityPolicy.VOLATILE,
        )
        reliable_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        # --- Subscribers ---
        # Same topics as used in official read_write_demo (read_write.cpp)
        self._status_sub = self.create_subscription(
            StatusMsg,
            '/robotis/status',
            self._on_status_msg,
            reliable_qos,
        )
        self._joint_sub = self.create_subscription(
            JointState,
            '/robotis/present_joint_states',   # published by robotis_controller
            self._on_joint_states,
            sensor_qos,
        )
        self._button_sub = self.create_subscription(
            String,
            '/robotis/open_cr/button',          # published by open_cr_module
            self._on_button,
            reliable_qos,
        )

        # --- Publishers ---
        self._voltage_pub = self.create_publisher(Float32, '/op3/power/battery_voltage', reliable_qos)
        self._batt_status_pub = self.create_publisher(String, '/op3/power/battery_status', reliable_qos)
        self._joint_loads_pub = self.create_publisher(JointState, '/op3/power/joint_loads', sensor_qos)
        self._joint_voltages_pub = self.create_publisher(
            Float32MultiArray, '/op3/power/joint_voltages', sensor_qos
        )
        self._summary_pub = self.create_publisher(String, '/op3/power/summary', reliable_qos)

        # --- Timers ---
        # 1 Hz: report timer (same concept as SPIN_RATE=30 in read_write.cpp, but for reporting)
        report_hz = self.get_parameter('report_period_sec').value
        self._report_timer = self.create_timer(report_hz, self._on_report_timer)

        # 5 Hz: check for op3_manager (mirrors the while-loop in read_write.cpp main())
        self._manager_check_timer = self.create_timer(2.0, self._check_manager)

        self.get_logger().info(
            '\n[OP3 Power Monitor] Node started.'
            '\nWaiting for /op3_manager... (matches read_write_demo behavior)'
            '\nSubscribing to:'
            '\n  /robotis/status              <- battery voltage (open_cr_module)'
            '\n  /robotis/present_joint_states <- joint states (robotis_controller)'
            '\n  /robotis/open_cr/button      <- button events (open_cr_module)'
            '\nPublishing to:'
            '\n  /op3/power/battery_voltage | /op3/power/battery_status'
            '\n  /op3/power/joint_loads     | /op3/power/summary'
        )

    # -----------------------------------------------------------------------
    # Parameter Declaration
    # -----------------------------------------------------------------------

    def _declare_parameters(self) -> None:
        self.declare_parameter('report_period_sec', 1.0)
        self.declare_parameter('voltage_warn_threshold_v', VOLTAGE_LOW_V)
        self.declare_parameter('voltage_ok_threshold_v', VOLTAGE_OK_V)
        self.declare_parameter('print_table', True)

    # -----------------------------------------------------------------------
    # Manager Detection (mirrors checkManagerRunning() from read_write.cpp)
    # -----------------------------------------------------------------------

    def _check_manager(self) -> None:
        """Check if /op3_manager is running. Mirrors checkManagerRunning() from read_write.cpp."""
        node_names = self.get_node_names_and_namespaces()
        found = any(
            f'/{ns}/{name}'.replace('//', '/') == OP3_MANAGER_NAME or name == 'op3_manager'
            for name, ns in node_names
        )
        if found and not self._manager_connected:
            self._manager_connected = True
            self.get_logger().info(
                '[OP3 Power Monitor] ✅ Connected to /op3_manager. Monitoring active.'
            )
        elif not found and self._manager_connected:
            self._manager_connected = False
            self.get_logger().warn(
                '[OP3 Power Monitor] ⚠️  /op3_manager disconnected.'
            )

    # -----------------------------------------------------------------------
    # Subscriber Callbacks
    # -----------------------------------------------------------------------

    def _on_status_msg(self, msg: StatusMsg) -> None:
        """
        Parse battery voltage from /robotis/status published by open_cr_module.
        Text format: "Present Volt : 11.5V"
        This is confirmed from open_cr_module.cpp handleVoltage() function.
        """
        match = VOLTAGE_PATTERN.search(msg.status_msg)
        if match is None:
            return  # Not a voltage message (could be button info, etc.)

        try:
            voltage = float(match.group(1))
        except ValueError:
            self.get_logger().warn(
                f'[Power Monitor] Cannot parse voltage from: "{msg.status_msg}"'
            )
            return

        self._battery_voltage = voltage
        self._last_voltage_msg_time = time.monotonic()

        ok_v = self.get_parameter('voltage_ok_threshold_v').value
        warn_v = self.get_parameter('voltage_warn_threshold_v').value

        if voltage >= ok_v:
            self._battery_status = 'OK'
        elif voltage >= warn_v:
            self._battery_status = 'LOW'
            self.get_logger().warn(
                f'[Power Monitor] ⚠️  Battery LOW: {voltage:.2f}V '
                f'(OK threshold: {ok_v}V)'
            )
        else:
            self._battery_status = 'CRITICAL'
            self.get_logger().error(
                f'[Power Monitor] 🔴 Battery CRITICAL: {voltage:.2f}V! '
                f'Robot may shut down. (threshold: {warn_v}V, matches open_cr_module.cpp < 11V)'
            )

        self._publish_battery_data()

    def _on_joint_states(self, msg: JointState) -> None:
        """
        Process /robotis/present_joint_states published by robotis_controller.

        From the official framework docs:
          "Publish a topic that contains present & goal joint states"
          Fields: present position, present velocity, present effort,
                  goal position, goal velocity, goal effort

        IMPORTANT: effort[] = present_current register value (raw units).
        In DEFAULT OP3.robot, present_current is NOT in bulk-read items,
        so effort[] = 0. To enable it, add 'present_current' to OP3.robot.
        """
        self._last_joint_msg_time = time.monotonic()
        voltage = self._battery_voltage or XM430_NOMINAL_VOLTAGE_V

        # Detect if current data is actually available (non-zero effort values)
        has_nonzero_effort = any(
            abs(e) > 0.0
            for e in msg.effort
        ) if msg.effort else False

        if has_nonzero_effort != self._current_data_available:
            self._current_data_available = has_nonzero_effort
            if has_nonzero_effort:
                self.get_logger().info(
                    '[Power Monitor] ✅ Non-zero effort[] detected! '
                    'present_current appears to be in OP3.robot bulk-read. '
                    'Current data will be shown in Amperes.'
                )
            elif not self._warned_no_current:
                self._warned_no_current = True
                self.get_logger().warn(
                    '[Power Monitor] ℹ️  effort[] values are all zero. '
                    'To enable per-joint current tracking, add "present_current" '
                    'to BULK READ ITEMS in OP3.robot for each Dynamixel, then rebuild op3_manager.'
                )

        for i, joint_name in enumerate(msg.name):
            if joint_name not in self._joint_data:
                self._joint_data[joint_name] = JointPowerData(name=joint_name)

            jd = self._joint_data[joint_name]
            jd.position_rad  = msg.position[i] if i < len(msg.position) else 0.0
            jd.velocity_rad_s = msg.velocity[i] if i < len(msg.velocity) else 0.0
            effort_raw = msg.effort[i] if i < len(msg.effort) else 0.0
            jd.effort_raw = effort_raw

            # --- Per-joint voltage estimation ---
            # Each XM430-W350 has a present_input_voltage register (addr 144).
            # All servos share the same power bus → input voltage ≈ battery voltage
            # minus small wire resistance drop (proportional to effort/load).
            # If present_input_voltage is in OP3.robot bulk-read, it would appear
            # in a separate topic. Since it's not, we estimate from battery voltage.
            if self._battery_voltage is not None:
                # Higher load → slightly higher voltage drop on wires
                load_factor = min(abs(effort_raw) / 1193.0, 1.0)  # 1193 = XM430 max current
                wire_drop = ESTIMATED_WIRE_DROP_V * (1.0 + load_factor)
                jd.input_voltage_V = round(self._battery_voltage - wire_drop, 2)
            else:
                jd.input_voltage_V = None

            # Convert to current only if we have actual data in effort
            if has_nonzero_effort and abs(effort_raw) > 0:
                # XM430: 1 unit = 2.69 mA (from Dynamixel e-manual)
                jd.current_A = abs(effort_raw) * XM430_CURRENT_UNIT_A
                jd.estimated_power_W = jd.current_A * voltage
            else:
                jd.current_A = None
                jd.estimated_power_W = None

        self._publish_joint_loads(msg.header)
        self._publish_joint_voltages()

    def _on_button(self, msg: String) -> None:
        """
        Log button events from /robotis/open_cr/button (open_cr_module).
        Button names match what's shown in official read_write.cpp:
        'mode', 'start', 'user', 'reset', 'mode_long', 'start_long', 'user_long'
        """
        self.get_logger().info(
            f'[Power Monitor] OpenCR button pressed: "{msg.data}"'
        )

    # -----------------------------------------------------------------------
    # Publishers
    # -----------------------------------------------------------------------

    def _publish_battery_data(self) -> None:
        if self._battery_voltage is not None:
            v_msg = Float32()
            v_msg.data = float(self._battery_voltage)
            self._voltage_pub.publish(v_msg)

        s_msg = String()
        s_msg.data = self._battery_status
        self._batt_status_pub.publish(s_msg)

    def _publish_joint_loads(self, header) -> None:
        js = JointState()
        js.header = header
        js.header.stamp = self.get_clock().now().to_msg()
        for name in OP3_JOINT_NAMES:
            jd = self._joint_data[name]
            js.name.append(name)
            js.position.append(jd.position_rad)
            js.velocity.append(jd.velocity_rad_s)
            js.effort.append(jd.effort_raw)
        self._joint_loads_pub.publish(js)

    def _publish_joint_voltages(self) -> None:
        """Publish per-joint estimated input voltage as Float32MultiArray.
        Data order follows OP3_JOINT_NAMES."""
        msg = Float32MultiArray()
        for name in OP3_JOINT_NAMES:
            jd = self._joint_data[name]
            msg.data.append(jd.input_voltage_V if jd.input_voltage_V is not None else 0.0)
        self._joint_voltages_pub.publish(msg)

    def _publish_summary(self, snapshot: PowerSnapshot) -> None:
        msg = String()
        msg.data = json.dumps(snapshot.to_dict(), indent=None)
        self._summary_pub.publish(msg)

    # -----------------------------------------------------------------------
    # 1 Hz Report Timer
    # -----------------------------------------------------------------------

    def _on_report_timer(self) -> None:
        now = time.monotonic()

        snapshot = PowerSnapshot(
            timestamp=time.time(),
            battery_voltage_V=self._battery_voltage,
            battery_status=self._battery_status,
            manager_connected=self._manager_connected,
            current_data_available=self._current_data_available,
            joints=dict(self._joint_data),
        )

        self._publish_summary(snapshot)

        # Stale data warnings
        if self._last_voltage_msg_time is not None:
            if (now - self._last_voltage_msg_time) > 10.0:
                self.get_logger().warn(
                    f'[Power Monitor] No /robotis/status for '
                    f'{now - self._last_voltage_msg_time:.0f}s. '
                    f'Is open_cr_module running?'
                )

        if self._last_joint_msg_time is not None:
            if (now - self._last_joint_msg_time) > 2.0:
                self.get_logger().warn(
                    f'[Power Monitor] No /robotis/present_joint_states for '
                    f'{now - self._last_joint_msg_time:.0f}s. '
                    f'Is op3_manager running?'
                )

        if self.get_parameter('print_table').value:
            self._print_report_table(snapshot)

    # -----------------------------------------------------------------------
    # Terminal Report Table
    # -----------------------------------------------------------------------

    def _print_report_table(self, snapshot: PowerSnapshot) -> None:
        self._print_counter += 1

        if self._print_counter % 10 == 1:
            self.get_logger().info(
                '\n' + '═' * 78 + '\n'
                '  OP3 POWER MONITOR — Voltage & Current per Component\n'
                '  Topics: /robotis/present_joint_states + /robotis/status\n'
                + '═' * 78
            )

        v_str = f'{snapshot.battery_voltage_V:.2f} V' \
            if snapshot.battery_voltage_V is not None else 'N/A'
        bat_icon = {'OK': '🟢', 'LOW': '🟡', 'CRITICAL': '🔴'}.get(
            snapshot.battery_status, '⚪'
        )
        mgr_icon = '✅' if snapshot.manager_connected else '❌'

        # --- Voltage Summary Section ---
        avg_v = snapshot.avg_joint_voltage_V
        min_v = snapshot.min_joint_voltage_V
        max_v = snapshot.max_joint_voltage_V
        avg_str = f'{avg_v:.2f}V' if avg_v is not None else 'N/A'
        min_str = f'{min_v:.2f}V' if min_v is not None else 'N/A'
        max_str = f'{max_v:.2f}V' if max_v is not None else 'N/A'

        lines = ['\n┌─ Voltage Overview ─────────────────────────────────────────────────────────┐']
        lines.append(
            f'│  op3_manager: {mgr_icon}    Battery (OpenCR): {bat_icon} {v_str:<8} [{snapshot.battery_status:<8}]'
            '                 │'
        )
        lines.append(
            f'│  Servo Bus : avg={avg_str:<7} min={min_str:<7} max={max_str:<7}'
            '                              │'
        )
        lines.append('└────────────────────────────────────────────────────────────────────────────┘')

        # --- Per-Joint Table with Voltage Column ---
        lines.append('┌─ Per-Joint Detail (XM430-W350 × 20) ───────────────────────────────────────┐')
        lines.append('│  {:>16}  {:>8}  {:>8}  {:>7}  {:>8}  {:>8}  {:>8}   │'.format(
            'Joint', 'Vin (V)', 'Pos(°)', 'Vel', 'Effort', 'I (A)', 'P (W)'
        ))
        lines.append('│  ' + '─' * 72 + '  │')

        for name in OP3_JOINT_NAMES:
            jd = snapshot.joints.get(name)
            if jd is None:
                continue
            pos_deg = math.degrees(jd.position_rad)
            vin_str = f'{jd.input_voltage_V:.2f}' if jd.input_voltage_V is not None else ' N/A '
            i_str = f'{jd.current_A:.4f}' if jd.current_A is not None else '  N/A '
            p_str = f'{jd.estimated_power_W:.3f}' if jd.estimated_power_W is not None else '  N/A '
            lines.append('│  {:>16}  {:>8}  {:>8.2f}  {:>7.3f}  {:>8.2f}  {:>8}  {:>8}   │'.format(
                name, vin_str, pos_deg, jd.velocity_rad_s, jd.effort_raw, i_str, p_str
            ))

        lines.append('│  ' + '─' * 72 + '  │')

        pw = snapshot.total_estimated_power_W
        pw_str = f'{pw:.2f} W' if pw is not None else 'N/A'
        lines.append(
            f'│  TOTAL   Battery: {v_str:<8}   '
            f'Σ|effort|: {snapshot.total_effort_abs:>7.2f}   '
            f'Σ power: {pw_str:<10}'
            '            │'
        )
        lines.append('└────────────────────────────────────────────────────────────────────────────┘')

        self.get_logger().info('\n'.join(lines))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main(args=None) -> None:
    rclpy.init(args=args)
    node = PowerMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('[OP3 Power Monitor] Shutting down.')
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
