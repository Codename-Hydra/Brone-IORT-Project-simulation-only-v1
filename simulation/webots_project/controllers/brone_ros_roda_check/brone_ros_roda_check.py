"""
BRONE HYBRID CONTROLLER (DIGITAL TWIN LINK) - ROTATION SYNC FIX
---------------------------------------------------------------
Status Sistem:
1. Navigasi : AMAN (Sync Webots & Real Robot).
2. Kecepatan: AMAN (Webots Speed x1.185).
3. Tombol   : AMAN (Webots & Real Robot sinkron).

Perbaikan Terakhir:
- Menambahkan tanda minus (-) pada output 'angular.z' di update_real_robot.
  Ini membalik arah putaran HANYA untuk robot asli agar sesuai dengan Webots.
"""

import sys
import os
import math

# --- 1. SETUP LINGKUNGAN ROS 2 ---
ros_pkg_path = '/opt/ros/jazzy/lib/python3.12/site-packages'
if ros_pkg_path not in sys.path:
    sys.path.append(ros_pkg_path)

os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

# Import Library
try:
    import pygame
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
    from controller import Robot # API Webots
except ImportError as e:
    sys.exit(f"CRITICAL ERROR: Library kurang lengkap. {e}")

class BroneHybridController:
    def __init__(self):
        # === A. SETUP WEBOTS (Dunia 1) ===
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # Setup Motor Webots
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf')) # Mode Velocity
            m.setVelocity(0.0)
            self.wheels.append(m)

        # Parameter Fisik
        self.L = 0.208
        self.r_wheel = 0.06
        self.sin_a = math.sin(math.radians(45))
        self.cos_a = math.cos(math.radians(45))

        # === KALIBRASI SPEED ===
        # Webots dipercepat agar mengejar Real Robot (8m vs 6.75m)
        self.SYNC_FACTOR = 1.185 

        # === B. SETUP ROS 2 (Dunia 2) ===
        rclpy.init(args=None)
        self.ros_node = rclpy.create_node('brone_digital_twin_controller')
        self.publisher_ = self.ros_node.create_publisher(Twist, '/cmd_vel', 10)
        print("-> ROS 2 Siap. Mode Hybrid Full Feature Aktif.")

        # === C. SETUP JOYSTICK ===
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print(f"-> Joystick: {self.joystick.get_name()}")
        else:
            sys.exit("ERROR: Joystick tidak ditemukan.")

        # Variabel Smoothing
        self.MAX_LINEAR_SPEED = 0.5
        self.MAX_ANGULAR_SPEED = 1.0
        self.DECAY_RATE = 0.1

        self.cur_vx = 0.0
        self.cur_vy = 0.0
        self.cur_w  = 0.0

    def get_joystick_input(self):
        pygame.event.pump() 
        
        # --- MAPPING AXIS (AMAN) ---
        # Maju (vy) -> Axis 1 (Dibalik jadi positif)
        raw_vy = -self.joystick.get_axis(1) 

        # Geser (vx) -> Axis 0 (Positif agar Webots Kanan)
        raw_vx = self.joystick.get_axis(0) 

        # Putar (w) -> Axis 3 (Analog Kanan)
        raw_w  = -self.joystick.get_axis(3)

        # Deadzone
        if abs(raw_vx) < 0.1: raw_vx = 0
        if abs(raw_vy) < 0.1: raw_vy = 0
        if abs(raw_w)  < 0.1: raw_w  = 0

        # --- MAPPING TOMBOL (LOGIKA WEBOTS) ---
        # Kita set sesuai Webots (LB = -1, RB = 1)
        try:
            if self.joystick.get_button(6): raw_w = -1.0   # LB
            if self.joystick.get_button(7): raw_w = 1.0    # RB
        except:
            pass

        return raw_vx * self.MAX_LINEAR_SPEED, \
               raw_vy * self.MAX_LINEAR_SPEED, \
               raw_w  * self.MAX_ANGULAR_SPEED

    def apply_smoothing(self, target_vx, target_vy, target_w):
        if target_vx == 0: self.cur_vx = 0
        else: self.cur_vx += (target_vx - self.cur_vx) * self.DECAY_RATE
        
        if target_vy == 0: self.cur_vy = 0
        else: self.cur_vy += (target_vy - self.cur_vy) * self.DECAY_RATE
        
        if target_w == 0: self.cur_w = 0
        else: self.cur_w += (target_w - self.cur_w) * self.DECAY_RATE
        
        return self.cur_vx, self.cur_vy, self.cur_w

    def update_webots_motors(self, vx, vy, w):
        """Webots: Kinematika Standar + KALIBRASI"""
        
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        
        # Terapkan FAKTOR KALIBRASI (1.185x)
        vels = [
            w1 * self.SYNC_FACTOR, 
            w2 * self.SYNC_FACTOR, 
            w3 * self.SYNC_FACTOR, 
            w4 * self.SYNC_FACTOR
        ]
        
        for i, wheel in enumerate(self.wheels):
            wheel.setVelocity(vels[i])

    def update_real_robot(self, vx, vy, w):
        """ROS 2: Mapping Khusus Robot Fisik"""
        msg = Twist()
        
        # Mapping Linear
        msg.linear.y = float(vy)      # Maju
        msg.linear.x = -float(vx)     # Geser (Negatif biar aman)
        
        # --- PERBAIKAN ROTASI REAL LIFE ---
        # Karena di Webots sudah benar, tapi di Real Life terbalik,
        # kita tambahkan tanda MINUS (-) di sini.
        msg.angular.z = -float(w)
        
        self.publisher_.publish(msg)

    def run(self):
        print("=== BRONE CONTROLLER: SYSTEM READY ===")
        print("Status: All Systems Synchronized.")
        
        try:
            while self.robot.step(self.timestep) != -1:
                tgt_vx, tgt_vy, tgt_w = self.get_joystick_input()
                vx, vy, w = self.apply_smoothing(tgt_vx, tgt_vy, tgt_w)
                
                self.update_webots_motors(vx, vy, w)
                self.update_real_robot(vx, vy, w)
                
                rclpy.spin_once(self.ros_node, timeout_sec=0)
        except KeyboardInterrupt:
            pass
        finally:
            self.update_webots_motors(0,0,0)
            self.update_real_robot(0,0,0)
            self.ros_node.destroy_node()
            rclpy.shutdown()
            pygame.quit()

if __name__ == "__main__":
    controller = BroneHybridController()
    controller.run()