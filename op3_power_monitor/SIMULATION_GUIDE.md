# Step-by-Step: Testing op3_power_monitor dengan Simulasi OP3

Panduan ini menjelaskan cara menjalankan **Webots + OP3 Manager (Simulation) + OP3 GUI Demo + Web Dashboard** secara bersama-sama, lalu mem-verifikasi `op3_power_monitor` menerima dan menampilkan datanya.

---

## Prasyarat

Pastikan workspace sudah ter-build dan ter-source:

```bash
# Build semua package yang diperlukan jika belum
cd ~/robotis_ws
colcon build --packages-select op3_webots_ros2 op3_manager op3_gui_demo op3_power_monitor

# Source workspace (lakukan sekali di setiap terminal baru)
source ~/robotis_ws/install/local_setup.bash
```

Pastikan juga pustaka `websockets` sudah terinstal (diperlukan oleh Web Dashboard):

```bash
pip3 install websockets
```

> **Tip:** Jika sudah menambahkan baris source ke `~/.bashrc`, cukup buka terminal baru dan tidak perlu mengetik source lagi.

---

## 🚀 Quick Start — Satu Klik

Jika tidak ingin membuka 6 terminal manual, gunakan script launcher yang menjalankan **semua komponen sekaligus**:

```bash
# Dari source tree
~/robotis_ws/src/op3_power_monitor/scripts/start_simulation.sh

# Atau jika sudah ter-install
~/robotis_ws/install/op3_power_monitor/share/op3_power_monitor/scripts/start_simulation.sh
```

Script ini secara otomatis:
1. Source ROS2 + workspace
2. Jalankan Webots (tunggu 8 detik)
3. Jalankan OP3 Manager simulation (tunggu 6 detik)
4. Jalankan OP3 GUI Demo
5. Jalankan Power Monitor Node
6. Publish voltase simulasi (default: 11.8V)
7. Jalankan Web Dashboard → buka `http://localhost:8080`

**Tekan `Ctrl+C` untuk menghentikan semua proses sekaligus** (shutdown otomatis dalam urutan aman).

### Opsi Tambahan

```bash
# Tanpa GUI Demo (headless)
./start_simulation.sh --no-gui

# Voltase simulasi custom
./start_simulation.sh --voltage 12.0

# Port dashboard custom
./start_simulation.sh --http-port 8081 --ws-port 9091

# Gabungan
./start_simulation.sh --no-gui --voltage 10.5

# Lihat semua opsi
./start_simulation.sh --help
```

> Jika ingin menjalankan step-by-step secara manual (terpisah per terminal), ikuti panduan di bawah.

---

## Arsitektur Sistem

```
┌──────────────────────────────────────────────────────────────┐
│  Terminal 1          Terminal 2           Terminal 3          │
│                                                              │
│  [Webots]        [op3_manager]          [op3_gui_demo]       │
│  Simulator   ←→  simulation mode   ←→   Qt Control GUI      │
│                       ↓                                      │
│               /robotis/present_joint_states                   │
│               /robotis/status                                │
│                       ↓                                      │
│  Terminal 5:  Terminal 4:                                    │
│  [simulasi    [op3_power_monitor]                            │
│   voltase]     ↓ /op3/power/summary (JSON @1Hz)              │
│                       ↓                                      │
│             Terminal 6: [power_dashboard]                    │
│              WebSocket :9090  ←→  Browser (localhost:8080)    │
│              ┌─────────────────────────────────────┐         │
│              │  Battery Gauge │ Robot Body Map      │         │
│              │  Voltage Chart │ Per-Joint Table     │         │
│              │  Summary Cards │ Filter per Group    │         │
│              └─────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────┘
```

---

## Step 1 — Jalankan Webots Simulator

Buka **Terminal 1**:

```bash
ros2 launch op3_webots_ros2 robot_launch.py
```

Webots akan terbuka dengan world `robotis_op3_extern.wbt` yang berisi robot OP3 di lapangan. Tunggu hingga Webots selesai load (robot terlihat di scene).

> **Catatan:** Webots perlu terinstall di sistem. Jika belum, cek alias `webots` di `.bashrc` Anda, atau jalankan langsung lewat launcher-nya.

---

## Step 2 — Jalankan OP3 Manager (Mode Simulasi)

Buka **Terminal 2**:

```bash
ros2 launch op3_manager op3_simulation.launch.py
```

Launch file ini menjalankan `op3_manager` dengan parameter `simulation: true` dan `simulation_robot_name: robotis_op3` — sehingga berkomunikasi ke Webots via topik, **bukan ke hardware fisik**.

Tunggu sampai muncul log seperti:
```
[op3_manager]: ...robotis_controller: Timer start...
```

