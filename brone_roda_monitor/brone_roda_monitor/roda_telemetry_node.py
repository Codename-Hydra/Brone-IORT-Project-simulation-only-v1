#!/usr/bin/env python3
"""
BRone Roda — Telemetry Node
============================
ROS2 node that:
  1. Subscribes to /cmd_vel (Twist)              — motion command
  2. Subscribes to /brone/wheel_states (JointState) — wheel torque/velocity
  3. Computes power, battery SOC, per-wheel metrics
  4. Publishes /brone/power/summary (String JSON) — for dashboard

This replaces the old monolithic Webots-only telemetry pipeline
with proper ROS2 pub/sub architecture.

Physical parameters from the real BRone Roda robot:
  - 4x mecanum wheels at 45° angles
  - Battery: 6S LiPo 22.2V nominal, 5200mAh
  - Motor Kt derived from stall torque & current
  - Wheel radius: 0.055m, L (half-wheelbase): 0.208m
"""

import math
import time
import json
import subprocess
import re
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import JointState
from std_msgs.msg import String


# ============================================================
# Data classes
# ============================================================

@dataclass
class WheelData:
    name: str
    torque_Nm: float = 0.0
    velocity_rad_s: float = 0.0
    rpm: float = 0.0
    current_A: float = 0.0
    power_W: float = 0.0

    def to_dict(self):
        return {
            'name': self.name,
            'torque_Nm': round(self.torque_Nm, 4),
            'velocity_rad_s': round(self.velocity_rad_s, 3),
            'rpm': round(self.rpm, 1),
            'current_A': round(self.current_A, 4),
            'power_W': round(self.power_W, 3),
        }


@dataclass
class BatteryState:
    voltage_V: float = 22.2
    current_A: float = 0.0
    power_W: float = 0.0
    soc_pct: float = 100.0
    status: str = 'OK'
    runtime_hours: float = 24.0
    cell_voltage_V: float = 3.7

    def to_dict(self):
        return {
            'voltage_V': round(self.voltage_V, 2),
            'current_A': round(self.current_A, 2),
            'power_W': round(self.power_W, 2),
            'soc_pct': round(self.soc_pct, 1),
            'status': self.status,
            'runtime_hours': round(self.runtime_hours, 2),
            'cell_voltage_V': round(self.cell_voltage_V, 3),
        }


@dataclass
class MotionState:
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0

    def to_dict(self):
        return {
            'vx': round(self.vx, 3),
            'vy': round(self.vy, 3),
            'omega': round(self.omega, 3),
        }


# ============================================================
# Main Node
# ============================================================

