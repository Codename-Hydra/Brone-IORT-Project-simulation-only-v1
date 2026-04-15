"""
BRONE DITER TAHAP 6: Passive Monitoring Controller
===================================================
Laptop-side monitoring for robot controlled by Jetson → Orange Pi.

Purpose:
- Subscribe telemetry from Orange Pi (battery, motors, state)
- Visualize in Webots simulator (mirror real robot)
- Display in Digital Twin Interface via WebSocket
- All Tahap 5 features (battery estimation, torque monitoring)

Key: NO command output - purely monitoring mode

Author: Digital Twin BroneRoda Team
Version: 6.0-Monitor
"""

import os
import time
import math
import threading
from controller import Robot

# ROS2 imports
try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import BatteryState, JointState
    from geometry_msgs.msg import Twist
except ImportError:
    print("ERROR: ROS2 not available. Make sure to source ROS2 setup.")
    import sys
    sys.exit(1)


class TelemetrySubscriber(Node):
    """ROS2 Node to subscribe telemetry from Orange Pi"""
    
    def __init__(self):
        super().__init__('brone_telemetry_monitor')
        
        # Storage for latest telemetry data
        self.battery_voltage = 24.0
        self.battery_current = 0.0
        self.battery_percentage = 100.0
        
        self.wheel_velocities = [0.0, 0.0, 0.0, 0.0]  # rad/s
        self.wheel_torques = [0.0, 0.0, 0.0, 0.0]     # Nm
        
        self.robot_vx = 0.0
        self.robot_vy = 0.0
        self.robot_w = 0.0
        
        self.data_received = False
        
        # Subscribe to Orange Pi telemetry
        self.battery_sub = self.create_subscription(
            BatteryState,
            '/battery_status',
            self.battery_callback,
            10
        )
        
        self.motor_sub = self.create_subscription(
            JointState,
            '/motor_status',
            self.motor_callback,
            10
        )
        
        self.velocity_sub = self.create_subscription(
            Twist,
            '/robot_velocity',
            self.velocity_callback,
            10
        )
        
        self.get_logger().info("✓ Telemetry Subscriber Active")
        self.get_logger().info("  Listening for:")
        self.get_logger().info("    - /battery_status (BatteryState)")
        self.get_logger().info("    - /motor_status (JointState)")
        self.get_logger().info("    - /robot_velocity (Twist)")
    
    def battery_callback(self, msg):
        """Receive battery data from Orange Pi"""
        self.battery_voltage = msg.voltage
        self.battery_current = msg.current
        self.battery_percentage = msg.percentage
        self.data_received = True
        
        self.get_logger().info(
            f"Battery: {self.battery_voltage:.1f}V, {self.battery_percentage:.0f}%",
            throttle_duration_sec=2.0
        )
    
    def motor_callback(self, msg):
        """Receive motor data from Orange Pi"""
        # JointState: name=['wheel1', 'wheel2', 'wheel3', 'wheel4']
        #             velocity=[w1, w2, w3, w4] (rad/s)
        #             effort=[t1, t2, t3, t4] (Nm)
        
        if len(msg.velocity) >= 4:
            self.wheel_velocities = list(msg.velocity[:4])
        
        if len(msg.effort) >= 4:
            self.wheel_torques = list(msg.effort[:4])
        
        self.data_received = True
    
    def velocity_callback(self, msg):
        """Receive robot velocity from Orange Pi"""
        self.robot_vx = msg.linear.x
        self.robot_vy = msg.linear.y
        self.robot_w = msg.angular.z
        self.data_received = True


