#!/usr/bin/env python3
"""
BRone Roda — Gamepad Teleop Controller
========================================
Kontrol robot fisik via GameSir / Xbox-style gamepad.
Publish /cmd_vel (Twist) ke Orange Pi via ROS2 DDS.

Mapping:
  Left Stick Y (Axis 1) → Maju/Mundur (linear.y)
  Left Stick X (Axis 0) → Kiri/Kanan  (linear.x)
  LB (Button 6)         → Putar CCW   (angular.z +)
  RB (Button 7)         → Putar CW    (angular.z -)

Fitur:
  - Smooth acceleration, INSTANT stop (lepas stick = berhenti total)
  - Deadzone 10% untuk menghindari drift
  - Safety: Ctrl+C langsung kirim STOP
  - Terminal dashboard real-time

Requires: pygame (pip install pygame)
"""

import sys
import os
import time

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

try:
    import pygame
except ImportError:
    print("❌ pygame belum terinstall!")
    print("   Install: pip install pygame")
    sys.exit(1)

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist


class GamepadTeleop(Node):
    def __init__(self):
        super().__init__('brone_gamepad_teleop')

        # Parameters
        self._max_linear = self.declare_parameter('max_linear', 0.35).value   # m/s
        self._max_angular = self.declare_parameter('max_angular', 0.8).value  # rad/s
        self._deadzone = self.declare_parameter('deadzone', 0.10).value
        self._accel_rate = self.declare_parameter('accel_rate', 0.12).value

        # Publisher
        self._pub = self.create_publisher(Twist, '/cmd_vel', 10)

        # Joystick setup
        pygame.init()
        pygame.joystick.init()
        self._js = None

        if pygame.joystick.get_count() > 0:
            self._js = pygame.joystick.Joystick(0)
            self._js.init()
            js_name = self._js.get_name()
            n_axes = self._js.get_numaxes()
            n_btns = self._js.get_numbuttons()
            self.get_logger().info(f'✅ Joystick: {js_name} ({n_axes} axes, {n_btns} buttons)')
        else:
            self.get_logger().warn('⚠️ Joystick tidak ditemukan! Hubungkan GameSir lalu restart.')

        # Smoothing state
        self._cur_vx = 0.0
        self._cur_vy = 0.0
        self._cur_w = 0.0

        # Dashboard state
        self._tick = 0
        self._t0 = time.time()

        # Timer: 20 Hz control loop
        self.create_timer(0.05, self._control_loop)

        self.get_logger().info(
            '\n╔══════════════════════════════════════════════╗\n'
            '║   🎮 BRONE RODA — GAMEPAD TELEOP            ║\n'
            '╠══════════════════════════════════════════════╣\n'
            f'║  Max Linear : {self._max_linear:.2f} m/s                    ║\n'
            f'║  Max Angular: {self._max_angular:.2f} rad/s                   ║\n'
            '║  Topic      : /cmd_vel                      ║\n'
            '╠══════════════════════════════════════════════╣\n'
            '║  Left Stick  → Maju/Mundur/Kiri/Kanan       ║\n'
            '║  LB (btn 6)  → Putar Kiri  (CCW)            ║\n'
            '║  RB (btn 7)  → Putar Kanan (CW)             ║\n'
            '║  Ctrl+C      → EMERGENCY STOP               ║\n'
            '╚══════════════════════════════════════════════╝\n'
        )

    def _control_loop(self):
        pygame.event.pump()

        target_vx = 0.0
        target_vy = 0.0
        target_w = 0.0

        if self._js:
            # Read stick axes
            raw_x = self._js.get_axis(0)   # Left/Right
            raw_y = self._js.get_axis(1)   # Up/Down

            # Apply deadzone
            if abs(raw_x) < self._deadzone:
                raw_x = 0.0
            if abs(raw_y) < self._deadzone:
                raw_y = 0.0

            # Map to velocity (inverted as needed per existing robot convention)
            target_vx = -raw_x * self._max_linear   # Stick kanan → robot kanan
            target_vy = -raw_y * self._max_linear    # Stick atas → robot maju

            # Rotation buttons
            try:
                btn_lb = self._js.get_button(6)
                btn_rb = self._js.get_button(7)
            except pygame.error:
                btn_lb = 0
                btn_rb = 0

            if btn_lb:
                target_w = self._max_angular    # CCW
            elif btn_rb:
                target_w = -self._max_angular   # CW

        # Smooth acceleration, INSTANT stop
        if target_vx == 0.0:
            self._cur_vx = 0.0
        else:
            self._cur_vx += (target_vx - self._cur_vx) * self._accel_rate

        if target_vy == 0.0:
            self._cur_vy = 0.0
        else:
            self._cur_vy += (target_vy - self._cur_vy) * self._accel_rate

        if target_w == 0.0:
            self._cur_w = 0.0
        else:
            self._cur_w += (target_w - self._cur_w) * self._accel_rate

        # Publish
        msg = Twist()
        msg.linear.x = float(self._cur_vx)
        msg.linear.y = float(self._cur_vy)
        msg.angular.z = float(self._cur_w)
        self._pub.publish(msg)

        # Terminal dashboard (every 0.5s = 10 ticks)
        self._tick += 1
        if self._tick % 10 == 0:
            moving = abs(self._cur_vx) > 0.01 or abs(self._cur_vy) > 0.01 or abs(self._cur_w) > 0.01
            status = '🟢 RUN ' if moving else '⚪ IDLE'
            elapsed = time.time() - self._t0
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)

            print(
                f'\r[{status}] '
                f'Vx:{self._cur_vx:+.2f} '
                f'Vy:{self._cur_vy:+.2f} '
                f'ω:{self._cur_w:+.2f} '
                f'| ⏱ {mins:02d}:{secs:02d}',
                end='', flush=True
            )


def main(args=None):
    rclpy.init(args=args)
    node = GamepadTeleop()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        # Emergency stop
        stop = Twist()
        for _ in range(5):
            node._pub.publish(stop)
        print('\n🛑 STOP — Robot dihentikan.')
        node.destroy_node()
        rclpy.try_shutdown()
        pygame.quit()


if __name__ == '__main__':
    main()