Node yang aktif setelah ini:
- `/op3_manager` (node utama robotis_controller)
- `/robotis/present_joint_states` sudah mulai dipublikasikan

---

## Step 3 — Jalankan OP3 GUI Demo

Buka **Terminal 3**:

```bash
ros2 launch op3_gui_demo op3_demo.launch.py
```

Jendela GUI Qt akan terbuka berisi:
- **Motion Module Control** — enable/disable modul gerak
- **Walking Control** — parameter jalan kaki
- **Direct Pose Control** — atur posisi joint langsung
- **Ball Detection** — (tidak aktif di simulasi)

Gunakan GUI ini untuk **menggerakkan robot** di Webots sehingga data joint berubah dan power monitor mendapatkan nilai yang bervariasi.

---

## Step 4 — Jalankan Power Monitor

Buka **Terminal 4**:

```bash
ros2 run op3_power_monitor power_monitor_node
```

Jika package tidak ditemukan, jalankan:

```bash
source /opt/ros/jazzy/setup.bash
source ~/robotis_ws/install/local_setup.bash
export AMENT_PREFIX_PATH=~/robotis_ws/install/op3_power_monitor:$AMENT_PREFIX_PATH
export PYTHONPATH=~/robotis_ws/install/op3_power_monitor/lib/python3.12/site-packages:$PYTHONPATH
ros2 run op3_power_monitor power_monitor_node
```

Node akan menampilkan tabel real-time di terminal:

```
┌─ System ──────────────────────────────────────────────────┐
│  op3_manager : ✅   Battery: ⚪ N/A  [UNKNOWN]              │
│  Current data: ⚠️  effort[]=0 — add present_current...     │
└───────────────────────────────────────────────────────────┘
┌─ Joints (XM430-W350 × 20) ───────────────────────────────┐
│           Joint   Pos(deg)  Vel(r/s)  Effort  I (A)       │
│     r_sho_pitch      -2.50    0.0010      0.00   N/A      │
│     l_sho_pitch       2.50    0.0008      0.00   N/A      │
│          ...                                              │
└───────────────────────────────────────────────────────────┘
```

> **Kenapa Vin dan Battery menunjukkan N/A?**
> Di simulasi Webots, modul `open_cr_module` **tidak aktif** sehingga tidak ada pesan voltase yang dipublikasikan ke `/robotis/status`. Kolom `Vin (V)` per-servo dihitung dari `battery_voltage`, jadi jika battery N/A maka Vin juga N/A.
> **Solusi:** Jalankan Step 5 di bawah untuk mensimulasikan data voltase.

---

## Step 5 — Simulasi Voltase (WAJIB untuk Simulasi)

Karena di mode simulasi tidak ada OpenCR fisik, **wajib** simulasikan data voltase agar kolom `Vin (V)` dan `Battery` terisi:

Buka **Terminal 5**:

```bash
# Kirim data voltase 11.8V setiap 1 detik
ros2 topic pub --rate 1 /robotis/status robotis_controller_msgs/msg/StatusMsg \
  "{type: 1, module_name: 'SENSOR', status_msg: 'Present Volt : 11.8V'}"
```

Setelah pesan pertama diterima, **semua kolom Vin langsung terisi**:

```
┌─ Voltage Overview ─────────────────────────────────────────────┐
│  Battery (OpenCR): 🟢 11.80 V  [OK]                            │
│  Servo Bus : avg=11.75V  min=11.70V  max=11.75V               │
└───────────────────────────────────────────────────────────────┘
┌─ Per-Joint Detail ────────────────────────────────────────────┐
│     r_sho_pitch     11.75    -2.50   0.001    0.00    N/A     │
│     l_sho_pitch     11.75     2.50   0.000    0.00    N/A     │
│          ...                                                  │
└───────────────────────────────────────────────────────────────┘
```

Ganti nilai voltase untuk melihat status berubah:
- `12.0V` → 🟢 OK
- `11.2V` → 🟡 LOW (warning di terminal)
- `10.5V` → 🔴 CRITICAL (error di terminal)

> **Catatan:** Di hardware asli, OpenCR otomatis mempublikasikan voltase baterai setiap detik — Step ini tidak diperlukan.

---

## Step 6 — Buka Web Dashboard UI

Untuk visualisasi yang lebih interaktif, jalankan node Web Dashboard. Node ini secara internal subscribe ke `/op3/power/summary` (yang dipublikasikan oleh `power_monitor_node`) dan meneruskan datanya lewat WebSocket ke browser.

Buka **Terminal 6**:

```bash
ros2 run op3_power_monitor power_dashboard
```

Output akan menunjukkan:

```
[OP3 Power Dashboard] Starting...
  WebSocket: ws://0.0.0.0:9090
  HTTP:      http://0.0.0.0:8080
  Subscribed to: /op3/power/summary

  Open http://localhost:8080 in your browser!
```

