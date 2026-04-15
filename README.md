# 🚀 BRone IORT Project: Grand Simulation Edition

![ROS 2 Jazzy](https://img.shields.io/badge/ROS_2-Jazzy-22314E?logo=ros) ![Webots](https://img.shields.io/badge/Webots-R2025a-red?logo=geometry-networks) ![Python 3](https://img.shields.io/badge/Python-3.12-blue?logo=python)

Repositori ini adalah meta-package untuk **Brone System** (Internet of Robotic Things), sebuah ekosistem *Digital Twin* berbasis ROS 2 yang mengintegrasikan Brone Humanoid (OP3) dan platform Omnidirectional 4-roda (BRone Roda), serta memvisualisasikan seluruh telemetri ke dalam Web Dashboard interaktif.

## 🗂️ Struktur Repositori

Proyek ini dipisahkan secara modular menjadi beberapa komponen:

| Folder / Package | Deskripsi |
|---|---|
| 🔋 `op3_power_monitor/` | ROS 2 Node untuk mengekstrak sensor data OP3, melacak konsumsi daya servo, dan menjalankan **Tornado HTTP Web Server** untuk Unified Dashboard. |
| 🛞 `brone_roda_monitor/` | ROS 2 Node yang menangani pub/sub khusus untuk *BRone Roda base*, mengalkulasi *state of charge* (SoC), dan menyajikan data torsi motor individual. |
| 🎮 `simulation/` | Project Webots terpadu. Termasuk file 3D Model (`.proto`), fisik *Worlds* (`.wbt`), dan *Controller Node* berbasis python C-API (`DITER_Roda_ros_bridge`). |
| 🛠️ `scripts/` | Berisi skrip otomasi seperti `start_grand_simulation.sh` yang menjalankan 8+ subsistem ROS secara berurutan dan sinkron. |

## 🏗️ Arsitektur Sistem

Ekosistem *Grand Simulation* mengedepankan isolasi tugas (separation of concerns):
1. **Simulation Layer (Webots):** Menjalankan fisika, mendengarkan Joint States, mengirim input kamera/IMU.
2. **Control Ingestion:** Input joystick/keyboard dicerna oleh IK Solver (Inverse Kinematics). Arah Cartesian diubah menjadi kompensasi kecepatan *4-wheel mecanum*.
3. **Telemetry & Dashboard Layer:** Setiap node controller bertindak merilis statistik operasi (Ping, Voltage, Ampere, Torque) sebagai pesan JSON ke node `unified_dashboard`, yang kemudian disalurkan tanpa *delay* memanfaatkan teknologi *WebSocket*.

## ⚠️ Prerequisites (Wajib)

Sebelum Anda mengkloning dan melakukan kompilasi paket ini, pastikan PC Anda sudah memiliki *framework* dasar berikut ter-install di workspace `src` Anda:

1.  **OS:** Ubuntu 24.04 (Noble Numbat).
2.  **ROS 2:** [Jazzy Jalisco](https://docs.ros.org/en/jazzy/Installation.html).
3.  **Simulator:** Webots R2025a (atau terintegrasi ke dalam paket ROS).
4.  **OP3 Frameworks (Robotis Base):**
    *   `ROBOTIS-OP3`, `ROBOTIS-OP3-msgs`, `ROBOTIS-OP3-Simulations`, `ROBOTIS-Framework`.
    *   Ini diperlukan agar `op3_manager` siap dikawinkan dengan Web Dashboard kita.

## ⚙️ Environment Setup & Compilation

Instalasi repositori ini ke dalam Workspace Colcon Anda.

### 1. Kloning Source Code
```bash
# Masuk ke direktori source colcon (Misal: robotis_ws)
cd ~/robotis_ws/src

# Kloning repo meta-package ini
git clone git@github.com:Codename-Hydra/Brone-IORT-Project-simulation-only-v1.git
```

### 2. Instalasi Dependency Modul Tambahan
Skrip ini membutuhkan pustaka Python eksternal (terutama untuk HTTP server & PyGame Joysticks):
```bash
cd Brone-IORT-Project-simulation-only-v1
pip3 install -r requirements.txt
```

### 3. Build & Source Workspace
Pastikan Anda mengeksekusi kompilasi dari *Root Workspace* Anda:
```bash
cd ~/robotis_ws
colcon build --symlink-install --packages-select op3_power_monitor brone_roda_monitor
source install/local_setup.bash
```
*(Tip: Flag `--symlink-install` sangat direkomendasikan karena Web Dashboard HTML/JS diperbarui dari folder source ke hasil instalasi secara Real-time).*

## 🚀 Usage (Jalankan Grand Simulation)

Seluruh ekosistem ini sudah diotomatisasi. Anda tidak perlu memanggil *roslaunch* secara acak.

Buka terminal baru (*bash*) dan eksekusi:
```bash
cd ~/robotis_ws/src/Brone-IORT-Project-simulation-only-v1/scripts
./start_grand_simulation.sh
```

**Apa yang terjadi ketika dieksekusi?**
1. Modul akan menumpang ke environment setup ROS 2 Anda.
2. Membuka dua Instance Webots secara background.
3. Node `op3_manager` masuk ke *virtual-serial* mode (simulation mode).
4. OP3 Action GUI Demo dan Console Power Terminal (gnome-terminal) menyala.
5. Membuka Web Server WebSocket. 

**Cara Akses Unified Dashboard**
Kunjungi halaman berikut di Browser Anda (Chrome disarankan):
👉 **http://localhost:8080**

### Opsi Tambahan Skrip (Flags)
Anda dapat memodifikasi perilaku simulator secara interaktif:
*   `--no-roda` : Meluncurkan OP3 saja tanpa Omnidirectional Base simulator.
*   `--no-gui` : Tidak memunculkan UI *RobotAction Demo* bawaan OP3.
*   `--voltage 12.0` : Memaksa suplai baterai simulasi ke 12.0V (Default: 11.8V).
*   `--roda-dummy` : Menonaktifkan Webots tetapi men-generasikan *Dummy Sine Waves* untuk keperluan uji stress (stress-test) WebSocket web dashboard.
