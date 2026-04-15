#!/usr/bin/env python3
"""
BRone Roda — Motion Test Node
================================
Publishes /cmd_vel (Twist) in a repeating sequence:
  1. MAJU    (forward)   — 3s
  2. MUNDUR  (backward)  — 3s
  3. KANAN   (strafe R)  — 3s
  4. KIRI    (strafe L)  — 3s
  5. PUTAR CW            — 3s
  6. PUTAR CCW           — 3s
  7. STOP               — 2s

Designed to test the real robot via Orange Pi.
Use with start_roda.sh for full production test.
"""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

# Speed parameters (m/s and rad/s) — conservative for testing
LINEAR_SPEED = 0.15    # m/s
ANGULAR_SPEED = 0.4    # rad/s

# Motion sequence: (name, vx, vy, omega, duration_sec)
MOTION_SEQUENCE = [
    ('⬆️  MAJU (Forward)',    LINEAR_SPEED,  0.0,            0.0,           3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           1.5),
    ('⬇️  MUNDUR (Backward)', -LINEAR_SPEED, 0.0,            0.0,           3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           1.5),
    ('➡️  KANAN (Strafe R)',   0.0,          -LINEAR_SPEED,   0.0,           3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           1.5),
    ('⬅️  KIRI (Strafe L)',    0.0,           LINEAR_SPEED,   0.0,           3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           1.5),
    ('🔄 PUTAR CW (Spin)',    0.0,           0.0,            -ANGULAR_SPEED, 3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           1.5),
    ('🔄 PUTAR CCW (Spin)',   0.0,           0.0,            ANGULAR_SPEED,  3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           2.0),
    ('↗️  DIAGONAL FR',       LINEAR_SPEED,  -LINEAR_SPEED,  0.0,           3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           1.5),
    ('↙️  DIAGONAL BL',      -LINEAR_SPEED,  LINEAR_SPEED,   0.0,           3.0),
    ('⏹️  STOP',              0.0,           0.0,            0.0,           2.0),
]


class RodaMotionTest(Node):
    def __init__(self):
        super().__init__('brone_roda_motion_test')

        self._speed = self.declare_parameter('speed', LINEAR_SPEED).value
        self._loop = self.declare_parameter('loop', True).value

        self._pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self._seq_idx = 0
        self._elapsed = 0.0
        self._dt = 0.1  # 10 Hz publish rate
        self._cycle = 1

        self.create_timer(self._dt, self._tick)

        total_time = sum(s[4] for s in MOTION_SEQUENCE)
        self.get_logger().info(
            '\n╔══════════════════════════════════════════════╗\n'
            '║   🛞 BRONE RODA — MOTION TEST               ║\n'
            '╠══════════════════════════════════════════════╣\n'
            f'║  Speed   : {self._speed:.2f} m/s                      ║\n'
            f'║  Sequence: {len(MOTION_SEQUENCE)} steps ({total_time:.0f}s per cycle)     ║\n'
            f'║  Loop    : {"Yes ♾️" if self._loop else "No (single run)"}                        ║\n'
            '║  Topic   : /cmd_vel                         ║\n'
            '╠══════════════════════════════════════════════╣\n'
            '║  Press Ctrl+C to stop (sends STOP command)  ║\n'
            '╚══════════════════════════════════════════════╝\n'
        )
        self._print_step()

    def _print_step(self):
        step = MOTION_SEQUENCE[self._seq_idx]
        name, vx, vy, omega, dur = step
        self.get_logger().info(
            f'[Cycle {self._cycle}] {name}  '
            f'(vx={vx:.2f}, vy={vy:.2f}, ω={omega:.2f}) '
            f'— {dur:.1f}s'
        )

    def _tick(self):
        step = MOTION_SEQUENCE[self._seq_idx]
        name, vx, vy, omega, duration = step

        # Scale linear speeds by parameter
        scale = self._speed / LINEAR_SPEED if LINEAR_SPEED > 0 else 1.0

        msg = Twist()
        msg.linear.x = vx * scale
        msg.linear.y = vy * scale
        msg.angular.z = omega  # angular not scaled by linear speed param
        self._pub.publish(msg)

        self._elapsed += self._dt

        if self._elapsed >= duration:
            self._elapsed = 0.0
            self._seq_idx += 1

            if self._seq_idx >= len(MOTION_SEQUENCE):
                if self._loop:
                    self._seq_idx = 0
                    self._cycle += 1
                    self.get_logger().info(
                        f'\n━━━ Cycle {self._cycle} ━━━'
                    )
                else:
                    self.get_logger().info(
                        '\n✅ Motion test complete! Sending STOP.'
                    )
                    self._send_stop()
                    raise SystemExit(0)

            self._print_step()

    def _send_stop(self):
        msg = Twist()
        for _ in range(10):
            self._pub.publish(msg)
        self.get_logger().info('🛑 STOP command sent.')


def main(args=None):
    rclpy.init(args=args)
    node = RodaMotionTest()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        # Always send stop on exit
        stop = Twist()
        node._pub.publish(stop)
        node._pub.publish(stop)
        node.get_logger().info('🛑 Motion test stopped. Robot STOPPED.')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
