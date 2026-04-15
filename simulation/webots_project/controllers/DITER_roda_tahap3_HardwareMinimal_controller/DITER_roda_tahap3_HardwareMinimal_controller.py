"""
BRONE DITER BATTERY MASTER - TAHAP 5 (STABILIZED)
- Methodology: DITER (Voltage Sag + Kt Logic + UVLO + Efficiency Loss)
- Fix: Menurunkan R_Internal & Cutoff agar tahan terhadap Spike arus awal
- Fix: Stabilisasi rumus Constant Power Load untuk mencegah crash matematika
"""

import os
import time
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
        
        # Nama file untuk menyimpan state baterai
        self.SAVE_FILE = "brone_battery_state.txt"

        # --- A. SPESIFIKASI BATERAI (2x LiPo 3S 5200mAh Seri) ---
        self.BATT_NOMINAL_VOLTAGE = 22.2 
        self.BATT_CAPACITY_MAH = 5200.0
        
        # --- TUNING STABILITAS (FIXED) ---
        # Batas aman software diturunkan sedikit untuk toleransi spike sesaat
        self.CUTOFF_VOLTAGE = 18.5 
        
        # DITER PARAMETER: Internal Resistance
        # Diubah ke 0.05 Ohm (Simulasi Baterai High C-Rating yang sehat)
        # Nilai 0.15 sebelumnya terlalu resistif untuk 4 motor sekaligus
        self.R_INTERNAL = 0.05 
        
        # Konversi ke Energi Total (Joule)
        self.total_energy_capacity = (21.0 * (self.BATT_CAPACITY_MAH / 1000.0)) * 3600.0
        
        # Init energy sementara
        self.current_energy = self.total_energy_capacity 

        # --- B. SPESIFIKASI BEBAN ELEKTRONIK ---
        self.P_STATIC = 8.0 # Watt (Orange Pi 5 + ESP32)

        # --- C. SPESIFIKASI MOTOR DRIVER (BTS7960) ---
        self.DRIVER_EFFICIENCY = 0.92

        # --- D. SPESIFIKASI MOTOR (PG36 24V) ---
        self.I_IDLE = 0.4         
        self.I_STALL = 6.0        
        self.TORQUE_STALL = 1.96  
        self.MAX_SPEED = 46.0     
        self.K_T = self.TORQUE_STALL / (self.I_STALL - self.I_IDLE)

        # --- E. KINEMATIKA ---
        self.INV_W1 = -1.0
        self.INV_W2 = -1.0
        self.INV_W3 = -1.0
        self.INV_W4 = -1.0
        self.L = 0.208
        self.r_wheel = 0.06
        self.sin_a = 0.7071
        self.cos_a = 0.7071

        # --- F. INIT DEVICES ---
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            m.enableTorqueFeedback(self.timestep)
            self.wheels.append(m)

        # Joystick
        pygame.init()
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            print(f">> SYSTEM READY: {self.js.get_name()}")
            print(f">> DITER MODEL: Active (Stabilized Logic)")
        else:
            print("!! WARNING: Joystick not found")

        self.last_log = 0.0
        self.avg_power_window = [] 

    def get_input(self):
        pygame.event.pump()
        if not self.js: return 0, 0, 0

        raw_x = self.js.get_axis(0)
        raw_y = self.js.get_axis(1)
        raw_rot = 0.0
        
        if self.js.get_button(6): raw_rot = 1.0
        elif self.js.get_button(7): raw_rot = -1.0
        
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        vx = raw_x * -1.0  
        vy = raw_y * 1.0   
        theta = raw_rot * -2.0

        return vx, vy, theta

    def invers_kinematics(self, vx, vy, w):
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        return [w1, w2, w3, w4]

    # --- SAVE & LOAD STATE ---
    def save_battery_state(self):
        try:
            with open(self.SAVE_FILE, "w") as f:
                f.write(str(self.current_energy))
        except Exception as e:
            print(f"Error saving state: {e}")

    def load_battery_state(self):
        if not os.path.exists(self.SAVE_FILE):
            return None
        try:
            with open(self.SAVE_FILE, "r") as f:
                return float(f.read())
        except:
            return None

    def wait_for_user_selection(self):
        print("\n=========================================")
        print("   SISTEM MANAJEMEN BATERAI BRONE (DITER)   ")
        print("   Status: STABILIZED VERSION               ")
        print("=========================================")
        print("Silakan Pilih Status Baterai Awal:")
        print("  [L1] -> BELUM DICAS (Resume Log Terakhir)")
        print("  [R1] -> SUDAH DICAS (Reset ke 100%)")
        print("-----------------------------------------")
        print("Menunggu input joystick...")

        selected = False
        while self.robot.step(self.timestep) != -1:
            pygame.event.pump()
            if not self.js: 
                print("Error: Joystick tidak terdeteksi. Default ke 100%.")
                return 

            # Button L1 (Resume)
            if self.js.get_button(4) or self.js.get_button(6): 
                saved_energy = self.load_battery_state()
                if saved_energy is not None:
                    self.current_energy = saved_energy
                    p = (self.current_energy / self.total_energy_capacity) * 100
                    print(f"\n>> MODE DIPILIH: RESUME (Sisa Baterai: {p:.1f}%)")
                else:
                    print("\n>> INFO: Data lama tidak ditemukan. Mulai 100%.")
                    self.current_energy = self.total_energy_capacity
                selected = True
                break

            # Button R1 (Reset/Full)
            elif self.js.get_button(5) or self.js.get_button(7): 
                self.current_energy = self.total_energy_capacity
                print(f"\n>> MODE DIPILIH: FULL CHARGE (Reset ke 100%)")
                self.save_battery_state()
                selected = True
                break
            
        if selected:
            print("Memulai simulasi dalam 1 detik...")
            start_wait = self.robot.getTime()
            while self.robot.step(self.timestep) != -1:
                if self.robot.getTime() - start_wait > 1.0: break

    def calculate_diter_metrics(self, dt):
        """
        DITER ADVANCED CALCULATION (Stabilized)
        """
        # 1. Open Circuit Voltage (Voc)
        soc = max(0.0, self.current_energy / self.total_energy_capacity)
        v_open_circuit = 18.0 + (7.2 * soc)
        
        # 2. Arus Motor Murni (Physics Based)
        i_motors_pure = 0.0
        for m in self.wheels:
            tau = abs(m.getTorqueFeedback())
            i_load = tau / self.K_T
            i_motors_pure += (i_load + self.I_IDLE)

        # 3. Arus Input Motor (Efisiensi Driver)
        i_motors_drawn = i_motors_pure / self.DRIVER_EFFICIENCY

        # 4. Arus Beban Statis (STABILIZED CALCULATION)
        # Menggunakan v_open_circuit (stabil) sebagai pembagi, bukan v_terminal (fluktuatif)
        # Ini mencegah "Feedback Loop" matematika yang menyebabkan voltage crash
        i_static_stable = self.P_STATIC / v_open_circuit
        
        # Total Arus yang keluar dari Baterai
        i_total_drawn = i_motors_drawn + i_static_stable
        
        # 5. Voltage Drop (DITER Eq 12)
        v_terminal = v_open_circuit - (i_total_drawn * self.R_INTERNAL)
        
        # Safety clamp agar voltase tidak negatif dalam simulasi ekstrem
        if v_terminal < 0: v_terminal = 0.0
            
        # 6. Hitung Daya & Energi
        total_power = v_terminal * i_total_drawn
        consumed_joules = total_power * dt
        self.current_energy -= consumed_joules
        
        # Update Window
        self.avg_power_window.append(total_power)
        if len(self.avg_power_window) > (5.0 / dt): 
            self.avg_power_window.pop(0)
            
        return total_power, i_total_drawn, v_terminal

    def estimate_runtime(self):
        if len(self.avg_power_window) == 0: return 0
        avg_power = sum(self.avg_power_window) / len(self.avg_power_window)
        if avg_power < 1.0: return 9999 
        sisa_wh = self.current_energy / 3600.0
        return sisa_wh / avg_power

    def robot_stop(self):
        for w in self.wheels: w.setVelocity(0)

    def run(self):
        self.wait_for_user_selection()

        print("\n=== BRONE DITER: SIMULATION ACTIVE ===")
        print("Log: Waktu | Voltase | Arus Total | Daya Total | Baterai % | Status")
        
        while self.robot.step(self.timestep) != -1:
            t = self.robot.getTime()
            dt = self.timestep / 1000.0
            
            # Control Logic
            vx, vy, w = self.get_input()
            vels = self.invers_kinematics(vx, vy, w)
            
            self.wheels[0].setVelocity(max(min(vels[0] * self.INV_W1, 46), -46))
            self.wheels[1].setVelocity(max(min(vels[1] * self.INV_W2, 46), -46))
            self.wheels[2].setVelocity(max(min(vels[2] * self.INV_W3, 46), -46))
            self.wheels[3].setVelocity(max(min(vels[3] * self.INV_W4, 46), -46))

            # DITER Calculation
            power, current, voltage = self.calculate_diter_metrics(dt)
            
            # Battery Stats
            batt_percent = max(0.0, (self.current_energy / self.total_energy_capacity) * 100.0)
            time_left = self.estimate_runtime()
            
            # --- UVLO SAFETY CHECK (Stabilized) ---
            if voltage <= self.CUTOFF_VOLTAGE:
                print(f"\n!!! LOW VOLTAGE PROTECTION: {voltage:.2f}V !!!")
                print("!!! BATTERY CRITICAL - SHUTDOWN !!!")
                self.robot_stop()
                self.save_battery_state() 
                break

            if self.current_energy <= 0:
                print("\n!!! ENERGY DEPLETED !!!")
                self.robot_stop()
                self.save_battery_state()
                break

            # Logging & Saving
            if t - self.last_log > 1.0:
                h = int(time_left)
                m = int((time_left - h) * 60)
                time_str = f"{h}h {m}m"
                
                print(f"T:{t:05.1f}s | V:{voltage:.2f}V | I:{current:.2f}A | "
                      f"P:{power:05.2f}W | Bat:{batt_percent:04.1f}% | Est:{time_str}")
                
                self.save_battery_state()
                self.last_log = t

if __name__ == "__main__":
    bot = BroneDiterBattery()
    bot.run()