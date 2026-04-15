"""
BRONE DITER BATTERY MASTER
- Kinematika: Calibrated (All Inverted)
- Hardware Model: PG36 Motor + Orange Pi 5 Pro + ESP32
- Battery Model: 2x 11.1V 5200mAh (Series) -> 22.2V 5200mAh
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import math
from controller import Robot

try:
    import pygame
except ImportError:
    print("CRITICAL: Pygame error. Install: sudo apt install python3-pygame")

class BroneDiterBattery:
    def __init__(self):
        # 1. Init Robot
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())

        # --- A. SPESIFIKASI BATERAI (2x LiPo 3S 5200mAh Seri) ---
        # Tegangan Nominal: 11.1V x 2 = 22.2 Volt
        # Kapasitas Arus: Tetap 5200 mAh (Karena Seri)
        self.BATT_VOLTAGE = 22.2 
        self.BATT_CAPACITY_MAH = 5200.0
        
        # Konversi ke Energi Total (Joule) untuk simulasi
        # Wh = V * Ah
        # Joule = Wh * 3600
        self.total_energy_capacity = (self.BATT_VOLTAGE * (self.BATT_CAPACITY_MAH / 1000.0)) * 3600.0
        self.current_energy = self.total_energy_capacity # Mulai penuh (100%)

        # --- B. SPESIFIKASI BEBAN ELEKTRONIK (Static Load) ---
        # Orange Pi 5 Pro (Idle/Avg Load) + ESP32 + USB TTL + Driver Logic
        # OPi5: ~5-7W, ESP32: ~0.5W, Others: ~0.5W
        self.P_STATIC = 8.0 # Watt

        # --- C. SPESIFIKASI MOTOR (PG36 24V) ---
        self.I_IDLE = 0.25        # Ampere
        self.I_STALL = 2.5        # Ampere
        self.TORQUE_STALL = 1.96  # N.m
        self.MAX_SPEED = 46.0     # Rad/s

        # --- D. SETUP KINEMATIKA (Fixed Calibration) ---
        self.INV_W1 = -1.0
        self.INV_W2 = -1.0
        self.INV_W3 = -1.0
        self.INV_W4 = -1.0
        
        # Geometri
        self.L = 0.208
        self.r_wheel = 0.06
        self.sin_a = 0.7071
        self.cos_a = 0.7071

        # --- E. INIT DEVICES ---
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            m.enableTorqueFeedback(self.timestep) # Wajib untuk DITER
            self.wheels.append(m)

        # Joystick
        pygame.init()
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            print(f">> SYSTEM READY: {self.js.get_name()}")
            print(f">> BATTERY PROFILE: {self.BATT_VOLTAGE}V {self.BATT_CAPACITY_MAH}mAh")
        else:
            print("!! WARNING: Joystick not found")

        self.last_log = 0.0
        self.avg_power_window = [] # Untuk estimasi sisa waktu

    def get_input(self):

        pygame.event.pump()
        if not self.js: return 0, 0, 0

        raw_x = self.js.get_axis(0)
        raw_y = self.js.get_axis(1)
        
        raw_rot = 0.0
        # Button 6 (L1) & 7 (R1)
        if self.js.get_button(6): raw_rot = 1.0
        elif self.js.get_button(7): raw_rot = -1.0
        
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        # --- REVISI INVERS KONTROL ---
        # Awalnya: vx = raw_x * 1.0, sekarang dikali -1.0
        vx = raw_x * -1.0  
        
        # Awalnya: vy = -raw_y * 1.0, sekarang dikali -1.0 jadi positif
        # (Ingat: Axis Y joystick biasanya terbalik, atas negatif. Jadi kalau mau invers "maju jadi mundur", kita balik logikanya)
        # Logika Asli: Atas (Y-) -> Vy Positif (Maju).
        # Logika Invers: Atas (Y-) -> Vy Negatif (Mundur).
        # Jadi rumusnya menjadi:
        vy = raw_y * 1.0   

        # Awalnya: theta = raw_rot * 2.0, sekarang dikali -1.0
        theta = raw_rot * -2.0

        return vx, vy, theta

    def invers_kinematics(self, vx, vy, w):
        # Rumus C++ Original
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        return [w1, w2, w3, w4]

    def calculate_diter_metrics(self, dt):
        """
        Inti dari DITER: Menghitung konsumsi energi fisika + elektronik
        """
        i_motors = 0.0
        
        # 1. Hitung Arus Motor Dinamis (Physics-Based)
        for m in self.wheels:
            tau = abs(m.getTorqueFeedback())
            # Rumus Linear Load: I = I_idle + (Torsi/Torsi_Stall * (I_stall - I_idle))
            load_ratio = min(tau / self.TORQUE_STALL, 1.0)
            current = self.I_IDLE + (load_ratio * (self.I_STALL - self.I_IDLE))
            i_motors += current

        # 2. Hitung Daya Total (P = V*I + P_static)
        # Tegangan pakai nominal baterai (22.2V)
        power_dynamic = self.BATT_VOLTAGE * i_motors
        total_power = power_dynamic + self.P_STATIC
        
        # 3. Kurangi Kapasitas Baterai (Joule counting)
        consumed_joules = total_power * dt
        self.current_energy -= consumed_joules
        
        # Update rata-rata untuk estimasi waktu (Moving Average 5 detik)
        self.avg_power_window.append(total_power)
        if len(self.avg_power_window) > (5.0 / dt): 
            self.avg_power_window.pop(0)
            
        return total_power, i_motors

    def estimate_runtime(self):
        """Estimasi sisa waktu berdasarkan rata-rata penggunaan daya terkini"""
        if len(self.avg_power_window) == 0: return 0
        avg_power = sum(self.avg_power_window) / len(self.avg_power_window)
        
        if avg_power < 1.0: return 9999 # Infinite jika diam
        
        # Sisa Waktu (Jam) = Sisa Energi (Wh) / Daya Rata2 (W)
        sisa_wh = self.current_energy / 3600.0
        hours_left = sisa_wh / avg_power
        return hours_left

    def run(self):
        print("=== BRONE DITER: BATTERY SIMULATION STARTED ===")
        print("Log: Waktu | Daya Total | Baterai % | Est. Sisa Waktu")
        
        while self.robot.step(self.timestep) != -1:
            t = self.robot.getTime()
            dt = self.timestep / 1000.0
            
            # 1. Control
            vx, vy, w = self.get_input()
            vels = self.invers_kinematics(vx, vy, w)
            
            self.wheels[0].setVelocity(max(min(vels[0] * self.INV_W1, 46), -46))
            self.wheels[1].setVelocity(max(min(vels[1] * self.INV_W2, 46), -46))
            self.wheels[2].setVelocity(max(min(vels[2] * self.INV_W3, 46), -46))
            self.wheels[3].setVelocity(max(min(vels[3] * self.INV_W4, 46), -46))

            # 2. DITER Calculation
            power, current = self.calculate_diter_metrics(dt)
            
            # 3. Battery Stats
            batt_percent = (self.current_energy / self.total_energy_capacity) * 100.0
            time_left = self.estimate_runtime()
            
            # 4. Logging (Tiap 1 Detik)
            if t - self.last_log > 1.0:
                # Format waktu sisa (Jam:Menit)
                h = int(time_left)
                m = int((time_left - h) * 60)
                time_str = f"{h}h {m}m"
                
                print(f"T:{t:05.1f}s | Pwr:{power:06.2f}W (I_mot:{current:.1f}A) | "
                      f"Batt: {batt_percent:05.1f}% | Sisa: {time_str}")
                
                self.last_log = t
                
            if self.current_energy <= 0:
                print("!!! BATERAI HABIS - ROBOT MATI !!!")
                # Stop robot
                for w in self.wheels: w.setVelocity(0)
                break

if __name__ == "__main__":
    bot = BroneDiterBattery()
    bot.run()