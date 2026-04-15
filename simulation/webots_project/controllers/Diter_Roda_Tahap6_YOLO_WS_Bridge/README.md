# DITER RODA TAHAP 6 - Monitoring Controller

## Overview
**Passive monitoring controller** untuk laptop yang menerima telemetry dari Orange Pi robot (dikontrol oleh Jetson YOLO) dan menampilkan di Webots simulator + Digital Twin Interface.

## Architecture

```
Jetson Orin ──YOLO──► Orange Pi ──ROS2──► Laptop (Tahap 6)
  (Vision)            (Robot)            (Monitor + Viz)
                         │
                         └──► ESP32 ──► Motors
```

**Key Points:**
- ✅ **Passive Mode**: NO command output to robot
- ✅ **Telemetry Source**: Orange Pi via ROS2
- ✅ **Visualization**: Webots simulator mirrors real robot
- ✅ **Web Display**: Digital Twin Interface via WebSocket
- ✅ **All Tahap 5 Features**: Battery, torque, monitoring

## Requirements

- ROS 2 (Humble atau Jazzy)
- Python 3.8+
- Webots R2023b+
- Python packages:
  - `rclpy`
  - `sensor_msgs`, `geometry_msgs`
  - `websockets` (untuk WebSocket Bridge version)

## Files

```
Diter_Roda_Tahap6_YOLO/
├── Diter_Roda_Tahap6_YOLO.py              # Base monitoring controller
├── Diter_Roda_Tahap6_YOLO_WS_Bridge.py    # WebSocket Bridge version
├── battery_config.json                     # Battery configuration
└── README.md                               # This file
```

## ROS2 Topics (Orange Pi → Laptop)

Controller subscribes to these topics from Orange Pi:

| Topic | Type | Content |
|-------|------|---------|
| `/battery_status` | `sensor_msgs/BatteryState` | Voltage, current, percentage |
| `/motor_status` | `sensor_msgs/JointState` | Wheel velocities (rad/s), torques (Nm) |
| `/robot_velocity` | `geometry_msgs/Twist` | Robot vx, vy, w |

## Usage

### 1. Setup Orange Pi untuk Publish Telemetry

Orange Pi perlu publish telemetry via ROS2. Tambahkan ke script yang sudah ada:

```python
# Di Orange Pi script
from sensor_msgs.msg import BatteryState, JointState
from geometry_msgs.msg import Twist

# Create publishers
battery_pub = node.create_publisher(BatteryState, '/battery_status', 10)
motor_pub = node.create_publisher(JointState, '/motor_status', 10)
velocity_pub = node.create_publisher(Twist, '/robot_velocity', 10)

# Publish data
battery_msg = BatteryState()
battery_msg.voltage = current_voltage
battery_msg.current = current_draw
battery_msg.percentage = battery_percent
battery_pub.publish(battery_msg)

motor_msg = JointState()
motor_msg.name = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
motor_msg.velocity = [w1, w2, w3, w4]  # rad/s
motor_msg.effort = [t1, t2, t3, t4]    # Nm
motor_pub.publish(motor_msg)
```

### 2. Run Laptop Monitoring Controller

**Basic Mode (No WebSocket):**
```bash
# Setup ROS2
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=10
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp

# Set Webots environment
export WEBOTS_HOME=/path/to/webots
export PYTHONPATH=${WEBOTS_HOME}/lib/controller/python:$PYTHONPATH
export LD_LIBRARY_PATH=${WEBOTS_HOME}/lib/controller:$LD_LIBRARY_PATH

# Run Webots with Tahap 6 world file
# Controller akan otomatis load
```

**WebSocket Bridge Mode (With Digital Twin):**
```bash
# 1. Start WebSocket Server
cd /home/codename-hydra/Documents/Digital_Twin_Interface
python3 ws_server.py

# 2. Start Web Interface
npm run dev

# 3. Run Webots dengan WS Bridge controller
# Edit world file untuk point ke: Diter_Roda_Tahap6_YOLO_WS_Bridge.py
```

### 3. Verify Telemetry

Check if topics are visible:
```bash
# Di Laptop
ros2 topic list | grep -E "battery|motor|velocity"

# Monitor incoming data
ros2 topic echo /battery_status
ros2 topic echo /motor_status
```

## Features

### Passive Monitoring
- **NO command output** - purely visualization
- Webots robot wheels mirror real robot movement
- Real-time telemetry display in terminal

### Battery Monitoring
- Voltage, current, power display
- Percentage estimation
- Remaining time calculation

### Motor Monitoring
- Individual wheel velocities (converted to RPM)
- Individual wheel torques (Nm)
- Real-time updates

### WebSocket Integration
- Broadcast telemetry to Digital Twin Interface
- Real-time web visualization
- Battery, motors, system status display

## Troubleshooting

### No Telemetry Received
```bash
# Check ROS_DOMAIN_ID consistency
echo $ROS_DOMAIN_ID  # Should be 10 on both laptop and Orange Pi

# Check topics from Orange Pi
ros2 topic list
ros2 topic hz /battery_status

# Check CycloneDDS peer configuration
cat ~/Documents/cyclonedds.xml
```

### Webots Not Mirroring Robot
- Verify wheel velocities are being published correctly
- Check topic names match exactly
- Ensure data is being received (check terminal logs)

### WebSocket Connection Failed
```bash
# Check WebSocket server is running
lsof -i:8765

# Restart if needed
pkill -f ws_server.py
python3 ws_server.py
```

## System Workflow

**Complete Flow:**
1. **Jetson Orin**: YOLO detection → publish `/yolo_detection`
2. **Orange Pi**: Subscribe YOLO → control motors → publish telemetry
3. **Laptop**: Subscribe telemetry → visualize Webots → broadcast web
4. **Digital Twin**: Display real-time robot status

## Author
Digital Twin BroneRoda Team  
Version: 6.0-Monitor
