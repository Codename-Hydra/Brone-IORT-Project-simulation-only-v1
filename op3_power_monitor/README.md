# op3_power_monitor

ROS2 Python package untuk memonitor tegangan dan arus dari setiap komponen **ROBOTIS OP3** secara *real-time* tanpa memodifikasi kode yang sudah ada di `robotis_ws`.

---

## Deskripsi

Package ini bekerja secara **pasif** — hanya subscribe ke topik ROS2 yang sudah dipublikasikan oleh `op3_manager` dan `open_cr_module`. Mengikuti arsitektur resmi ROBOTIS OP3 Framework yang dijelaskan di [Read-Write Tutorial](https://emanual.robotis.com/docs/en/platform/op3/tutorials/).

### Sumber Data

| Komponen | Data | Sumber Topik |
|---|---|---|
| Board OpenCR (ID 200) | Voltase baterai total (V) | `/robotis/status` |
| 20× Dynamixel XM430-W350 | Posisi, Kecepatan, Effort/Arus per-joint | `/robotis/present_joint_states` |
| Tombol OpenCR | Event button press | `/robotis/open_cr/button` |

---

## Struktur Package

```
op3_power_monitor/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/
│   └── op3_power_monitor
├── op3_power_monitor/
│   ├── __init__.py
│   ├── power_monitor_node.py     ← node utama
│   └── power_dashboard_node.py   ← node web dashboard
└── web/
    ├── index.html                ← dashboard UI
    ├── style.css
    └── app.js
```

---

## Topics

### Subscribed (membaca dari sistem yang ada)

| Topic | Tipe | Keterangan |
|---|---|---|
| `/robotis/status` | `robotis_controller_msgs/StatusMsg` | Berisi teks tegangan, contoh: `"Present Volt : 11.5V"` |
| `/robotis/present_joint_states` | `sensor_msgs/JointState` | Posisi, kecepatan, effort tiap joint |
| `/robotis/open_cr/button` | `std_msgs/String` | Event tombol: `mode`, `start`, `user`, `reset` |

### Published (output node ini)

| Topic | Tipe | Keterangan |
|---|---|---|
| `/op3/power/battery_voltage` | `std_msgs/Float32` | Tegangan baterai dalam Volt |
| `/op3/power/battery_status` | `std_msgs/String` | `OK` / `LOW` / `CRITICAL` |
| `/op3/power/joint_loads` | `sensor_msgs/JointState` | Effort/arus per joint |
| `/op3/power/summary` | `std_msgs/String` | JSON snapshot semua data (1 Hz) |

---

## Threshold Baterai

Sesuai dengan logika di `open_cr_module.cpp`:

| Status | Voltase |
|---|---|
| 🟢 `OK` | ≥ 11.5 V |
| 🟡 `LOW` | ≥ 11.0 V dan < 11.5 V |
| 🔴 `CRITICAL` | < 11.0 V |

---

## Instalasi & Build

Pastikan pustaka `websockets` sudah terinstal di sistem Anda untuk menjalankan web dashboard:

```bash
pip3 install websockets
```

Lalu bangun packagenya:

```bash
cd ~/robotis_ws
colcon build --packages-select op3_power_monitor
```

Kemudian tambahkan ke `~/.bashrc` agar package selalu dapat ditemukan:

```bash
# Tambahkan baris ini di ~/.bashrc (setelah source workspace)
_OP3_POWER_PREFIX=~/robotis_ws/install/op3_power_monitor
export AMENT_PREFIX_PATH="$_OP3_POWER_PREFIX:$AMENT_PREFIX_PATH"
export PYTHONPATH="$_OP3_POWER_PREFIX/lib/python3.12/site-packages:$PYTHONPATH"
unset _OP3_POWER_PREFIX
```

> **Catatan:** Export manual ini diperlukan karena workspace `robotis_ws` sudah dibangun sebelum package ini ditambahkan — file `local_setup.bash` tidak otomatis ter-update untuk package baru.

---

## Cara Menjalankan

### Dengan Hardware Robot

```bash
# Terminal 1: jalankan op3_manager terlebih dahulu
ros2 launch op3_read_write_demo op3_read_write.launch.xml

# Terminal 2: jalankan power monitor
ros2 run op3_power_monitor power_monitor_node
```

### Tanpa Hardware (Simulasi/Test)

```bash
# Terminal 1: jalankan node
ros2 run op3_power_monitor power_monitor_node

# Terminal 2: kirim data voltase simulasi (1 Hz)
ros2 topic pub --rate 1 /robotis/status robotis_controller_msgs/msg/StatusMsg \
  "{type: 1, module_name: 'SENSOR', status_msg: 'Present Volt : 11.5V'}"

# Terminal 3: lihat output
ros2 topic echo /op3/power/battery_voltage
ros2 topic echo /op3/power/summary
```

---

## Output Terminal (Tabel Real-Time)

Node mencetak tabel ringkasan ke terminal setiap detik:

```
═══════════════════════════════════════════════════════════════════════
  OP3 POWER MONITOR — based on ROBOTIS OP3 Framework
  Topic: /robotis/present_joint_states + /robotis/status
═══════════════════════════════════════════════════════════════════════

┌─ System ──────────────────────────────────────────────────────────┐
│  op3_manager : ✅   Battery: 🟢 11.50 V  [OK]                     │
│  Current data: ⚠️  effort[]=0 — add present_current to OP3.robot  │
└───────────────────────────────────────────────────────────────────┘
┌─ Joints (/robotis/present_joint_states — XM430-W350 × 20) ───────┐
│           Joint   Pos(deg)   Vel(r/s)  Effort(raw)     I (A)      │
│  ─────────────────────────────────────────────────────            │
│     r_sho_pitch       0.00     0.0000        0.00       N/A       │
│     l_sho_pitch       0.00     0.0000        0.00       N/A       │
│          ...                                                       │
│  ─────────────────────────────────────────────────────            │
```

---

## Web Dashboard (Zero-Dependency)

Package ini juga menyertakan Web Dashboard lengkap untuk memantau data daya. Dashboard ini menggunakan server WebSocket bawaan dan web HTTP server bawaan, sehingga **tidak butuh rosbridge_suite**.

Cara menjalankan:

```bash
# Terminal 1: jalankan node power monitor (sebagai publisher summary)
ros2 run op3_power_monitor power_monitor_node

# Terminal 2: jalankan node dashboard
ros2 run op3_power_monitor power_dashboard
```

Kemudian buka browser dan navigasi ke: [http://localhost:8080](http://localhost:8080)

Dashboard menampilkan:
- 🔋 **Battery Gauge**: Indikator cincin + status OK/LOW/CRITICAL
- 🤖 **Robot Body Map**: SVG 20 joint titik, menyala merah/kuning saat drop tegangan
- 📈 **Voltage Chart**: Grafik time-series 60-detik
- 📊 **Per-Joint Table**: Data detil dengan sorting real-time


---

## Mengaktifkan Pembacaan Arus Per-Joint (Opsional)

Secara default, `effort[]` dari `/robotis/present_joint_states` bernilai 0 karena `present_current` tidak ada di bulk-read items.

Untuk mengaktifkannya, edit `OP3.robot`:

```
# Path: robotis_ws/src/ROBOTIS-OP3/op3_manager/config/OP3.robot
# Ubah setiap baris Dynamixel dari:
dynamixel | ... | r_sho_pitch | present_position, position_p_gain, ...

# Menjadi:
dynamixel | ... | r_sho_pitch | present_position, present_current, position_p_gain, ...
```

Setelah itu rebuild `op3_manager`:

```bash
colcon build --packages-select op3_manager
```

Node `op3_power_monitor` akan otomatis mendeteksi adanya data arus dan mengkonversinya ke Ampere menggunakan faktor XM430-W350: **1 unit = 2.69 mA**.

---

## Parameter Node

| Parameter | Default | Keterangan |
|---|---|---|
| `report_period_sec` | `1.0` | Interval laporan dalam detik |
| `voltage_ok_threshold_v` | `11.5` | Threshold voltase "OK" |
| `voltage_warn_threshold_v` | `11.0` | Threshold voltase "LOW" warning |
| `print_table` | `true` | Tampilkan tabel di terminal |

Contoh mengubah parameter saat run:

```bash
ros2 run op3_power_monitor power_monitor_node \
  --ros-args -p report_period_sec:=0.5 -p print_table:=false
```

---

## Referensi

- [ROBOTIS OP3 Read-Write Tutorial](https://emanual.robotis.com/docs/en/platform/op3/tutorials/)
- [Dynamixel XM430-W350 e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/)
- Source: `robotis_ws/src/ROBOTIS-OP3/open_cr_module/src/open_cr_module.cpp`
- Config: `robotis_ws/src/ROBOTIS-OP3/op3_manager/config/OP3.robot`
