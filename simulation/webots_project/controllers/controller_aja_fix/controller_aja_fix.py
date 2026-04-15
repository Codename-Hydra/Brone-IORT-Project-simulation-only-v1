"""
BRONE TELEOP CLEAN
- Fitur: Kontrol Joystick untuk Robot Mecanum
- Kinematika: X-Drive (W1=FR, W2=FL, W3=BL, W4=BR)
- Tanpa Estimasi Energi (No DITER)
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import math
from controller import Robot

try:
    import pygame
except ImportError:
    print("CRITICAL: Pygame tidak terinstal. Install dengan 'sudo apt install python3-pygame'")

# Struktur data sederhana untuk kecepatan roda
class MotionStruct:
    def __init__(self):
        self.w1 = 0.0
        self.w2 = 0.0
        self.w3 = 0.0
        self.w4 = 0.0

class BroneTeleopClean:
    def __init__(self):
        # 1. Init Robot Webots
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # 2. Init Joystick (Pygame)
        pygame.init()
        pygame.joystick.init()
        self.js = None
        self.num_axes = 0
        self.num_buttons = 0
        
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            self.num_axes = self.js.get_numaxes()
            self.num_buttons = self.js.get_numbuttons()
            print(f">> JOYSTICK TERHUBUNG: {self.js.get_name()}")
        else:
            print("!! PERINGATAN: Tidak ada Joystick! Robot diam.")

        # 3. Parameter Kinematika Saja
        self.L = 0.208      # Jarak pusat ke roda (meter)
        self.R_WHEEL = 0.06 # Jari-jari roda (meter)
        self.MAX_SPEED_RAD = 20.0 # Limit kecepatan roda (rad/s)

        # 4. Init Motor (Tanpa Torque Feedback)
        self.wheels = []
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            if m is None:
                print(f"ERROR: Motor '{name}' tidak ditemukan!")
                continue
            m.setPosition(float('inf')) # Mode Velocity
            m.setVelocity(0.0)
            # Torque feedback dihapus karena tidak butuh DITER
            self.wheels.append(m)

        # 5. Konfigurasi Arah Putaran (Sesuai kalibrasi sebelumnya)
        self.INV_W1 = -1.0 # FR (Kanan)
        self.INV_W2 =  1.0 # FL (Kiri)
        self.INV_W3 =  1.0 # BL (Kiri)
        self.INV_W4 = -1.0 # BR (Kanan)

    def get_joystick_input(self):
        """Membaca input Joystick"""
        pygame.event.pump()
        if not self.js: return 0, 0, 0

        # Mapping Axis Standard
        raw_x = self.js.get_axis(0) 
        raw_y = self.js.get_axis(1)
        
        # Deadzone
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        # Mapping Tombol Putar (Sesuaikan Index Tombol Anda)
        # Button 6 (L2/L1) & 7 (R2/R1)
        btn_ccw = self.js.get_button(6) if self.num_buttons > 6 else 0
        btn_cw  = self.js.get_button(7) if self.num_buttons > 7 else 0
        
        raw_rot = 0.0
        if btn_ccw: raw_rot = 1.0
        if btn_cw:  raw_rot = -1.0

        # Gain Kecepatan (m/s)
        MAX_LIN = 1.0
        MAX_ROT = 1.5

        vx = raw_x * MAX_LIN
        vy = -raw_y * MAX_LIN # Invert Y (Atas = Positif)
        omega = raw_rot * MAX_ROT

        return vx, vy, omega

    def inverse_kinematics(self, vx, vy, omega):
        """Kinematika Mecanum X-Drive"""
        # Konversi Omega angular ke linear component
        v_omega = omega * self.L 

        # Hitung Kecepatan Linear Roda (m/s)
        v_fr = vy - vx + v_omega # Wheel 1
        v_fl = vy + vx - v_omega # Wheel 2
        v_bl = vy - vx - v_omega # Wheel 3
        v_br = vy + vx + v_omega # Wheel 4
        
        # Konversi ke Rad/s
        out = MotionStruct()
        out.w1 = v_fr / self.R_WHEEL
        out.w2 = v_fl / self.R_WHEEL
        out.w3 = v_bl / self.R_WHEEL
        out.w4 = v_br / self.R_WHEEL
        
        return out

    def clamp(self, val):
        if val > self.MAX_SPEED_RAD: return self.MAX_SPEED_RAD
        if val < -self.MAX_SPEED_RAD: return -self.MAX_SPEED_RAD
        return val

    def run(self):
        print("=== BRONE TELEOP (CLEAN) STARTED ===")
        print("Siap Dikendalikan via Joystick.")
        
        while self.robot.step(self.timestep) != -1:
            # 1. Baca Joystick
            vx, vy, omega = self.get_joystick_input()
            
            # 2. Hitung Kinematika
            vels = self.inverse_kinematics(vx, vy, omega)
            
            # 3. Kirim ke Motor
            self.wheels[0].setVelocity(self.clamp(vels.w1 * self.INV_W1))
            self.wheels[1].setVelocity(self.clamp(vels.w2 * self.INV_W2))
            self.wheels[2].setVelocity(self.clamp(vels.w3 * self.INV_W3))
            self.wheels[3].setVelocity(self.clamp(vels.w4 * self.INV_W4))

if __name__ == "__main__":
    controller = BroneTeleopClean()
    controller.run()