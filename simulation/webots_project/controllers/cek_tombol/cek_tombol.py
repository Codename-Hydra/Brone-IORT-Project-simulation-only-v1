"""
BRONE TRACKING V2 (Fixed Buttons)
- Mapping: L1=6 (CCW), R1=7 (CW)
- Tujuan: Mencatat Pola Arah Putaran Roda (+/-)
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import math
from controller import Robot

try:
    import pygame
except ImportError:
    pass

class BroneTracker:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # Nama Roda (Sesuai WBT)
        # W1=Depan Kanan, W2=Depan Kiri, W3=Belakang Kiri, W4=Belakang Kanan
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        
        # KITA SET SEMUA KE 1.0 DULU UNTUK MELIHAT ARAH ASLI MOTOR
        self.INV_W1 = 1.0 
        self.INV_W2 = 1.0
        self.INV_W3 = 1.0
        self.INV_W4 = 1.0

        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            self.wheels.append(m)

        # Parameter Kinematik
        self.L = 0.208
        self.r_wheel = 0.06
        
        # Pre-calc trigono (Sudut 45 derajat)
        # Sin(45) = Cos(45) = 0.7071
        self.sin_a = 0.7071
        self.cos_a = 0.7071

        # Init Joystick
        pygame.init()
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            print(f">> JOYSTICK OK: {self.js.get_name()}")
        else:
            print("!! WARNING: Joystick tidak deteksi")

    def get_input(self):
        pygame.event.pump()
        if not self.js: return 0, 0, 0

        # Axis Gerak
        raw_x = self.js.get_axis(0) # Kiri Kanan
        raw_y = self.js.get_axis(1) # Maju Mundur
        
        # Tombol Rotasi (UPDATED: 6 & 7)
        raw_rot = 0.0
        # Button 6 = L1 (Putar Kiri / CCW / Positif)
        if self.js.get_button(6): 
            raw_rot = 1.0
        # Button 7 = R1 (Putar Kanan / CW / Negatif)
        elif self.js.get_button(7):
            raw_rot = -1.0
        
        # Deadzone
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        # Gain
        vx = raw_x * 1.0
        vy = -raw_y * 1.0 # Invert Y agar Maju = Positif
        theta = raw_rot * 1.5

        return vx, vy, theta

    def invers_kinematic_cpp(self, vx, vy, vtheta):
        # Rumus C++ Asli (Tanpa modifikasi tanda)
        # w1 (FR)
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * vtheta) / self.r_wheel
        # w2 (FL)
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * vtheta) / self.r_wheel
        # w3 (BL)
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * vtheta) / self.r_wheel
        # w4 (BR)
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * vtheta) / self.r_wheel
        
        return [w1, w2, w3, w4]

    def run(self):
        print("=== TES ARAH MAJU ===")
        print("Dorong Stik MAJU, lalu lapor hasilnya ke saya!")
        
        while self.robot.step(self.timestep) != -1:
            vx, vy, w = self.get_input()
            
            # Hitung Rumus
            vels = self.invers_kinematic_cpp(vx, vy, w)
            
            # Kirim ke Motor (Tanpa Inversi dulu)
            self.wheels[0].setVelocity(vels[0])
            self.wheels[1].setVelocity(vels[1])
            self.wheels[2].setVelocity(vels[2])
            self.wheels[3].setVelocity(vels[3])

            # LOGGING HANYA JIKA ADA INPUT
            if abs(vy) > 0.5: # Hanya saat maju kencang
                print(f"INPUT MAJU (Vy={vy:.1f}) -> "
                      f"W1={vels[0]:+.1f} | W2={vels[1]:+.1f} | "
                      f"W3={vels[2]:+.1f} | W4={vels[3]:+.1f}")

if __name__ == "__main__":
    bot = BroneTracker()
    bot.run()