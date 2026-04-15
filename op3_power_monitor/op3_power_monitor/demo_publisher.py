#!/usr/bin/env python3
"""
Dummy data publishers for BOTH dashboards — demo/visualization testing only.
Publishes realistic-looking fake data to:
  /op3/power/summary      (OP3 Body)
  /brone/power/summary     (BRone Roda)

All values fluctuate with sine-wave patterns to simulate real robot activity.
"""

import math
import json
import time
import random

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

# ============================================================
# OP3 Joint names (matches OP3.robot config)
# ============================================================
OP3_JOINTS = [
    ('r_sho_pitch', 1), ('l_sho_pitch', 2),
    ('r_sho_roll', 3), ('l_sho_roll', 4),
    ('r_el', 5), ('l_el', 6),
    ('r_hip_yaw', 7), ('l_hip_yaw', 8),
    ('r_hip_roll', 9), ('l_hip_roll', 10),
    ('r_hip_pitch', 11), ('l_hip_pitch', 12),
    ('r_knee', 13), ('l_knee', 14),
    ('r_ank_pitch', 15), ('l_ank_pitch', 16),
    ('r_ank_roll', 17), ('l_ank_roll', 18),
    ('head_pan', 19), ('head_tilt', 20),
]


class DemoPublisher(Node):
    def __init__(self):
        super().__init__('brone_demo_publisher')
        self._pub_op3 = self.create_publisher(String, '/op3/power/summary', 10)
        self._pub_roda = self.create_publisher(String, '/brone/power/summary', 10)
        self._t0 = time.time()
        self._tick = 0
        self.create_timer(0.2, self._publish)  # 5 Hz
        self.get_logger().info(
            '\n[DEMO Publisher] Running...\n'
            '  Publishing fake data to:\n'
            '    /op3/power/summary   (OP3 Body)\n'
            '    /brone/power/summary (BRone Roda)\n'
            '  Press Ctrl+C to stop.\n'
        )

    def _sin(self, period=10.0, phase=0.0, amp=1.0, offset=0.0):
        t = time.time() - self._t0
        return offset + amp * math.sin(2 * math.pi * t / period + phase)

    def _noise(self, scale=0.01):
        return random.gauss(0, scale)

    # ============================================================
    # OP3 Body
    # ============================================================
    def _make_op3(self):
        t = time.time() - self._t0
        batt_v = 11.75 + self._sin(30, 0, 0.35) + self._noise(0.02)
        batt_v = max(10.0, min(13.0, batt_v))

        if batt_v > 11.5:
            status = 'OK'
        elif batt_v > 11.0:
            status = 'LOW'
        else:
            status = 'CRITICAL'

        joints = {}
        total_effort = 0.0
        total_power = 0.0

        for name, jid in OP3_JOINTS:
            # Position varies with walking pattern
            pos_base = {
                'r_hip_pitch': -0.4, 'l_hip_pitch': 0.4,
                'r_knee': 0.8, 'l_knee': -0.8,
                'r_ank_pitch': -0.4, 'l_ank_pitch': 0.4,
            }.get(name, 0.0)
            pos = pos_base + self._sin(4, jid * 0.3, 0.15) + self._noise(0.005)

            # Effort (torque raw) — legs work harder
            is_leg = 'hip' in name or 'knee' in name or 'ank' in name
            effort_base = 120.0 if is_leg else 30.0
            effort = effort_base * abs(self._sin(5, jid * 0.5, 1.0, 0.3)) + self._noise(2.0)
            effort = max(0.0, effort)

            # Per-joint voltage (slight droop under load)
            load_factor = min(effort / 1193.0, 1.0)
            vin = batt_v - load_factor * 0.15 + self._noise(0.01)

            # Current (from effort)
            current = effort * 0.00269  # XM430 current unit
            power = vin * current

            total_effort += abs(effort)
            total_power += power

            joints[name] = {
                'position_rad': round(pos, 4),
                'velocity_rad_s': round(self._sin(3, jid, 0.05), 4),
                'effort_raw': round(effort, 4),
                'input_voltage_V': round(vin, 2),
                'current_A': round(current, 4),
                'estimated_power_W': round(power, 3),
            }

        vins = [j['input_voltage_V'] for j in joints.values()]

        return {
            'timestamp': round(t, 3),
            'manager_connected': True,
            'current_data_available': True,
            'battery': {
                'voltage_V': round(batt_v, 2),
                'status': status,
            },
            'voltage_summary': {
                'battery_total_V': round(batt_v, 2),
                'avg_joint_input_V': round(sum(vins) / len(vins), 2),
                'min_joint_input_V': round(min(vins), 2),
                'max_joint_input_V': round(max(vins), 2),
            },
            'joints': joints,
            'totals': {
                'total_effort_abs': round(total_effort, 3),
                'estimated_total_power_W': round(total_power, 3),
            },
        }

    # ============================================================
    # BRone Roda
    # ============================================================
    def _make_roda(self):
        t = time.time() - self._t0

        # Simulate some motion (alternating patterns)
        vx = self._sin(8, 0, 0.3) * (1 if int(t / 12) % 2 == 0 else 0.1)
        vy = self._sin(6, 1.5, 0.4) * (1 if int(t / 12) % 2 == 1 else 0.1)
        omega = self._sin(10, 3.0, 0.5) * (0.3 if abs(vx) < 0.05 and abs(vy) < 0.05 else 0.0)

        # Battery (6S LiPo)
        soc = max(0, 100.0 - t * 0.05)  # Slow drain
        v_oc = 18.0 + (7.2 * soc / 100.0)

        total_current = 0.0
        wheel_data = {}
        wheel_labels = ['wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR']
        speed = math.sqrt(vx**2 + vy**2)

        for i, wname in enumerate(wheel_labels):
            # Torque proportional to speed + some variation per wheel
            torque = speed * 1.2 + abs(omega) * 0.5 + self._noise(0.05)
            torque = max(0.0, torque)
            vel_rad = speed / 0.055 * (1 if i % 2 == 0 else -1) + self._noise(0.1)
            rpm = vel_rad * 60.0 / (2 * math.pi)
            current = (torque / 0.35) + 0.4 + self._noise(0.02)
            power = v_oc * current / 4  # Rough per-wheel

            total_current += current

            wheel_data[wname] = {
                'name': wname,
                'torque_Nm': round(torque, 4),
                'velocity_rad_s': round(vel_rad, 3),
                'rpm': round(rpm, 1),
                'current_A': round(current, 4),
                'power_W': round(power, 3),
            }

        total_power = v_oc * total_current / 0.92 + 8.0  # + static
        v_terminal = max(0, v_oc - total_current * 0.05)

        if soc > 30:
            batt_status = 'OK'
        elif soc > 10:
            batt_status = 'LOW'
        else:
            batt_status = 'CRITICAL'

        avg_rpm = sum(abs(w['rpm']) for w in wheel_data.values()) / 4.0

        # Runtime estimation
        if total_power > 1:
            remaining_wh = (v_oc * 5.2 * soc / 100.0)
            runtime_h = remaining_wh / total_power
        else:
            runtime_h = 99.0

        return {
            'type': 'brone_roda',
            'battery': {
                'voltage_V': round(v_terminal, 2),
                'current_A': round(total_current, 2),
                'power_W': round(total_power, 2),
                'soc_pct': round(soc, 1),
                'status': batt_status,
                'runtime_hours': round(runtime_h, 2),
                'cell_voltage_V': round(v_terminal / 6.0, 3),
            },
            'wheels': wheel_data,
            'motion': {
                'vx': round(vx, 3),
                'vy': round(vy, 3),
                'omega': round(omega, 3),
            },
            'system': {
                'ping_ms': round(5 + abs(self._sin(20, 0, 15)) + self._noise(2), 0),
                'connection_quality': 'SAFE',
                'robot_ip': '10.30.117.200',
            },
            'totals': {
                'total_power_W': round(total_power, 2),
                'total_current_A': round(total_current, 2),
                'avg_rpm': round(avg_rpm, 1),
            },
        }

    # ============================================================
    # Publish
    # ============================================================
    def _publish(self):
        op3_msg = String()
        op3_msg.data = json.dumps(self._make_op3())
        self._pub_op3.publish(op3_msg)

        roda_msg = String()
        roda_msg.data = json.dumps(self._make_roda())
        self._pub_roda.publish(roda_msg)

        self._tick += 1


def main(args=None):
    rclpy.init(args=args)
    node = DemoPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('[DEMO Publisher] Stopped.')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
