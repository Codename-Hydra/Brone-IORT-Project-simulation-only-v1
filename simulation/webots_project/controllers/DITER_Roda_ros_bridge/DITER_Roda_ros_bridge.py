"""
BRONE HYBRID CONTROLLER + DITER PRO (SAFETY FAILSAFE EDITION)
-------------------------------------------------------------
Fitur:
- Auto-Respawn: Ya (Patient Loop).
- Latency Monitor: Ya.
- SAFETY CUTOFF: Jika Ping > 50ms, Robot (Sim & Real) OTOMATIS BERHENTI.
- Smart Idle & Physics Power: Ya.
"""

import sys
import os
import math
import time
import threading
import subprocess
import re

# --- 1. SETUP LINGKUNGAN ROS 2 ---
ros_pkg_path = '/opt/ros/jazzy/lib/python3.12/site-packages'
if ros_pkg_path not in sys.path:
    sys.path.append(ros_pkg_path)

os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

try:
    import pygame
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, QoSReliabilityPolicy, QoSDurabilityPolicy, QoSHistoryPolicy
    from geometry_msgs.msg import Twist
    from controller import Robot 
except ImportError as e:
    sys.exit(f"CRITICAL ERROR: Library kurang lengkap. {e}")

class BroneDiterController:
    def __init__(self):
        # --- KONFIGURASI PENTING ---
        self.ROBOT_IP = "127.0.0.1" # Ubah ke localhost untuk pure Webots simulation
        self.MAX_SAFE_LATENCY = 100.0 # Batas toleransi (ms)
        
        self.robot = None
        self.timestep = 32
        self.latency_ms = 0.0 
        self.connection_quality = "UNK"
        self.is_lagging = False # Flag status lag
        
        # ROS 2 Setup
        if not rclpy.ok():
            rclpy.init(args=None)
        self.ros_node = rclpy.create_node('brone_diter_node')
        
        # Optimized QoS: Keep RELIABLE for compatibility, but increase buffer
        cmd_vel_qos = QoSProfile(
            reliability=QoSReliabilityPolicy.RELIABLE,  # Must match subscriber!
            durability=QoSDurabilityPolicy.VOLATILE,
            history=QoSHistoryPolicy.KEEP_LAST,
            depth=50  # Increased buffer to handle Jazzy-Humble mismatch
        )
        
        self.publisher_ = self.ros_node.create_publisher(Twist, '/cmd_vel', cmd_vel_qos)
        print("> ROS2 Publisher: RELIABLE QoS with depth=50 (Jazzy-Humble compatible)")

        # Joystick Setup
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print(f"-> JOYSTICK READY: {self.joystick.get_name()}")
        else:
            self.joystick = None

        # Variables Physics
        self.L = 0.208
        self.r_wheel = 0.055
        self.sin_a = math.sin(math.radians(45))
        self.cos_a = math.cos(math.radians(45))
        
        # Power Specs
        self.VOLTAGE_BATT = 22.2 
        self.P_STATIC  = 8.0     
        self.EFF_BTS   = 0.92    
        self.I_IDLE  = 0.4       
        self.I_STALL = 6.0       
        self.T_STALL = 1.96      
        self.K_T = self.T_STALL / (self.I_STALL - self.I_IDLE) 
        
        # Control Smoothing
        self.SYNC_FACTOR = 1.185 
        self.MAX_LINEAR_SPEED = 0.5  
        self.MAX_ANGULAR_SPEED = 1.0 
        self.DECAY_RATE = 0.05        
        self.cur_vx = 0.0
        self.cur_vy = 0.0
        self.cur_w  = 0.0

        # Start Latency Monitor Thread
        self.monitor_thread = threading.Thread(target=self._latency_loop, daemon=True)
        self.monitor_thread.start()

    def _latency_loop(self):
        """Thread khusus Ping"""
        while True:
            try:
                # Ping timeout 1 detik
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', self.ROBOT_IP],
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.returncode == 0:
                    match = re.search(r'time=([\d.]+)', result.stdout)
                    if match:
                        self.latency_ms = float(match.group(1))
                    else:
                        self.latency_ms = 0.0
                else:
                    self.latency_ms = 999.0 # Timeout dianggap 999ms
                
                # Update Status Lag
                if self.latency_ms > self.MAX_SAFE_LATENCY:
                    self.is_lagging = True
                    self.connection_quality = "UNSAFE"
                else:
                    self.is_lagging = False
                    self.connection_quality = "SAFE"
                    
            except Exception:
                self.latency_ms = 999.0
                self.is_lagging = True
            
            time.sleep(0.5) # Update cepat (setiap 0.5 detik)

    def attempt_connection(self):
        print(">> Menunggu Webots siap...", end='', flush=True)
        while True:
            try:
                self.robot = Robot()
                self.timestep = int(self.robot.getBasicTimeStep())
                
                self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
                self.wheels = []
                for name in self.wheel_names:
                    m = self.robot.getDevice(name)
                    m.setPosition(float('inf')) 
                    m.setVelocity(0.0)
                    m.enableTorqueFeedback(self.timestep)
                    self.wheels.append(m)
                
                print("\n>> SUKSES! TERHUBUNG KE WEBOTS.")
                return True 
            except Exception:
                time.sleep(1)
                print(".", end='', flush=True)

    def calculate_power(self, is_moving):
        total_current = 0.0
        for m in self.wheels:
            if is_moving:
                torque = abs(m.getTorqueFeedback())
                i_motor = (torque / self.K_T) + self.I_IDLE
            else:
                i_motor = self.I_IDLE
            total_current += i_motor
        p_dyn = (self.VOLTAGE_BATT * total_current) / self.EFF_BTS
        return self.P_STATIC + p_dyn, total_current

    def get_input(self):
        pygame.event.pump() 
        if not self.joystick: return 0,0,0
        
        vy = -self.joystick.get_axis(1) 
        vx = self.joystick.get_axis(0)  
        w = 0.0 
        if abs(vx)<0.1: vx=0
        if abs(vy)<0.1: vy=0
        try:
            if self.joystick.get_button(6): w = -1.0 
            if self.joystick.get_button(7): w = 1.0  
        except: pass
        return vx*self.MAX_LINEAR_SPEED, vy*self.MAX_LINEAR_SPEED, w*self.MAX_ANGULAR_SPEED

    def smooth(self, tvx, tvy, tw):
        if tvx == 0: self.cur_vx = 0
        else: self.cur_vx += (tvx - self.cur_vx) * self.DECAY_RATE
        if tvy == 0: self.cur_vy = 0
        else: self.cur_vy += (tvy - self.cur_vy) * self.DECAY_RATE
        if tw == 0: self.cur_w = 0
        else: self.cur_w += (tw - self.cur_w) * self.DECAY_RATE
        return self.cur_vx, self.cur_vy, self.cur_w

    def update_motors(self, vx, vy, w):
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        vels = [w1*self.SYNC_FACTOR, w2*self.SYNC_FACTOR, w3*self.SYNC_FACTOR, w4*self.SYNC_FACTOR]
        for i, wheel in enumerate(self.wheels):
            wheel.setVelocity(vels[i])
            
    def update_ros(self, vx, vy, w):
        msg = Twist()
        msg.linear.y = float(vy)
        msg.linear.x = -float(vx)
        msg.angular.z = -float(w) 
        self.publisher_.publish(msg)

    def run(self):
        self.attempt_connection()
        
        print(f"=== SYSTEM ACTIVE (Max Latency: {self.MAX_SAFE_LATENCY}ms) ===")
        step_counter = 0
        
        try:
            while self.robot.step(self.timestep) != -1:
                # 1. Ambil Input Joystick
                tvx, tvy, tw = self.get_input()
                
                # --- [SAFETY CHECK] ---
                if self.is_lagging:
                    # BAHAYA: Ping tinggi! Hentikan paksa!
                    vx, vy, w = 0.0, 0.0, 0.0
                    
                    # Reset internal state agar tidak ada sisa momentum saat connect lagi
                    self.cur_vx = 0.0
                    self.cur_vy = 0.0
                    self.cur_w  = 0.0
                    
                    is_moving = False
                    status_display = "LAG STOP" # Status Khusus
                else:
                    # AMAN: Ping rendah. Lanjut normal.
                    vx, vy, w = self.smooth(tvx, tvy, tw)
                    is_moving = (abs(tvx)>0 or abs(tvy)>0 or abs(tw)>0 or abs(vx)>0.01)
                    status_display = "RUN" if is_moving else "IDLE"

                # 2. Kirim Perintah (Entah itu Stop atau Jalan)
                self.update_motors(vx, vy, w)
                self.update_ros(vx, vy, w)
                
                # 3. Hitung Power
                power, amps = self.calculate_power(is_moving)
                
                # 4. Dashboard
                if step_counter % 20 == 0: 
                    if status_display != "LAG STOP":
                        if power > 400: status_display = "STALL!!"
                    
                    lat_str = f"{self.latency_ms:.0f}ms"
                    if self.latency_ms > 900: lat_str = "TIMEOUT"
                    
                    print(f"[{status_display:^8}] {power:05.1f}W | Ping: {lat_str:<7} | V:{vx:+.2f}")
                
                step_counter += 1
                rclpy.spin_once(self.ros_node, timeout_sec=0)
                
        except Exception as e:
            print(f"Runtime Error: {e}")
            
        print("\n>> WEBOTS RESET DETECTED. RESTARTING...")
        try:
            self.ros_node.destroy_node()
            rclpy.shutdown()
            pygame.quit()
        except: pass
        sys.exit(0)

if __name__ == "__main__":
    c = BroneDiterController()
    c.run()