Buka browser dan kunjungi: [http://localhost:8080](http://localhost:8080)

### Fitur Dashboard

| Komponen | Deskripsi |
|---|---|
| **Battery Gauge** | Arc meter animasi dengan tick 9–13V. Warna berubah otomatis berdasarkan status: 🟢 OK, 🟡 LOW, 🔴 CRITICAL |
| **Robot Body Map** | SVG anatomi OP3 dengan **20 titik joint** sesuai `OP3.robot`. Setiap titik berubah warna sesuai voltase input-nya |
| **Voltage Chart** | Grafik time-series 60 detik terakhir, lengkap dengan garis threshold OK/LOW |
| **Per-Joint Table** | Tabel detail: ID, Nama, Vin, Position, Velocity, Effort, Current, Power |
| **Filter Group** | Tombol filter: `All (20)`, `Head`, `R Arm`, `L Arm`, `R Leg`, `L Leg` |
| **Summary Cards** | Total Power (W), Avg Voltage, Min Voltage, Σ \|Effort\| |
| **Uptime Timer** | Waktu sejak dashboard dibuka |

### Mapping 20 Joint di Body Map

SVG body map menampilkan semua 20 servo XM430-W350 sesuai urutan `OP3.robot` config:

| Group | Joint (ID) |
|---|---|
| **Head** | `head_pan` (19), `head_tilt` (20) |
| **R Arm** | `r_sho_pitch` (1), `r_sho_roll` (3), `r_el` (5) |
| **L Arm** | `l_sho_pitch` (2), `l_sho_roll` (4), `l_el` (6) |
| **R Leg** | `r_hip_yaw` (7), `r_hip_roll` (9), `r_hip_pitch` (11), `r_knee` (13), `r_ank_pitch` (15), `r_ank_roll` (17) |
| **L Leg** | `l_hip_yaw` (8), `l_hip_roll` (10), `l_hip_pitch` (12), `l_knee` (14), `l_ank_pitch` (16), `l_ank_roll` (18) |

### Interaksi

- **Hover di titik SVG** → tooltip menampilkan nama joint, ID, Vin, dan posisi. Baris tabel juga akan ter-highlight.
- **Hover di baris tabel** → titik joint yang bersesuaian di SVG akan membesar.
- **Klik filter** → tabel hanya menampilkan joint sesuai group yang dipilih.

---

## Step 7 — Verifikasi Output Topics

Buka **Terminal 7** untuk memonitor topik:

```bash
# Cek tegangan per-joint
ros2 topic echo /op3/power/joint_voltages

# Cek joint states diterima dari simulasi
ros2 topic echo /op3/power/joint_loads

# Cek JSON summary (termasuk voltage_summary)
ros2 topic echo /op3/power/summary

# Lihat semua topik aktif
ros2 topic list | grep op3/power
```

---

## Urutan Shutdown yang Aman

```bash
# 1. Stop web dashboard (Ctrl+C di Terminal 6)
# 2. Stop simulasi voltase (Ctrl+C di Terminal 5)
# 3. Stop power monitor (Ctrl+C di Terminal 4)
# 4. Stop GUI demo (Ctrl+C di Terminal 3)
# 5. Stop op3_manager (Ctrl+C di Terminal 2)
# 6. Tutup Webots (Ctrl+C di Terminal 1, atau close window Webots)
```

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| Webots tidak terbuka | Pastikan `WEBOTS_HOME` ter-set atau gunakan alias `webots` di `.bashrc` |
| `op3_manager` tidak connect ke Webots | Pastikan Webots sudah fully loaded sebelum launch `op3_manager` |
| `joint_states` kosong di power monitor | Cek `/robotis/present_joint_states` aktif: `ros2 topic hz /robotis/present_joint_states` |
| `op3_power_monitor` tidak ditemukan | Jalankan manual export AMENT_PREFIX_PATH di atas |
| GUI demo tidak bisa connect | Tunggu ~5 detik setelah `op3_manager` siap sebelum launch GUI |
| Dashboard blank / `Disconnected` | Pastikan `power_monitor_node` sudah jalan **sebelum** `power_dashboard` |
| Port 8080 sudah dipakai | Ubah port: `ros2 run op3_power_monitor power_dashboard --ros-args -p http_port:=8081 -p ws_port:=9091` |
| `ModuleNotFoundError: websockets` | Install: `pip3 install websockets` |
| Joint dots tetap abu-abu | Belum ada data voltase — jalankan Step 5 (simulasi voltase) |
| Browser tidak bisa connect WebSocket | Pastikan URL WS sesuai hostname (default: `ws://localhost:9090`) |
