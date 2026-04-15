"""
Webots Controller: HYBRID (Simulasi + ROS 2 Publisher)
Fitur:
1. Smoothing Input (Anti-Kejang untuk Robot Asli)
2. Menggerakkan Robot Fisik via ROS 2
3. Menggerakkan Robot Simulasi via Webots Motor API
"""
import sys
import os
import math

# --- 1. SETUP ROS 2 JAZZY ---
# Pastikan path ini sesuai dengan instalasi Jazzy Anda
ros_pkg_path = '/opt/ros/jazzy/lib/python3.12/site-packages'
if ros_pkg_path not in sys.path:
    sys.path.append(ros_pkg_path)

# Matikan warning hash check
os.environ['ROS_DISABLE_TYPE_HASH_CHECK'] = '1'

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import Twist
except ImportError:
    sys.exit("CRITICAL: Gagal import rclpy. Jalankan 'source /opt/ros/jazzy/setup.bash' di terminal!")

from controller import Robot

class WebotsController(Node):
    def __init__(self):
        super().__init__('webots_hybrid_node')
        self.publisher_ = self.create_publisher(Twist, '/cmd_vel', 10)
        
        # --- SETUP WEBOTS ---
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        self.keyboard = self.robot.getKeyboard()
        self.keyboard.enable(self.timestep)
        
        # --- SETUP MOTOR SIMULASI ---
        self.wheels = []
        # Sesuaikan nama ini dengan yang ada di PROTO (wheel1 s/d wheel4)
        wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        for name in wheel_names:
            motor = self.robot.getDevice(name)
            if motor:
                motor.setPosition(float('inf')) # Mode Velocity
                motor.setVelocity(0.0)
                self.wheels.append(motor)
            else:
                print(f"Warning: Motor {name} tidak ditemukan!")

        # --- PARAMETER ROBOT (Untuk Simulasi) ---
        # L = Jarak roda ke tengah (bisa disesuaikan agar visual pas)
        self.L_GEOM = 0.22 
        self.WHEEL_RADIUS = 0.06
        self.MAX_SIM_SPEED = 20.0 # Rad/s (Limit kecepatan motor simulasi)

    def run(self):
        print("=== WEBOTS HYBRID CONTROLLER ===")
        print("Kontrol: Panah (Gerak) + Shift (Putar)")
        
        # Parameter Smoothing
        TARGET_SPEED = 0.5 
        TURN_SPEED = 1.0
        DECAY_RATE = 0.1 # Makin kecil makin smooth (tapi agak delay)

        # Variabel Kecepatan (Current)
        cur_vx = 0.0
        cur_vy = 0.0
        cur_w = 0.0

        while self.robot.step(self.timestep) != -1:
            key = self.keyboard.getKey()
            
            # --- 1. BACA INPUT ---
            target_vx = 0.0
            target_vy = 0.0
            target_w = 0.0
            
            if key == self.keyboard.UP:
                target_vx = TARGET_SPEED
            elif key == self.keyboard.DOWN:
                target_vx = -TARGET_SPEED
            elif key == self.keyboard.LEFT:
                target_vy = TARGET_SPEED     # Geser Kiri
            elif key == self.keyboard.RIGHT:
                target_vy = -TARGET_SPEED    # Geser Kanan
            elif key == (self.keyboard.SHIFT + self.keyboard.LEFT):
                target_w = TURN_SPEED        # Putar Kiri
            elif key == (self.keyboard.SHIFT + self.keyboard.RIGHT):
                target_w = -TURN_SPEED       # Putar Kanan

            # --- 2. SMOOTHING (FILTER) ---
            cur_vx += (target_vx - cur_vx) * DECAY_RATE
            cur_vy += (target_vy - cur_vy) * DECAY_RATE
            cur_w  += (target_w - cur_w)  * DECAY_RATE
            
            # Deadzone Software (biar benar-benar 0 saat berhenti)
            if abs(cur_vx) < 0.01: cur_vx = 0.0
            if abs(cur_vy) < 0.01: cur_vy = 0.0
            if abs(cur_w) < 0.01:  cur_w = 0.0

            # --- 3. KIRIM KE ROS 2 (ROBOT ASLI) ---
            msg = Twist()
            msg.linear.x = float(cur_vx)
            msg.linear.y = float(cur_vy)
            msg.angular.z = float(cur_w)
            self.publisher_.publish(msg)

            # --- 4. GERAKKAN SIMULASI (MECANUM KINEMATICS) ---
            # Rumus Mecanum:
            # FL (Wheel2) = vx - vy - (L+W)*w
            # FR (Wheel1) = vx + vy + (L+W)*w
            # BL (Wheel3) = vx + vy - (L+W)*w
            # BR (Wheel4) = vx - vy + (L+W)*w
            # *Note: Tanda +/- mungkin perlu dibalik tergantung orientasi roda di PROTO
            
            # Kita pakai pengali sederhana agar visualnya enak dilihat
            # Karena cur_vx satuannya m/s, kita konversi ke rad/s untuk motor
            
            # Faktor Geometri (sumbu robot)
            geom_factor = cur_w * self.L_GEOM 
            
            # Hitung kecepatan linear tiap roda
            # Perhatikan: Urutan motor di self.wheels adalah [1, 2, 3, 4]
            # Mapping biasa: 1=FR, 2=FL, 3=BL, 4=BR
            
            # Coba konfigurasi standar ini:
            v_wheel1 = cur_vx - cur_vy + geom_factor # FR
            v_wheel2 = cur_vx + cur_vy - geom_factor # FL
            v_wheel3 = cur_vx - cur_vy - geom_factor # BL
            v_wheel4 = cur_vx + cur_vy + geom_factor # BR

            # Konversi ke Rad/s (dibagi jari-jari)
            # Dikali faktor gain (misal 20) agar di layar terlihat ngebut
            SIM_GAIN = 20.0
            
            w1 = v_wheel1 * SIM_GAIN
            w2 = v_wheel2 * SIM_GAIN
            w3 = v_wheel3 * SIM_GAIN
            w4 = v_wheel4 * SIM_GAIN

            # Set Velocity ke Motor Webots
            if len(self.wheels) == 4:
                self.wheels[0].setVelocity(w1) 
                self.wheels[1].setVelocity(w2) 
                self.wheels[2].setVelocity(w3) 
                self.wheels[3].setVelocity(w4)

            # Spin ROS
            rclpy.spin_once(self, timeout_sec=0)

def main():
    rclpy.init(args=None)
    controller = WebotsController()
    try:
        controller.run()
    except KeyboardInterrupt:
        pass
    finally:
        controller.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()