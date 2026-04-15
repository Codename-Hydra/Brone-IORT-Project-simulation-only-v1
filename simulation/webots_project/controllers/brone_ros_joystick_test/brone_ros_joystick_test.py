"""
BRONE REAL ROBOT CONTROLLER (TOTAL INSTANT STOP)
Fitur:
1. Akselerasi: Smooth (Perlahan naik agar aman).
2. Deselerasi: INSTANT (Lepas joystick = Berhenti total).
3. Tombol LB(6)/RB(7): Rotasi.
4. Output: /cmd_vel.
"""

import sys
import os
import time
import math

# --- IMPORT PYGAME ---
import pygame

# --- SETUP ROS 2 JAZZY PATH ---
ros_pkg_path = '/opt/ros/jazzy/lib/python3.12/site-packages'
if ros_pkg_path not in sys.path:
    sys.path.append(ros_pkg_path)

os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
except ImportError:
    sys.exit("CRITICAL: Gagal import rclpy.")

class RealRobotController(Node):
    def __init__(self):
        super().__init__('brone_teleop_node')
        
        self.publisher_ = self.create_publisher(Twist, '/cmd_vel', 10)
        self.timer = self.create_timer(0.05, self.timer_callback) # 20 Hz
        
        # --- SETUP JOYSTICK ---
        pygame.init()
        pygame.joystick.init()
        
        self.joystick = None
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print(f"✅ Joystick Terhubung: {self.joystick.get_name()}")
        else:
            print("⚠️ WARNING: Joystick tidak ditemukan!")

        # --- KONFIGURASI KECEPATAN ---
        self.MAX_LINEAR_SPEED = 0.5  # m/s
        self.MAX_ANGULAR_SPEED = 0.8 # rad/s
        
        # Decay Rate (Hanya berpengaruh saat menambah kecepatan)
        self.DECAY_RATE = 0.1
        self.DEADZONE = 0.1 
        
        self.cur_vx = 0.0
        self.cur_vy = 0.0
        self.cur_w = 0.0

    def timer_callback(self):
        pygame.event.pump()
        
        target_vx = 0.0
        target_vy = 0.0
        target_w = 0.0

        if self.joystick:
            # === 1. INPUT ===
            raw_ax1 = self.joystick.get_axis(1) # Atas/Bawah
            raw_ax0 = self.joystick.get_axis(0) # Kiri/Kanan
            
            # Mapping Linear
            if abs(raw_ax1) > self.DEADZONE:
                target_vy = -raw_ax1 * self.MAX_LINEAR_SPEED 
            if abs(raw_ax0) > self.DEADZONE:
                target_vx = -raw_ax0 * self.MAX_LINEAR_SPEED 
            
            # Mapping Tombol Rotasi (LB=6, RB=7)
            try:
                btn_lb = self.joystick.get_button(6) 
                btn_rb = self.joystick.get_button(7) 
            except:
                btn_lb = 0; btn_rb = 0
            
            if btn_lb: target_w = self.MAX_ANGULAR_SPEED
            elif btn_rb: target_w = -self.MAX_ANGULAR_SPEED

        # === 2. SMOOTH ACCELERATION, INSTANT STOP ===
        
        # --- LOGIKA MAJU MUNDUR ---
        if target_vy == 0.0:
            self.cur_vy = 0.0 # Stop Instan
        else:
            self.cur_vy += (target_vy - self.cur_vy) * self.DECAY_RATE # Tarikan Halus

        # --- LOGIKA GESER KIRI KANAN ---
        if target_vx == 0.0:
            self.cur_vx = 0.0 # Stop Instan
        else:
            self.cur_vx += (target_vx - self.cur_vx) * self.DECAY_RATE # Tarikan Halus

        # --- LOGIKA ROTASI ---
        if target_w == 0.0:
            self.cur_w = 0.0 # Stop Instan
        else:
            self.cur_w += (target_w - self.cur_w) * self.DECAY_RATE # Tarikan Halus

        # === 3. PUBLISH ===
        msg = Twist()
        msg.linear.x = float(self.cur_vx) 
        msg.linear.y = float(self.cur_vy)
        msg.angular.z = float(self.cur_w)
        
        self.publisher_.publish(msg)

def main(args=None):
    rclpy.init(args=args)
    print("=== CONTROLLER: TOTAL INSTANT STOP ===")
    node = RealRobotController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        pygame.quit()

if __name__ == "__main__":
    main()