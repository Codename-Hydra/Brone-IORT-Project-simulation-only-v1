from controller import Robot, Motor

class BroneEnergyController:
    def __init__(self):
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # --- 1. Konfigurasi Spesifikasi Motor (PG36) ---
        self.V_SUPPLY = 24.0      # Volt
        self.I_STALL = 2.5        # Ampere
        self.I_IDLE = 0.2         # Ampere (Estimasi)
        self.TORQUE_STALL = 1.96  # N.m (20 kgf.cm)
        
        # --- 2. Inisialisasi Motor & Sensor ---
        self.left_motor = self.robot.getDevice('left_wheel_motor')
        self.right_motor = self.robot.getDevice('right_wheel_motor')
        
        # Aktifkan Feedback Torsi (PENTING untuk akurasi)
        self.left_motor.enableTorqueFeedback(self.timestep)
        self.right_motor.enableTorqueFeedback(self.timestep)
        
        self.left_motor.setPosition(float('inf'))
        self.right_motor.setPosition(float('inf'))
        self.left_motor.setVelocity(0.0)
        self.right_motor.setVelocity(0.0)

        # Variabel Akumulasi Energi
        self.total_energy_joules = 0.0
        self.last_log_time = 0.0

    def calculate_current(self, torque_val):
        """Menghitung arus berdasarkan beban torsi dinamis"""
        # Rumus linearitas DC Motor: I = I_idle + (Torsi_Load / Torsi_Stall) * (I_stall - I_idle)
        # Menggunakan nilai mutlak torsi karena arus tetap positif walau mundur
        load_ratio = abs(torque_val) / self.TORQUE_STALL
        # Clamp ratio max 1.0 (jika simulasi collision menyebabkan torsi ekstrem)
        load_ratio = min(load_ratio, 1.0) 
        
        current = self.I_IDLE + (load_ratio * (self.I_STALL - self.I_IDLE))
        return current

    def run(self):
        print("Mulai Estimasi Energi Robot BRONE - PG36 Specs")
        print("Time(s) | Tegangan(V) | Arus Tot(A) | Daya(W) | Energi(J) | Torsi L/R (N.m)")
        print("-" * 80)

        while self.robot.step(self.timestep) != -1:
            current_time = self.robot.getTime()
            
            # --- 3. Ambil Data Torsi Real-time dari Fisika Webots ---
            # Webots menghitung ini berdasarkan berat 8.5kg, gesekan, & inersia
            tau_left = self.left_motor.getTorqueFeedback()
            tau_right = self.right_motor.getTorqueFeedback()
            
            # --- 4. Hitung Konsumsi Daya ---
            i_left = self.calculate_current(tau_left)
            i_right = self.calculate_current(tau_right)
            
            total_current = i_left + i_right
            instant_power = self.V_SUPPLY * total_current  # P = V * I
            
            # Integrasi Energi (Jou