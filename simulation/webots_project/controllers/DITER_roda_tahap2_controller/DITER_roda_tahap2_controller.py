"""
BRONE DITER BATTERY MASTER - STATE PERSISTENCE
- Methodology: DITER + UVLO Protection + State Persistence (Save/Load)
- Fitur Baru: Pilih Mode Baterai saat Startup (L1: Resume, R1: Full Charge)
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
        self.CUTOFF_VOLTAGE = 19.8 
        self.R_INTERNAL = 0.15 
        
        # Energi Penuh (Kapasitas Maksimal)
        self.total_energy_capacity = (21.0 * (self.BATT_CAPACITY_MAH / 1000.0)) * 3600.0
        
        # Init energy sementara (akan di-overwrite oleh user selection)
        self.current_energy = self.total_energy_capacity 

        # --- B. SPESIFIKASI BEBAN & MOTOR ---
        self.P_STATIC = 8.0 
        self.I_IDLE = 0.25        
        self.I_STALL = 2.5        
        self.TORQUE_STALL = 1.96  
        self.K_T = self.TORQUE_STALL / self.I_STALL

        # --- C. KINEMATIKA & DEVICES ---
        self.INV_W1, self.INV_W2, self.INV_W3, self.INV_W4 = -1.0, -1.0, -1.0, -1.0
        self.L, self.r_wheel, self.sin_a, self.cos_a = 0.208, 0.06, 0.7071, 0.7071

        self.wheels = []
        for name in ['wheel1', 'wheel2', 'wheel3', 'wheel4']:
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
        else:
            print("!! WARNING: Joystick not found")

        self.last_log = 0.0
        self.avg_power_window = [] 

    def get_input(self):
        pygame.event.pump()
        if not self.js: return 0, 0, 0
        
        # Axis mapping
        raw_x = self.js.get_axis(0)
        raw_y = self.js.get_axis(1)
        raw_rot = 0.0
        if self.js.get_button(6): raw_rot = 1.0 # L1
        elif self.js.get_button(7): raw_rot = -1.0 # R1
        
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        return raw_x * -1.0, raw_y * 1.0, raw_rot * -2.0

    def invers_kinematics(self, vx, vy, w):
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        return [w1, w2, w3, w4]

    # --- FITUR BARU: SAVE & LOAD STATE ---
    def save_battery_state(self):
        """Menyimpan sisa energi (Joule) ke file"""
        try:
            with open(self.SAVE_FILE, "w") as f:
                f.write(str(self.current_energy))
        except Exception as e:
            print(f"Error saving state: {e}")

    def load_battery_state(self):
        """Membaca sisa energi dari file"""
        if not os.path.exists(self.SAVE_FILE):
            return None
        try:
            with open(self.SAVE_FILE, "r") as f:
                data = float(f.read())
                return data
        except:
            return None

    def wait_for_user_selection(self):
        """
        Looping di awal simulasi. Robot diam sampai user memilih mode baterai.
        L1 (Button 6) = Resume (Belum dicas)
        R1 (Button 7) = Reset (Full Charge)
        """
        print("\n=========================================")
        print("   SISTEM MANAJEMEN BATERAI BRONE (DITER)   ")
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
                return # Default full

            # Cek Button L1 (Index 6) -> Resume
            if self.js.get_button(4) or self.js.get_button(6): # Kadang L1 itu 4 atau 6 tergantung gamepad
                saved_energy = self.load_battery_state()
                if saved_energy is not None:
                    self.current_energy = saved_energy
                    p = (self.current_energy / self.total_energy_capacity) * 100
                    print(f"\n>> MODE DIPILIH: RESUME (Sisa Baterai: {p:.1f}%)")
                else:
                    print("\n>> INFO: Tidak ada file log lama. Memulai dengan 100%.")
                    self.current_energy = self.total_energy_capacity
                selected = True
                break

            # Cek Button R1 (Index 7) -> Full Charge
            elif self.js.get_button(5) or self.js.get_button(7): # Kadang R1 itu 5 atau 7
                self.current_energy = self.total_energy_capacity
                print(f"\n>> MODE DIPILIH: FULL CHARGE (Baterai di-reset ke 100%)")
                self.save_battery_state() # Reset file save juga
                selected = True
                break
            
            # Kedipkan teks atau tunggu sebentar agar CPU tidak panas
            # time.sleep(0.05) 

        if selected:
            # Beri jeda sedikit agar tombol tidak terdeteksi sebagai gerakan rotasi
            print("Memulai simulasi dalam 2 detik...")
            start_wait = self.robot.getTime()
            while self.robot.step(self.timestep) != -1:
                if self.robot.getTime() - start_wait > 2.0: break

    def calculate_diter_metrics(self, dt):
        # 1. Open Circuit Voltage berdasarkan SoC
        soc = max(0.0, self.current_energy / self.total_energy_capacity)
        v_open_circuit = 18.0 + (7.2 * soc)
        
        i_motors_total = 0.0
        for m in self.wheels:
            tau = abs(m.getTorqueFeedback())
            i_load = tau / self.K_T
            i_motors_total += (i_load + self.I_IDLE)

        # 2. Arus Beban Statis
        i_static_est = self.P_STATIC / v_open_circuit
        i_total_est = i_motors_total + i_static_est
        
        # 3. Voltage Drop
        v_terminal = v_open_circuit - (i_total_est * self.R_INTERNAL)
        if v_terminal < 0: v_terminal = 0.0
        
        if v_terminal > 0:
            i_static_real = self.P_STATIC / v_terminal
        else:
            i_static_real = 0
            
        i_total_real = i_motors_total + i_static_real
        total_power = v_terminal * i_total_real
        
        # 4. Kurangi Energi
        consumed_joules = total_power * dt
        self.current_energy -= consumed_joules
        
        # Update Window Estimasi
        self.avg_power_window.append(total_power)
        if len(self.avg_power_window) > (5.0 / dt): 
            self.avg_power_window.pop(0)
            
        return total_power, i_total_real, v_terminal

    def estimate_runtime(self):
        if len(self.avg_power_window) == 0: return 0
        avg_power = sum(self.avg_power_window) / len(self.avg_power_window)
        if avg_power < 1.0: return 9999 
        sisa_wh = self.current_energy / 3600.0
        return sisa_wh / avg_power

    def robot_stop(self):
        for w in self.wheels: w.setVelocity(0)

    def run(self):
        # 1. TUNGGU PILIHAN USER (L1/R1)
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

            # DITER Calc
            power, current, voltage = self.calculate_diter_metrics(dt)
            
            # Battery Stats & Safety
            batt_percent = max(0.0, (self.current_energy / self.total_energy_capacity) * 100.0)
            time_left = self.estimate_runtime()
            
            if voltage <= self.CUTOFF_VOLTAGE:
                print(f"\n!!! LOW VOLTAGE PROTECTION: {voltage:.2f}V !!!")
                self.robot_stop()
                self.save_battery_state() # Save kondisi mati
                break

            if self.current_energy <= 0:
                print("\n!!! ENERGY DEPLETED !!!")
                self.robot_stop()
                self.save_battery_state()
                break

            # Logging & Saving (Setiap 1 Detik)
            if t - self.last_log > 1.0:
                h = int(time_left)
                m = int((time_left - h) * 60)
                time_str = f"{h}h {m}m"
                
                print(f"T:{t:05.1f}s | V:{voltage:.2f}V | I:{current:.2f}A | "
                      f"P:{power:05.2f}W | Bat:{batt_percent:04.1f}% | Est:{time_str}")
                
                # --- AUTO SAVE SETIAP DETIK ---
                # Agar jika simulasi di-stop paksa, data tidak hilang
                self.save_battery_state()
                
                self.last_log = t

if __name__ == "__main__":
    bot = BroneDiterBattery()
    bot.run()