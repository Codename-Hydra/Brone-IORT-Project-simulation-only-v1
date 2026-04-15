"""
BRONE FINAL EXECUTION (Mapped & Calibrated)
- Mapping Roda: Sesuai observasi user (W1=FR, W2=FL, W3=BL, W4=BR)
- Kinematika: Mecanum X-Drive Standar
- Fitur: DITER (Estimasi Daya)
"""

from controller import Robot
import math

class BroneRobot:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # --- 1. KONFIGURASI MAPPING (Sesuai Data Anda) ---
        # Index Motor di Array: 0=Wheel1, 1=Wheel2, dst.
        self.IDX_FR = 0  # Wheel 1: Depan Kanan
        self.IDX_FL = 1  # Wheel 2: Depan Kiri
        self.IDX_BL = 2  # Wheel 3: Belakang Kiri
        self.IDX_BR = 3  # Wheel 4: Belakang Kanan
        
        # --- 2. KONFIGURASI ARAH (DIRECTION) ---
        # Sisi Kanan (FR & BR) biasanya perlu di-invert (-1.0) agar maju = positif
        # Sisi Kiri (FL & BL) biasanya normal (1.0)
        self.INV_FR = -1.0 
        self.INV_BR = -1.0
        self.INV_FL =  1.0
        self.INV_BL =  1.0
        
        # --- 3. PARAMETER FISIK (DITER) ---
        self.V_SUPPLY = 24.0
        self.I_IDLE = 0.25
        self.I_STALL = 2.5
        self.TORQUE_STALL = 1.96
        self.MAX_SPEED_RAD = 20.0 # Limit kecepatan (rad/s)

        # Init Motor
        self.wheels = []
        names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        for name in names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            m.enableTorqueFeedback(self.timestep)
            self.wheels.append(m)
            
        self.total_energy = 0.0
        self.last_log = 0.0

    def drive_mecanum(self, vx, vy, omega):
        """
        Rumus Kinematika Mecanum (Global Standard)
        vx: Geser Samping (Kanan +, Kiri -)
        vy: Maju Mundur (Maju +, Mundur -)
        omega: Putar (CCW +, CW -)
        """
        # Rumus Vektor Roda
        # Front Left (FL)  = vy - vx - omega
        # Front Right (FR) = vy + vx + omega
        # Back Left (BL)   = vy + vx - omega
        # Back Right (BR)  = vy - vx + omega
        
        # Catatan: Tanda +/- pada vx/omega bisa variatif tergantung frame robot.
        # Kita mulai dengan konfigurasi paling umum.
        
        v_fl = vy + vx - omega
        v_fr = vy - vx + omega
        v_bl = vy - vx - omega
        v_br = vy + vx + omega
        
        # Normalisasi (Agar tidak melebihi kecepatan maksimum)
        max_val = max(abs(v_fl), abs(v_fr), abs(v_bl), abs(v_br))
        scale = 1.0
        if max_val > 1.0:
            scale = 1.0 / max_val
            
        # Kirim ke Motor dengan Mapping & Inversi yang Benar
        # Perhatikan penggunaan self.IDX_... untuk memilih roda yang tepat
        self.wheels[self.IDX_FL].setVelocity(v_fl * scale * self.MAX_SPEED_RAD * self.INV_FL)
        self.wheels[self.IDX_FR].setVelocity(v_fr * scale * self.MAX_SPEED_RAD * self.INV_FR)
        self.wheels[self.IDX_BL].setVelocity(v_bl * scale * self.MAX_SPEED_RAD * self.INV_BL)
        self.wheels[self.IDX_BR].setVelocity(v_br * scale * self.MAX_SPEED_RAD * self.INV_BR)

    def calc_power(self):
        itotal = 0
        for m in self.wheels:
            tau = abs(m.getTorqueFeedback())
            ratio = min(tau/self.TORQUE_STALL, 1.0)
            itotal += self.I_IDLE + (ratio * (self.I_STALL - self.I_IDLE))
        return itotal * self.V_SUPPLY

    def run(self):
        print("=== BRONE FINAL MOVEMENT TEST ===")
        print("Skenario: Maju -> Mundur -> Kiri -> Kanan -> Putar -> Serong")
        
        while self.robot.step(self.timestep) != -1:
            t = self.robot.getTime()
            
            vx, vy, w = 0, 0, 0
            status = "DIAM"
            
            # --- SKENARIO UJI JALAN (Sequence) ---
            if 1.0 < t <= 3.0:
                status = "MAJU"
                vy = 0.5
            elif 4.0 < t <= 6.0:
                status = "MUNDUR"
                vy = -0.5
            elif 7.0 < t <= 9.0:
                status = "GESER KANAN"
                vx = 0.5
            elif 10.0 < t <= 12.0:
                status = "GESER KIRI"
                vx = -0.5
            elif 13.0 < t <= 15.0:
                status = "PUTAR KIRI (CCW)"
                w = 1.0
            elif 16.0 < t <= 18.0:
                status = "PUTAR KANAN (CW)"
                w = -1.0
            elif 19.0 < t <= 22.0:
                status = "SERONG KANAN DEPAN"
                vx = 0.3
                vy = 0.3
            elif t > 22.0:
                status = "SELESAI"
                vx, vy, w = 0, 0, 0
            
            # Eksekusi
            self.drive_mecanum(vx, vy, w)
            
            # Log DITER
            pwr = self.calc_power()
            self.total_energy += pwr * (self.timestep/1000.0)
            
            if t - self.last_log > 0.5:
                print(f"T:{t:04.1f} | {status:<18} | Pwr:{pwr:05.1f}W")
                self.last_log = t

if __name__ == "__main__":
    bot = BroneRobot()
    bot.run()