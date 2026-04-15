# Code Reference — op3_power_monitor

Dokumen ini menjelaskan **dari mana setiap data berasal** di `op3_power_monitor` — file sumber, fungsi, register address, dan konversi unit.

---

## Arsitektur Data Flow

```mermaid
graph TD
    subgraph "Hardware"
        BATT[🔋 LiPo Battery]
        OCR[OpenCR Board<br>ID: 200]
        DXL[20× Dynamixel<br>XM430-W350]
    end

    subgraph "ROBOTIS Framework (C++)"
        OCM[open_cr_module.cpp<br>handleVoltage :256]
        RC[robotis_controller.cpp<br>process :882]
    end

    subgraph "ROS2 Topics"
        T1[/robotis/status<br>StatusMsg]
        T2[/robotis/present_joint_states<br>JointState]
        T3[/robotis/open_cr/button<br>String]
    end

    subgraph "op3_power_monitor (Python)"
        PM[power_monitor_node.py]
    end

    BATT --> OCR
    BATT --> DXL
    OCR --> OCM
    DXL --> RC
    OCM --> T1
    OCM --> T3
    RC --> T2
    T1 --> PM
    T2 --> PM
    T3 --> PM
```

---

## 1. Battery Voltage (Total)

### Sumber Data

| Item | Detail |
|---|---|
| **Hardware** | OpenCR Board (sensor ID 200) — membaca `present_voltage` register |
| **File sumber** | [open_cr_module.cpp](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-OP3/open_cr_module/src/open_cr_module.cpp) |
| **Fungsi** | `OpenCRModule::process()` → line 111 |
| **Raw read** | `sensors["open-cr"]->sensor_state_->bulk_read_table_["present_voltage"]` |
| **Konversi** | `present_volt * 0.1` → Volt (line 144) |
| **Filter** | Low-pass filter ratio 0.4 di `handleVoltage()` (line 256-280) |
| **Format publish** | `StatusMsg.status_msg = "Present Volt : {value}V"` (line 274) |
| **Topic** | `/robotis/status` — type: `robotis_controller_msgs/msg/StatusMsg` |
| **Publisher** | `publishStatusMsg()` line 283-293 via `status_pub_` |
| **Threshold** | `< 11V` → `STATUS_WARN`, `>= 11V` → `STATUS_INFO` (line 276-277) |

### Kode di power_monitor_node.py

```python
# Line 119: regex pattern untuk parsing
VOLTAGE_PATTERN = re.compile(r'[Pp]resent\s+[Vv]olt\s*:\s*([\d.]+)\s*V')

# Line 323-332: callback parsing
def _on_status_msg(self, msg: StatusMsg):
    match = VOLTAGE_PATTERN.search(msg.status_msg)
    voltage = float(match.group(1))
```

### Config File

```
# OP3.robot — OpenCR sensor bulk-read items
sensor | /dev/ttyUSB0 | 200 | open-cr | 2.0 | open_cr | present_voltage, ...
```

File: [OP3.robot](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-OP3/op3_manager/config/OP3.robot)

---

## 2. Per-Joint Position (present_position)

### Sumber Data

| Item | Detail |
|---|---|
| **Hardware** | 20× Dynamixel XM430-W350 |
| **Register** | `present_position` — address **132**, length 4 bytes |
| **File sumber** | [robotis_controller.cpp](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-Framework/robotis_controller/src/robotis_controller/robotis_controller.cpp) |
| **Fungsi** | `RobotisController::process()` — line 959-961 |
| **Konversi** | `dxl->convertValue2Radian(data)` → radian |
| **Topic** | `/robotis/present_joint_states` — type: `sensor_msgs/msg/JointState` |
| **Publisher** | Line 653: `present_joint_state_pub_` |
| **Field** | `JointState.position[]` |

### Device File

```
# XM430-W350.device (atau XM540-W270.device)
present_position    | 132 | 4 | R | 0 | 4095 | ...
```

File: [XM540-W270.device](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-Framework/robotis_device/devices/dynamixel/XM540-W270.device)