class BroneDiterMonitor:
    """
    Webots monitoring controller for real robot
    
    Features:
    - Passive monitoring (no command output)
    - Subscribe telemetry from Orange Pi
    - Visualize in Webots
    - Battery and torque display
    """
    
    def __init__(self):
        # --- 1. INIT ROBOT & WEBOTS ---
        self.robot = Robot()
        self.timestep = int(self.robot.getBasicTimeStep())
        
        # --- 2. BATTERY SPECS (for estimation reference) ---
        self.BATT_NOMINAL_VOLTAGE = 22.2
        self.BATT_CAPACITY_MAH = 5200.0
        self.CUTOFF_VOLTAGE = 18.5
        
        # --- 3. SETUP WEBOTS DEVICES ---
        self.wheel_names = ['wheel1', 'wheel2', 'wheel3', 'wheel4']
        self.wheels = []
        for name in self.wheel_names:
            m = self.robot.getDevice(name)
            m.setPosition(float('inf'))
            m.setVelocity(0.0)
            self.wheels.append(m)
        
        # --- 4. INIT ROS2 ---
        if not rclpy.ok():
            rclpy.init()
        
        self.telemetry_node = TelemetrySubscriber()
        
        # Thread for ROS2 spinning
        self.ros_thread = threading.Thread(target=self._spin_ros, daemon=True)
        self.ros_thread.start()
        
        # Logging
        self.last_log = 0.0
        
        print("\n" + "="*50)
        print("BRONE DITER TAHAP 6: MONITOR MODE")
        print("="*50)
        print("Mode: Passive Monitoring")
        print("Source: Orange Pi Robot Telemetry")
        print("Output: Webots Visualization + Digital Twin")
        print("="*50 + "\n")
    
    def _spin_ros(self):
        """Spin ROS2 node in separate thread"""
        try:
            rclpy.spin(self.telemetry_node)
        except Exception as e:
            print(f"ROS2 spin error: {e}")
    
    def update_webots_from_telemetry(self):
        """Update Webots robot to mirror real robot state using Orange Pi kinematics"""
        # Get robot velocity from telemetry (normalized -1.0 to +1.0)
        # These values come from Orange Pi which does: last_vx = Vx / 200.0
        # SWAP vx and vy to fix 90-degree rotation in Webots
        vx_normalized = -self.telemetry_node.robot_vy  # Swap: use vy for forward/backward (inverted per user request)
        vy_normalized = self.telemetry_node.robot_vx  # Swap: use vx for left/right
        w_normalized = self.telemetry_node.robot_w    # -1.0 to +1.0 (but we ignore rotation)
        
        # Scale to actual m/s (max velocity ~0.5 m/s for reduced speed)
        # Scale to actual m/s (max velocity ~0.25 m/s for visual match)
        MAX_LINEAR_VEL = 0.25  # m/s - slower speed
        vx = vx_normalized * MAX_LINEAR_VEL
        vy = vy_normalized * MAX_LINEAR_VEL
        w = 0.0  # No rotation for YOLO tracking
        
        # Apply inverse kinematics to get wheel velocities
        # Mecanum wheel configuration (same as Tahap 5)
        L = 0.208  # Robot half-width + half-length (m)
        r_wheel = 0.06  # Wheel radius (m)
        sin_a = 0.7071  # sin(45°)
        cos_a = 0.7071  # cos(45°)
        
        # Inverse kinematics for mecanum wheels
        # Formula from BroneDiterFusion/Orange Pi
        w1 = (1.0/r_wheel) * (-vx * cos_a + vy * sin_a + L * w)
        w2 = (1.0/r_wheel) * (-vx * cos_a - vy * sin_a + L * w)
        w3 = (1.0/r_wheel) * (vx * cos_a - vy * sin_a + L * w)
        w4 = (1.0/r_wheel) * (vx * cos_a + vy * sin_a + L * w)
        
        # Correction multipliers (from Tahap 5)
        INV_W1 = -1.0
        INV_W2 = -1.0
        INV_W3 = -1.0
        INV_W4 = -1.0
        
        corrections = [INV_W1, INV_W2, INV_W3, INV_W4]
        wheel_vels = [w1, w2, w3, w4]
        
        # Set wheel velocities with corrections
        for i, wheel in enumerate(self.wheels):
            final_vel = wheel_vels[i] * corrections[i]
            wheel.setVelocity(final_vel)
    
    def run(self):
        """Main monitoring loop"""
        print(">> Waiting for telemetry from Orange Pi...")
        print("   (Make sure Orange Pi is publishing to ROS2 topics)")
        print()
        
        # Wait for first data
        timeout = 10.0
        start_time = self.robot.getTime()
        while self.robot.step(self.timestep) != -1:
            if self.telemetry_node.data_received:
                print("✓ Telemetry received! Starting visualization...\n")
                break
            
            if self.robot.getTime() - start_time > timeout:
                print("⚠ WARNING: No telemetry received after 10s")
                print("   Check if Orange Pi is running and publishing topics")
                print("   Continuing in demo mode...\n")
                break
        
        print("=== MONITORING ACTIVE ===")
        print("Format: [Torsi W1..W4] | Volt | Amp | Batt%")
        print()
        
        while self.robot.step(self.timestep) != -1:
            t = self.robot.getTime()
            
            # --- A. UPDATE WEBOTS FROM TELEMETRY ---
            self.update_webots_from_telemetry()
            
            # --- B. GET TELEMETRY DATA ---
            voltage = self.telemetry_node.battery_voltage
            current = self.telemetry_node.battery_current
            batt_percent = self.telemetry_node.battery_percentage
            torques = self.telemetry_node.wheel_torques
            
            # --- C. CALCULATE DERIVED METRICS ---
            power = voltage * current
            
            # --- D. LOGGING DISPLAY ---
            if t - self.last_log > 0.5:  # Update every 0.5 sec
                # Format torques
                tau_str = " ".join([f"{val:+5.2f}" for val in torques])
                
                # Print telemetry
                status = "✓" if self.telemetry_node.data_received else "⚠"
                print(f"[{status}] T:{t:05.1f} | Tau:[{tau_str}] Nm | {voltage:5.2f}V | {current:5.2f}A | {power:06.2f}W | Bat:{batt_percent:04.1f}%")
                
                self.last_log = t
    
    def __del__(self):
        """Cleanup ROS2 on exit"""
        try:
            if hasattr(self, 'telemetry_node'):
                self.telemetry_node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
        except:
            pass


if __name__ == "__main__":
    controller = BroneDiterMonitor()
    controller.run()