class RodaTelemetryNode(Node):
    """
    Topics subscribed:
        /cmd_vel              (geometry_msgs/Twist)     — Motion command
        /brone/wheel_states   (sensor_msgs/JointState)  — Wheel torque & velocity

    Topics published:
        /brone/power/summary  (std_msgs/String)  — JSON telemetry packet
    """

    # ---- Physical Constants (BRone Roda) ----
    CELL_COUNT = 6
    BATT_CAPACITY_MAH = 5200.0
    FULL_VOLTAGE = 4.2 * CELL_COUNT          # 25.2V
    EMPTY_VOLTAGE = 3.0 * CELL_COUNT         # 18.0V
    NOMINAL_VOLTAGE = 3.7 * CELL_COUNT       # 22.2V
    VOLTAGE_RANGE = FULL_VOLTAGE - EMPTY_VOLTAGE
    R_INTERNAL = 0.05                         # Ohm

    I_IDLE = 0.4       # A per motor at idle
    I_STALL = 6.0      # A per motor at stall
    T_STALL = 1.96     # N·m at stall
    K_T = T_STALL / (I_STALL - I_IDLE)       # Torque constant
    DRIVER_EFF = 0.92  # BTS motor driver efficiency
    P_STATIC = 8.0     # W — controller, sensors, etc.

    L = 0.208           # half-wheelbase (m)
    R_WHEEL = 0.055     # wheel radius (m)

    WHEEL_NAMES = ['wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR']

    def __init__(self):
        super().__init__('brone_roda_telemetry')

        # --- State ---
        self._wheels: Dict[str, WheelData] = {
            n: WheelData(name=n) for n in self.WHEEL_NAMES
        }
        self._battery = BatteryState()
        self._motion = MotionState()

        # Energy tracking
        total_energy_J = self.NOMINAL_VOLTAGE * (self.BATT_CAPACITY_MAH / 1000.0) * 3600.0
        self._total_energy = total_energy_J
        self._current_energy = total_energy_J
        self._avg_power_window = []
        self._last_calc_time = time.time()

        # Latency monitoring
        self._robot_ip = self.declare_parameter('robot_ip', '10.42.0.247').value
        self._ping_ms = 0.0
        self._connection_quality = 'UNKNOWN'
        self._ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        self._ping_thread.start()

        # --- Subscribers ---
        self.create_subscription(Twist, '/cmd_vel', self._cmd_vel_cb, 10)
        self.create_subscription(JointState, '/brone/wheel_states', self._wheel_states_cb, 10)

        # --- Publisher ---
        self._pub_summary = self.create_publisher(String, '/brone/power/summary', 10)

        # --- Timer: 5 Hz publish ---
        self.create_timer(0.2, self._publish_summary)

        self.get_logger().info(
            '\n[BRone Roda Telemetry] Starting...\n'
            f'  Battery: {self.CELL_COUNT}S LiPo {self.BATT_CAPACITY_MAH}mAh\n'
            f'  Robot IP: {self._robot_ip}\n'
            '  Subscribed to: /cmd_vel, /brone/wheel_states\n'
            '  Publishing:    /brone/power/summary (5 Hz)\n'
        )

    # ---- Ping Monitor ----

    def _ping_loop(self):
        while rclpy.ok():
            try:
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', self._robot_ip],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                if result.returncode == 0:
                    m = re.search(r'time=([\d.]+)', result.stdout)
                    self._ping_ms = float(m.group(1)) if m else 0.0
                else:
                    self._ping_ms = 999.0
                self._connection_quality = 'SAFE' if self._ping_ms < 100 else 'UNSAFE'
            except Exception:
                self._ping_ms = 999.0
                self._connection_quality = 'UNSAFE'
            time.sleep(1.0)

    # ---- Callbacks ----

    def _cmd_vel_cb(self, msg: Twist):
        self._motion.vx = msg.linear.x
        self._motion.vy = msg.linear.y
        self._motion.omega = msg.angular.z

    def _wheel_states_cb(self, msg: JointState):
        """
        Expected JointState:
            name:     ['wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR']
            effort:   [torque_FL, torque_FR, torque_RL, torque_RR]  (N·m)
            velocity: [vel_FL, vel_FR, vel_RL, vel_RR]              (rad/s)
        """
        for i, name in enumerate(msg.name):
            if name not in self._wheels:
                self._wheels[name] = WheelData(name=name)
            wd = self._wheels[name]
            wd.torque_Nm = msg.effort[i] if i < len(msg.effort) else 0.0
            wd.velocity_rad_s = msg.velocity[i] if i < len(msg.velocity) else 0.0
            wd.rpm = wd.velocity_rad_s * 60.0 / (2.0 * math.pi)

    # ---- Power Calculation ----

    def _calculate_power(self):
        now = time.time()
        dt = now - self._last_calc_time
        self._last_calc_time = now
        if dt <= 0 or dt > 2.0:
            dt = 0.2

        soc = max(0.0, self._current_energy / self._total_energy)
        v_oc = self.EMPTY_VOLTAGE + self.VOLTAGE_RANGE * soc

        i_total_motors = 0.0
        for wd in self._wheels.values():
            i_load = abs(wd.torque_Nm) / self.K_T
            i_motor = i_load + self.I_IDLE
            wd.current_A = i_motor
            i_total_motors += i_motor

        i_motors_drawn = i_total_motors / self.DRIVER_EFF
        i_static = self.P_STATIC / max(v_oc, 1.0)
        i_total = i_motors_drawn + i_static

        v_terminal = max(0.0, v_oc - i_total * self.R_INTERNAL)
        total_power = v_terminal * i_total
        consumed_J = total_power * dt
        self._current_energy = max(0.0, self._current_energy - consumed_J)

        # Per-wheel power
        for wd in self._wheels.values():
            wd.power_W = v_terminal * wd.current_A

        # Averaging for runtime estimation
        self._avg_power_window.append(total_power)
        max_window = int(5.0 / dt)
        if len(self._avg_power_window) > max_window:
            self._avg_power_window.pop(0)

        # Battery state
        self._battery.voltage_V = v_terminal
        self._battery.current_A = i_total
        self._battery.power_W = total_power
        self._battery.soc_pct = soc * 100.0
        self._battery.cell_voltage_V = v_terminal / self.CELL_COUNT

        if soc > 0.3:
            self._battery.status = 'OK'
        elif soc > 0.1:
            self._battery.status = 'LOW'
        else:
            self._battery.status = 'CRITICAL'

        # Runtime estimation
        if self._avg_power_window:
            avg_p = sum(self._avg_power_window) / len(self._avg_power_window)
            if avg_p > 1.0:
                self._battery.runtime_hours = (self._current_energy / 3600.0) / avg_p
            else:
                self._battery.runtime_hours = 999.0

    # ---- Publisher ----

    def _publish_summary(self):
        self._calculate_power()

        packet = {
            'type': 'brone_roda',
            'battery': self._battery.to_dict(),
            'wheels': {n: wd.to_dict() for n, wd in self._wheels.items()},
            'motion': self._motion.to_dict(),
            'system': {
                'ping_ms': round(self._ping_ms, 0),
                'connection_quality': self._connection_quality,
                'robot_ip': self._robot_ip,
            },
            'totals': {
                'total_power_W': round(self._battery.power_W, 2),
                'total_current_A': round(self._battery.current_A, 2),
                'avg_rpm': round(
                    sum(abs(wd.rpm) for wd in self._wheels.values()) / max(len(self._wheels), 1),
                    1
                ),
            },
        }

        msg = String()
        msg.data = json.dumps(packet)
        self._pub_summary.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RodaTelemetryNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('[BRone Roda Telemetry] Shutting down.')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