### Config — Bulk Read

```
# OP3.robot — setiap Dynamixel joint
dynamixel | ... | r_sho_pitch | present_position, position_p_gain, position_i_gain, position_d_gain
```

> **`present_position` ada di bulk-read** → data tersedia ✅

---

## 3. Per-Joint Effort/Current (present_current)

### Sumber Data

| Item | Detail |
|---|---|
| **Hardware** | 20× Dynamixel XM430-W350 |
| **Register** | `present_current` — address **126**, length 2 bytes |
| **Konversi raw → Ampere** | `1 unit = 2.69 mA` (dari e-manual Dynamixel) |
| **File sumber** | [robotis_controller.cpp](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-Framework/robotis_controller/src/robotis_controller/robotis_controller.cpp) |
| **Fungsi** | `RobotisController::process()` — line 965-966 |
| **Kode C++** | `dxl->dxl_state_->present_torque_ = dxl->convertValue2Torque(data)` |
| **Topic** | `/robotis/present_joint_states` — field: `JointState.effort[]` |

### ⚠️ Masalah: Tidak ada di Bulk-Read default

```
# OP3.robot — DEFAULT (TANPA present_current)
dynamixel | ... | r_sho_pitch | present_position, position_p_gain, ...
#                                ^ present_current TIDAK ADA di sini
```

**Akibat:** `effort[]` selalu = 0

**Solusi:** Ubah OP3.robot menjadi:
```
dynamixel | ... | r_sho_pitch | present_position, present_current, position_p_gain, ...
```

### Kode di power_monitor_node.py

```python
# Line 106: konversi factor
XM430_CURRENT_UNIT_A = 0.00269  # A per raw unit (dari Dynamixel e-manual)

# Line 414-420: konversi ke Ampere hanya jika data tersedia
if has_nonzero_effort and abs(effort_raw) > 0:
    jd.current_A = abs(effort_raw) * XM430_CURRENT_UNIT_A
    jd.estimated_power_W = jd.current_A * voltage
```

### Device File

```
# XM540-W270.device
present_current     | 126 | 2 | R | ... | unit: 2.69 mA
```

### Kode Controller C++

```cpp
// robotis_controller.cpp line 965-966
else if (dxl->present_current_item_ != 0 &&
         item->item_name_ == dxl->present_current_item_->item_name_)
    dxl->dxl_state_->present_torque_ = dxl->convertValue2Torque(data);
```

---

## 4. Per-Joint Input Voltage (Estimated)

### Sumber Data

| Item | Detail |
|---|---|
| **Hardware** | Dynamixel XM430-W350 register `present_input_voltage` |
| **Register** | Address **144**, length 2 bytes, unit 0.1V |
| **Status** | ⚠️ **TIDAK** tersedia via ROS topic (tidak di bulk-read) |
| **Implementasi** | **Estimasi** dari battery voltage − wire drop |

### Kode di power_monitor_node.py

```python
# Line 110: konversi factor (jika data asli tersedia)
XM430_VOLTAGE_UNIT_V = 0.1  # V per raw unit

# Line 117: estimasi wire drop
ESTIMATED_WIRE_DROP_V = 0.05  # volt

# Line 403-412: estimasi per-joint voltage dari battery
if self._battery_voltage is not None:
    load_factor = min(abs(effort_raw) / 1193.0, 1.0)  # 1193 = XM430 max current
    wire_drop = ESTIMATED_WIRE_DROP_V * (1.0 + load_factor)
    jd.input_voltage_V = round(self._battery_voltage - wire_drop, 2)
```

### Penjelasan Logika

- Semua servo terhubung ke **bus power yang sama** (paralel dari baterai)
- Tegangan input setiap servo ≈ tegangan baterai − voltage drop di kabel
- Drop lebih besar jika beban (effort) lebih tinggi
- `1193` = raw current maximum XM430-W350 (dari e-manual: 1193 × 2.69mA = 3.21A)

### Device File

