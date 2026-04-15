"""
BRONE DITER: FINAL FUSION (Control Tahap 3 + Full Physics Monitoring)
- Control: Joystick Pygame (Fixed Kinematics)
- Physics: DITER Battery Model (Voltage Sag, UVLO, Efficiency)
- Monitoring: Individual Wheel Torque, Volts, Amps, Watts, Runtime Est.
"""

import os
import time
import math
from controller import Robot

# Sembunyikan prompt support pygame
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

try:
    import pygame
except ImportError:
    print("CRITICAL: Pygame error. Install: sudo apt install python3-pygame")

class BroneDiterFusion:
    def __init__(self):
        # --- 1. INIT ROBOT & WEBOTS ---
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.SAVE_FILE = "brone_battery_state.txt"

        # --- 2. SPESIFIKASI BATERAI (2x LiPo 3S 5200mAh Seri) ---
        self.BATT_NOMINAL_VOLTAGE = 22.2 
        self.BATT_CAPACITY_MAH = 5200.0
        
        # Safety Settings
        self.CUTOFF_VOLTAGE = 18.5 
        self.R_INTERNAL = 0.05  # Resistansi internal baterai sehat
        
        # Konversi Kapasitas ke Joule
        # Rumus: (Nominal Voltage * (mAh/1000)) * 3600 detik
        self.total_energy_capacity = (21.0 * (self.BATT_CAPACITY_MAH / 1000.0)) * 3600.0
        self.current_energy = self.total_energy_capacity 

        # --- 3. SPESIFIKASI BEBAN & MOTOR ---
        self.P_STATIC = 8.0         # Beban statis (Raspberry Pi/Jetson + Sensors)
        self.DRIVER_EFFICIENCY = 0.92
        
        # Parameter Motor PG36 24V
        self.I_IDLE = 0.4         
        self.I_STALL = 6.0        
        self.TORQUE_STALL = 1.96  
        self.MAX_SPEED = 46.0     
        # Konstanta Torsi (Kt)
        self.K_T = self.TORQUE_STALL / (self.I_STALL - self.I_IDLE)

        # --- 4. KINEMATIKA (Mecanum) ---
        self.INV_W1 = -1.0
        self.INV_W2 = -1.0
        self.INV_W3 = -1.0
        self.INV_W4 = -1.0
        self.L = 0.208
        self.r_wheel = 0.06
        self.sin_a = 0.7071
        self.cos_a = 0.7071

        # --- 5. SETUP DEVICES ---
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            # [PENTING] Aktifkan Feedback Torsi
            m.enableTorqueFeedback(self.timestep)
            self.wheels.append(m)

        # --- 6. JOYSTICK ---
        pygame.init()
        pygame.joystick.init()
        self.js = None
        if pygame.joystick.get_count() > 0:
            self.js = pygame.joystick.Joystick(0)
            self.js.init()
            print(f">> SYSTEM READY: {self.js.get_name()}")
        else:
            print("!! WARNING: Joystick not found")

        # Logging helper
        self.last_log = 0.0
        self.avg_power_window = [] 

    def get_input(self):
        """Mengambil input joystick (Control Logic Tahap 3)"""
        pygame.event.pump()
        if not self.js: return 0, 0, 0

        raw_x = self.js.get_axis(0)
        raw_y = self.js.get_axis(1)
        raw_rot = 0.0
        
        # Button mapping untuk rotasi
        if self.js.get_button(6): raw_rot = 1.0
        elif self.js.get_button(7): raw_rot = -1.0
        
        # Deadzone
        if abs(raw_x) < 0.1: raw_x = 0.0
        if abs(raw_y) < 0.1: raw_y = 0.0

        # Mapping arah (sesuai request Tahap 3)
        vx = raw_x * -1.0  
        vy = raw_y * 1.0   
        theta = raw_rot * -2.0

        return vx, vy, theta

    def invers_kinematics(self, vx, vy, w):
        """Menghitung kecepatan masing-masing roda"""
        w1 = (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        w2 = (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w3 = ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel
        w4 = ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
        return [w1, w2, w3, w4]

    # --- SAVE & LOAD SYSTEM ---
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
        """Menu interaktif di awal simulasi"""
        print("\n=========================================")
        print("   SISTEM MONITORING & KONTROL BRONE     ")
        print("   Mode: FUSION (Physics + Torsi Monitor)")
        print("=========================================")
        print("Pilih Status Baterai Awal:")
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
                    print(f"\n>> RESUME SIMULASI: Sisa Baterai {p:.1f}%")
                else:
                    print("\n>> INFO: Data lama tidak ditemukan. Reset 100%.")
                    self.current_energy = self.total_energy_capacity
                selected = True
                break

            # Button R1 (Reset/Full)
            elif self.js.get_button(5) or self.js.get_button(7): 
                self.current_energy = self.total_energy_capacity
                print(f"\n>> FULL CHARGE: Reset Baterai ke 100%")
                self.save_battery_state()
                selected = True
                break
            
        if selected:
            # Delay sedikit agar user siap
            start_wait = self.robot.getTime()
            while self.robot.step(self.timestep) != -1:
                if self.robot.getTime() - start_wait > 1.0: break

    def calculate_diter_metrics(self, dt):
        """
        Inti perhitungan Fisika:
        Mengembalikan: Power, Arus Total, Voltase Terminal, List Torsi Roda
        """
        # 1. Open Circuit Voltage (Voc) berdasarkan State of Charge (SoC)
        soc = max(0.0, self.current_energy / self.total_energy_capacity)
        v_open_circuit = 18.0 + (7.2 * soc)
        
        # 2. Hitung Beban Motor & Torsi Individual
        i_motors_pure = 0.0
        individual_torques = [] # Menyimpan data torsi per roda

        for m in self.wheels:
            # Baca torsi aktual dari Webots Physics Engine
            tau = m.getTorqueFeedback()
            individual_torques.append(tau) # Simpan untuk display
            
            # Konversi Torsi ke Arus (Model DC Motor)
            # Arus = (Torsi / Kt) + Arus_Idle
            i_load = abs(tau) / self.K_T
            i_motors_pure += (i_load + self.I_IDLE)

        # 3. Hitung Arus Input (memperhitungkan efisiensi driver BTS7960)
        i_motors_drawn = i_motors_pure / self.DRIVER_EFFICIENCY

        # 4. Hitung Arus Statis (Constant Power Load stabil)
        i_static_stable = self.P_STATIC / v_open_circuit
        
        # Total Arus yang ditarik dari baterai
        i_total_drawn = i_motors_drawn + i_static_stable
        
        # 5. Voltage Drop (DITER Equation: V_term = Voc - I*R)
        v_terminal = v_open_circuit - (i_total_drawn * self.R_INTERNAL)
        
        if v_terminal < 0: v_terminal = 0.0
            
        # 6. Hitung Konsumsi Energi
        total_power = v_terminal * i_total_drawn
        consumed_joules = total_power * dt
        self.current_energy -= consumed_joules
        
        # Update rata-rata power untuk estimasi waktu
        self.avg_power_window.append(total_power)
        if len(self.avg_power_window) > (5.0 / dt): 
            self.avg_power_window.pop(0)
            
        return total_power, i_total_drawn, v_terminal, individual_torques

    def estimate_runtime(self):
        """Estimasi sisa waktu dalam jam"""
        if len(self.avg_power_window) == 0: return 0
        avg_power = sum(self.avg_power_window) / len(self.avg_power_window)
        if avg_power < 1.0: return 9999 
        sisa_wh = self.current_energy / 3600.0
        return sisa_wh / avg_power

    def robot_stop(self):
        for w in self.wheels: w.setVelocity(0)

    def run(self):
        # Menu Pilih Cas/Resume
        self.wait_for_user_selection()

        print("\n=== BRONE DITER: SIMULATION ACTIVE ===")
        print("Format Log: [Torsi W1..W4] | Volt | Amp | Power | Batt% | Est.Waktu")
        
        while self.robot.step(self.timestep) != -1:
            t = self.robot.getTime()
            dt = self.timestep / 1000.0
            
            # --- A. CONTROL (Tahap 3) ---
            vx, vy, w = self.get_input()
            vels = self.invers_kinematics(vx, vy, w)
            
            # Set Velocity dengan Clamping max speed
            self.wheels[0].setVelocity(max(min(vels[0] * self.INV_W1, 46), -46))
            self.wheels[1].setVelocity(max(min(vels[1] * self.INV_W2, 46), -46))
            self.wheels[2].setVelocity(max(min(vels[2] * self.INV_W3, 46), -46))
            self.wheels[3].setVelocity(max(min(vels[3] * self.INV_W4, 46), -46))

            # --- B. PHYSICS & MONITORING ---
            power, current, voltage, torques = self.calculate_diter_metrics(dt)
            
            # Battery Stats
            batt_percent = max(0.0, (self.current_energy / self.total_energy_capacity) * 100.0)
            time_left = self.estimate_runtime()
            
            # --- C. SAFETY CHECKS ---
            if voltage <= self.CUTOFF_VOLTAGE:
                print(f"\n!!! LOW VOLTAGE PROTECTION: {voltage:.2f}V !!!")
                self.robot_stop()
                self.save_battery_state() 
                break

            if self.current_energy <= 0:
                print("\n!!! ENERGY DEPLETED !!!")
                self.robot_stop()
                self.save_battery_state()
                break

            # --- D. LOGGING DISPLAY ---
            if t - self.last_log > 0.5: # Update setiap 0.5 detik
                # Format Estimasi Waktu
                if time_left > 100:
                    time_str = ">99h"
                else:
                    h = int(time_left)
                    m = int((time_left - h) * 60)
                    time_str = f"{h}h {m}m"

                # Format Torsi Array ke String rapi
                tau_str = " ".join([f"{val:+5.2f}" for val in torques])
                
                # Print Satu Baris Lengkap
                print(f"T:{t:05.1f} | Tau:[{tau_str}] Nm | {voltage:5.2f}V | {current:5.2f}A | {power:06.2f}W | Bat:{batt_percent:04.1f}% | Est:{time_str}")
                
                self.save_battery_state()
                self.last_log = t

if __name__ == "__main__":
    bot = BroneDiterFusion()
    bot.run()