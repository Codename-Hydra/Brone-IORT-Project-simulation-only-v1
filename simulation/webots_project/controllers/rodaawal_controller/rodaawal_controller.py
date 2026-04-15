from controller import Robot

# Inisialisasi Robot
robot = Robot()

# Ambil time step dari dunia (biasanya 32ms)
timestep = int(robot.getBasicTimeStep())

# --- 1. INISIALISASI MOTOR ---
# Pastikan nama di dalam string ("...") SAMA PERSIS dengan di Scene Tree
try:
    motor_kanan = robot.getDevice("motor_kanan")
    motor_kiri = robot.getDevice("motor_kiri")
    motor_depan = robot.getDevice("motor_depan")
    motor_belakang = robot.getDevice("motor_belakang")
except:
    print("ERROR: Nama motor tidak ditemukan! Cek nama di Scene Tree.")

# --- 2. SETTING MODE MOTOR ---
# Agar bisa diatur kecepatannya, posisi harus di-set ke Infinity
motor_kanan.setPosition(float('inf'))
motor_kiri.setPosition(float('inf'))
motor_depan.setPosition(float('inf'))
motor_belakang.setPosition(float('inf'))

# Set kecepatan awal 0
motor_kanan.setVelocity(0.0)
motor_kiri.setVelocity(0.0)
motor_depan.setVelocity(0.0)
motor_belakang.setVelocity(0.0)

# Kecepatan target (Rad/s)
KECEPATAN = 5.0 

# --- 3. LOOP UTAMA (Jantung Robot) ---
while robot.step(timestep) != -1:
    
    # Logika Gerak MAJU untuk Roda "+" (Omni/Mecanum Configuration)
    # Untuk maju, roda samping (Kanan & Kiri) berputar ke depan.
    # Roda Depan & Belakang DIAM (0) agar tidak melawan arah (mereka akan sliding).
    
    # Catatan: Jika robot malah mundur, ubah tanda minus/plus pada kecepatan.
    # Jika robot berputar di tempat, berarti salah satu roda terbalik sumbunya.
    
    motor_kanan.setVelocity(KECEPATAN) 
    motor_kiri.setVelocity(KECEPATAN)   
    
    # Roda depan & belakang dimatikan karena tegak lurus dengan arah maju
    motor_depan.setVelocity(0)
    motor_belakang.setVelocity(0)

    pass