```
# XM540-W270.device
present_input_voltage | 144 | 2 | R | 95 | 160 | ...
#                       ^addr  ^len     ^9.5V  ^16.0V (dalam unit 0.1V)
```

---

## 5. Button Events

### Sumber Data

| Item | Detail |
|---|---|
| **Hardware** | OpenCR Board — register `button` (3 physical buttons) |
| **File sumber** | [open_cr_module.cpp](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-OP3/open_cr_module/src/open_cr_module.cpp) |
| **Raw read** | `sensors["open-cr"]->sensor_state_->bulk_read_table_["button"]` — line 135 |
| **Bit mapping** | Bit 0 = mode, Bit 1 = start, Bit 2 = user (line 136-138) |
| **Publisher** | `button_pub_` line 86: `create_publisher<String>("/robotis/open_cr/button")` |
| **Publish fungsi** | `publishButtonMsg()` line 247-253 |
| **Long press** | > 2 detik → `"{name}_long"` (line 218-221) |

### Kode di power_monitor_node.py

```python
# Line 427-433: log button events
def _on_button(self, msg: String):
    self.get_logger().info(f'OpenCR button pressed: "{msg.data}"')
```

---

## 6. op3_manager Detection

### Sumber Referensi

| Item | Detail |
|---|---|
| **Pattern dari** | [read_write.cpp](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-OP3-Demo/op3_read_write_demo/src/read_write.cpp) |
| **Fungsi C++** | `checkManagerRunning()` — memeriksa apakah node `/op3_manager` ada |
| **Node name** | `/op3_manager` (from [op3_manager.cpp](file:///home/codename-hydra/robotis_ws/src/ROBOTIS-OP3/op3_manager/src/op3_manager.cpp) line 166) |

### Kode di power_monitor_node.py

```python
# Line 303-319: mirrors checkManagerRunning()
def _check_manager(self):
    node_names = self.get_node_names_and_namespaces()
    found = any(
        f'/{ns}/{name}'.replace('//', '/') == '/op3_manager'
        or name == 'op3_manager'
        for name, ns in node_names
    )
```

---

## Ringkasan Semua File Sumber

| File | Path | Data yang Diambil |
|---|---|---|
| open_cr_module.cpp | `src/ROBOTIS-OP3/open_cr_module/src/` | Battery voltage, button events |
| robotis_controller.cpp | `src/ROBOTIS-Framework/robotis_controller/src/robotis_controller/` | Joint states (pos/vel/effort) |
| OP3.robot | `src/ROBOTIS-OP3/op3_manager/config/` | Joint names, bulk-read items |
| XM540-W270.device | `src/ROBOTIS-Framework/robotis_device/devices/dynamixel/` | Control table addresses |
| StatusMsg.msg | `src/ROBOTIS-Framework-msgs/robotis_controller_msgs/msg/` | Message format untuk voltage |
| read_write.cpp | `src/ROBOTIS-OP3-Demo/op3_read_write_demo/src/` | Pattern untuk manager detection |
| power_monitor_node.py | `src/op3_power_monitor/op3_power_monitor/` | Node utama (subscribe + parse + publish) |

---

## Ringkasan Register Dynamixel XM430-W350

| Register | Address | Length | Unit | Status di OP3 |
|---|---|---|---|---|
| `present_position` | 132 | 4 | raw → radian | ✅ Di bulk-read |
| `present_velocity` | 128 | 4 | raw → rad/s | ❌ Tidak di bulk-read |
| `present_current` | 126 | 2 | 2.69 mA/unit | ❌ Tidak di bulk-read |
| `present_input_voltage` | 144 | 2 | 0.1 V/unit | ❌ Tidak di bulk-read |
| `position_p_gain` | 84 | 2 | raw | ✅ Di bulk-read |
| `position_i_gain` | 82 | 2 | raw | ✅ Di bulk-read |
| `position_d_gain` | 80 | 2 | raw | ✅ Di bulk-read |

> Referensi: [Dynamixel XM430-W350 e-Manual](https://emanual.robotis.com/docs/en/dxl/x/xm430-w350/)
