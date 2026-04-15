#!/usr/bin/env python3
"""
BRone Roda — Standalone Demo Publisher
========================================
Publishes realistic dummy data to /brone/power/summary for dashboard testing.
No robot hardware or Orange Pi required!

Values fluctuate with sine-wave patterns to simulate real robot activity.
"""

import math
import json
import time
import random

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class RodaDemoPublisher(Node):
    def __init__(self):
        super().__init__('brone_roda_demo_publisher')
        self._pub = self.create_publisher(String, '/brone/power/summary', 10)
        self._t0 = time.time()
        self._tick = 0
        self.create_timer(0.2, self._publish)  # 5 Hz
        self.get_logger().info(
            '\n[RODA DEMO Publisher] Running...\n'
            '  Publishing fake data to:\n'
            '    /brone/power/summary (BRone Roda)\n'
            '  Press Ctrl+C to stop.\n'
        )

    def _sin(self, period=10.0, phase=0.0, amp=1.0, offset=0.0):
        t = time.time() - self._t0
        return offset + amp * math.sin(2 * math.pi * t / period + phase)

    def _noise(self, scale=0.01):
        return random.gauss(0, scale)

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
            torque = speed * 1.2 + abs(omega) * 0.5 + self._noise(0.05)
            torque = max(0.0, torque)
            vel_rad = speed / 0.055 * (1 if i % 2 == 0 else -1) + self._noise(0.1)
            rpm = vel_rad * 60.0 / (2 * math.pi)
            current = (torque / 0.35) + 0.4 + self._noise(0.02)
            power = v_oc * current / 4

            total_current += current

            wheel_data[wname] = {
                'name': wname,
                'torque_Nm': round(torque, 4),
                'velocity_rad_s': round(vel_rad, 3),
                'rpm': round(rpm, 1),
                'current_A': round(current, 4),
                'power_W': round(power, 3),
            }

        total_power = v_oc * total_current / 0.92 + 8.0
        v_terminal = max(0, v_oc - total_current * 0.05)

        if soc > 30:
            batt_status = 'OK'
        elif soc > 10:
            batt_status = 'LOW'
        else:
            batt_status = 'CRITICAL'

        avg_rpm = sum(abs(w['rpm']) for w in wheel_data.values()) / 4.0

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
                'robot_ip': '10.42.0.247',
            },
            'totals': {
                'total_power_W': round(total_power, 2),
                'total_current_A': round(total_current, 2),
                'avg_rpm': round(avg_rpm, 1),
            },
        }

    def _publish(self):
        msg = String()
        msg.data = json.dumps(self._make_roda())
        self._pub.publish(msg)
        self._tick += 1


def main(args=None):
    rclpy.init(args=args)
    node = RodaDemoPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('[RODA DEMO Publisher] Stopped.')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
