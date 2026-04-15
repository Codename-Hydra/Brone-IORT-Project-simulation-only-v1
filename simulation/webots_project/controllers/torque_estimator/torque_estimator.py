"""
BRONE FINAL DITER (Control + Physics Data)
- Kinematika: Porting C++ (Fixed Direction)
- Fisika: Monitoring Torsi & Estimasi Daya (PG36)
- Input: Joystick Pygame
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import math
from controller import Robot

try:
    import pygame
except ImportError:
    print("CRITICAL: Pygame error. Install: sudo apt install python3-pygame")

class BroneDiter:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # --- 1. PARAMETER FISIK (PG36 24V) ---
        self.V_SUPPLY = 24.0      # Volt
        self.I_IDLE = 0.25        # Ampere (No Load)
        self.I_STALL = 2.5        # Ampere (Max Load)
        self.TORQUE_STALL = 1.96  # N.m (20 kgf.cm)
        self.MAX_SPEED = 46.0     # Rad/s (~440 RPM)

        # --- 2. KALIBRASI ARAH (FIXED) ---
        # Berdasarkan tes Anda: Semua roda perlu di-invert (-1.0)
        self.INV_W1 = -1.0
        self.INV_W2 = -1.0
        self.INV_W3 = -1.0
        self.INV_W4 = -1.0

        # --- 3. SETUP MOTOR & SENSOR ---
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            
            # [PENTING] Aktifkan Feedback Torsi untuk DITER
            m.enableTorqueFeedback(self.timestep)
            
            self.wheels.append(m)

        # --- 4. KINEMATIKA ---
        self.L = 0.208      
        self.r_wheel = 0.06 
        self.sin_a = 0.7071
        self.cos_a = 0.7071

        # --- 5. JOYSTICK ---
        pygame.init()
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            print(f">> DITER SIAP: {self.js.get_name()}")
        else:
            print("!! WARNING: Joystick tidak ditemukan.")

        # Stats
        self.total_energy = 0.0
        self.last_log = 0.0

    def get_input(self):
        pygame.event.pump()
        if not self.js: return 0, 0, 0

        # Mapping: Axis 0 (X), Axis 1 (Y)
        raw_x = self.js.get_axis(0)
        raw_y = self.js.get_axis(1)
        
        raw_rot = 0.0
        # Button 6 (L1) & 7 (R1)
        if self.js.get_button(6): raw_rot = 1.0   # Kiri
        elif self.js.get_button(7): raw_rot = -1.0 # Kanan
        
        # Deadzone
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        # Gain
        VEL_GAIN = 1.0 
        ROT_GAIN = 2.0

        vx = raw_x * VEL_GAIN
        vy = -raw_y * VEL_GAIN 
        theta = raw_rot * ROT_GAIN

        return vx, vy, theta

    def invers_kinematic_cpp(self, vx, vy, vtheta):
        """Rumus C++ Asli"""
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * vtheta) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * vtheta) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * vtheta) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * vtheta) / self.r_wheel
        return [w1, w2, w3, w4]

    def calculate_physics(self):
        """
        Menghitung Torsi Aktual -> Arus -> Daya
        Mengembalikan: (Total Daya, List Torsi per Roda)
        """
        i_total = 0.0
        torques = []

        for m in self.wheels:
            # 1. Baca Torsi Fisika dari Webots (Load Aktual)
            tau = m.getTorqueFeedback()
            torques.append(tau)
            
            # 2. Model Motor DC (Linear Interpolation)
            # Arus = Arus_Diam + (Persentase_Torsi * (Arus_Macet - Arus_Diam))
            load_ratio = min(abs(tau) / self.TORQUE_STALL, 1.0)
            current = self.I_IDLE + (load_ratio * (self.I_STALL - self.I_IDLE))
            
            i_total += current

        power = self.V_SUPPLY * i_total
        return power, torques

    def clamp(self, val):
        if val > self.MAX_SPEED: return self.MAX_SPEED
        if val < -self.MAX_SPEED: return -self.MAX_SPEED
        return val

    def run(self):
        print("=== BRONE DITER RUNNING ===")
        print("Log Format: [Torsi W1..W4] | Daya (W) | Energi (J)")
        
        while self.robot.step(self.timestep) != -1:
            t = self.robot.getTime()

            # 1. Input & Gerak
            vx, vy, w = self.get_input()
            raw_vels = self.invers_kinematic_cpp(vx, vy, w)
            
            self.wheels[0].setVelocity(self.clamp(raw_vels[0] * self.INV_W1))
            self.wheels[1].setVelocity(self.clamp(raw_vels[1] * self.INV_W2))
            self.wheels[2].setVelocity(self.clamp(raw_vels[2] * self.INV_W3))
            self.wheels[3].setVelocity(self.clamp(raw_vels[3] * self.INV_W4))

            # 2. Hitung Fisika (DITER)
            power, torques = self.calculate_physics()
            
            # Akumulasi Energi (Joule = Watt * detik)
            dt = self.timestep / 1000.0
            self.total_energy += power * dt

            # 3. Logging (Tiap 0.5 detik)
            if t - self.last_log > 0.5:
                # Format Torsi: 2 angka desimal
                t_str = " ".join([f"{val:+5.2f}" for val in torques])
                
                print(f"T:{t:04.1f} | Tau:[{t_str}] Nm | Pwr:{power:05.1f}W | Bat:{self.total_energy:.1f}J")
                self.last_log = t

if __name__ == "__main__":
    bot = BroneDiter()
    bot.run()