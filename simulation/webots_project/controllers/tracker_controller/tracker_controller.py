"""
BRONE KINEMATICS FIXED
- Logic: Porting dari Kinematik.cpp
- Calibration: ALL INVERTED (-1.0) berdasarkan data tracking user
- Control: Joystick Pygame
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import math
from controller import Robot

try:
    import pygame
except ImportError:
    print("CRITICAL: Pygame error.")

class BroneRobot:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # --- 1. KONFIGURASI KALIBRASI (HASIL RISET ANDA) ---
        # Semua roda dikali -1.0 agar sesuai fisika Webots
        self.INV_W1 = -1.0
        self.INV_W2 = -1.0
        self.INV_W3 = -1.0
        self.INV_W4 = -1.0

        # --- 2. SETUP MOTOR ---
        # W1=Depan Kanan, W2=Depan Kiri, W3=Belakang Kiri, W4=Belakang Kanan
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            # Torque feedback dimatikan dulu (sesuai request 'clean')
            self.wheels.append(m)

        # --- 3. PARAMETER KINEMATIK (Dari Kinematik.h) ---
        self.a = 45.0       
        self.L = 0.208      
        self.r_wheel = 0.06 
        
        # Pre-calc
        self.sin_a = 0.7071 # sin(45)
        self.cos_a = 0.7071 # cos(45)
        
        # Limit Kecepatan (Rad/s)
        self.MAX_SPEED = 46.0

        # --- 4. INIT JOYSTICK ---
        pygame.init()
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            print(f">> SYSTEM READY: {self.js.get_name()}")
        else:
            print("!! WARNING: Joystick tidak ditemukan.")

    def get_input(self):
        pygame.event.pump()
        if not self.js: return 0, 0, 0

        # Mapping: Axis 0 (X), Axis 1 (Y)
        # Button 6 (L1/L2) & 7 (R1/R2) untuk putar
        
        raw_x = self.js.get_axis(0)
        raw_y = self.js.get_axis(1)
        
        raw_rot = 0.0
        # Sesuaikan index tombol ini dengan joystick Anda (Tadi L1=6, R1=7)
        if self.js.get_button(6): raw_rot = 1.0   # Kiri
        elif self.js.get_button(7): raw_rot = -1.0 # Kanan
        
        # Deadzone
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        # Gain (Kecepatan m/s)
        VEL_GAIN = 1.0 
        ROT_GAIN = 2.0

        # Invert Y agar Atas = Positif (Maju)
        vx = raw_x * VEL_GAIN
        vy = -raw_y * VEL_GAIN 
        theta = raw_rot * ROT_GAIN

        return vx, vy, theta

    def invers_kinematic_cpp(self, vx, vy, vtheta):
        """
        Rumus ASLI dari Kinematik.cpp Anda.
        Output pola Maju: [+ - - +]
        """
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * vtheta) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * vtheta) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * vtheta) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * vtheta) / self.r_wheel
        
        return [w1, w2, w3, w4]

    def clamp(self, val):
        if val > self.MAX_SPEED: return self.MAX_SPEED
        if val < -self.MAX_SPEED: return -self.MAX_SPEED
        return val

    def run(self):
        print("=== BRONE SIAP JALAN ===")
        print("Kontrol: Analog Kiri (Gerak), L1/R1 (Putar)")
        
        while self.robot.step(self.timestep) != -1:
            # 1. Input
            vx, vy, w = self.get_input()
            
            # 2. Hitung Rumus C++
            raw_vels = self.invers_kinematic_cpp(vx, vy, w)
            
            # 3. Eksekusi ke Motor (DENGAN INVERSI TOTAL)
            # Kita balik semua tanda output rumus agar sesuai fisik robot
            self.wheels[0].setVelocity(self.clamp(raw_vels[0] * self.INV_W1))
            self.wheels[1].setVelocity(self.clamp(raw_vels[1] * self.INV_W2))
            self.wheels[2].setVelocity(self.clamp(raw_vels[2] * self.INV_W3))
            self.wheels[3].setVelocity(self.clamp(raw_vels[3] * self.INV_W4))

if __name__ == "__main__":
    bot = BroneRobot()
    bot.run()