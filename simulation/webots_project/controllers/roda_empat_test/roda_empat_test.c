/*
 * Modifikasi: Prediksi Daya Robot Omni 4 Roda (PG36 Specs)
 * Fitur: Logging 1 Detik, Rumus Linear Load
 */

#include <stdio.h>
#include <math.h>
#include <webots/motor.h>
#include <webots/robot.h>

#define TIME_STEP 8
#define NUM_WHEELS 4

// --- SPESIFIKASI MOTOR PG36 (Berdasarkan Data Anda) ---
const double V_SUPPLY = 24.0;       // Volt
const double I_STALL = 2.5;         // Ampere (Saat macet/beban max)
const double I_IDLE = 0.25;         // Ampere (Estimasi tanpa beban)
const double TORQUE_STALL = 1.96;   // N.m (20 kgf.cm konversi ke N.m)

// Beban Elektronik (Microcontroller, Driver, Sensor)
const double P_STATIC = 5.0;        // Watt (Estimasi)

static WbDeviceTag wheels[NUM_WHEELS];
static double cmd[5][4] = {
  {4, 0, -4, 0},    // Bergerak
  {0, 4, 0, -4},    // Geser Samping
  {-4, 0, 4, 0},    // Mundur
  {0, -4, 0, 4},    // Geser Balik
  {2, 2, 2, 2},     // Putar
};

// Variabel untuk Akumulasi Energi
double total_energy_joules = 0.0;
double last_log_time = 0.0;

double calculate_instant_power(double dt) {
  double total_current_motors = 0.0;
  
  // Header print (hanya sekali di awal debug stream jika perlu)
  // printf("Torsi Roda: ");

  for (int i = 0; i < NUM_WHEELS; i++) {
    // 1. Ambil Torsi Aktual dari Fisika Webots (N.m)
    double torque_measured = wb_motor_get_torque_feedback(wheels[i]);
    
    // 2. Hitung Arus Motor menggunakan Linear Interpolation
    // Rumus: I = I_idle + (Torsi_Terukur / Torsi_Stall) * (I_stall - I_idle)
    double load_ratio = fabs(torque_measured) / TORQUE_STALL;
    
    // Safety clamp (agar tidak melebihi 100% jika terjadi tabrakan ekstrem di simulasi)
    if (load_ratio > 1.0) load_ratio = 1.0;

    double current = I_IDLE + (load_ratio * (I_STALL - I_IDLE));
    
    total_current_motors += current;
  }

  // 3. Hitung Daya Total (P = V*I_total + P_static)
  double p_dynamic = V_SUPPLY * total_current_motors;
  double p_total = P_STATIC + p_dynamic;

  // 4. Hitung Energi (Joule = Watt * detik)
  total_energy_joules += p_total * dt;

  return p_total;
}

int main() {
  int i, j;
  double current_time = 0.0;

  wb_robot_init();

  // Inisialisasi Motor
  for (i = 0; i < NUM_WHEELS; i++) {
    char name[64];
    sprintf(name, "wheel%d", i + 1); // Pastikan nama di WBT adalah wheel1, wheel2, dst.
    wheels[i] = wb_robot_get_device(name);
    
    wb_motor_set_position(wheels[i], INFINITY);
    wb_motor_set_velocity(wheels[i], 0.0);
    
    // PENTING: Aktifkan Feedback Torsi
    wb_motor_enable_torque_feedback(wheels[i], TIME_STEP);
  }

  printf("=== MULAI SIMULASI ENERGI BRONE (PG36 24V) ===\n");
  printf("Time(s) | Daya(W) | Energi(J) | V_Batt(V)\n");
  printf("---------------------------------------------\n");

  int step_counter = 0;
  int maneuver_index = 0;

  while (wb_robot_step(TIME_STEP) != -1) {
    current_time = wb_robot_get_time();
    double dt = (double)TIME_STEP / 1000.0; // Detik

    // --- A. Logika Pergerakan Robot (Ganti manuver tiap 3 detik) ---
    if (step_counter % (3000 / TIME_STEP) == 0) {
        maneuver_index = (maneuver_index + 1) % 5;
        for (j = 0; j < NUM_WHEELS; j++) {
            // Speed factor disesuaikan agar tidak overspeed (Max PG36 440RPM ~ 46 rad/s)
            wb_motor_set_velocity(wheels[j], cmd[maneuver_index][j]); 
        }
    }
    step_counter++;

    // --- B. Kalkulasi Daya ---
    double instant_power = calculate_instant_power(dt);

    // --- C. Logging Setiap 1 Detik ---
    if (current_time - last_log_time >= 1.0) {
        printf("%05.1fs | %06.2fW | %06.2fJ | %.1fV\n", 
               current_time, instant_power, total_energy_joules, V_SUPPLY);
        last_log_time = current_time;
    }
  }

  wb_robot_cleanup();
  return 0;
}