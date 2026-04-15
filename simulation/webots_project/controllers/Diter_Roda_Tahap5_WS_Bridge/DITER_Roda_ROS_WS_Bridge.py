#!/usr/bin/env python3
"""
DITER RODA HYBRID: ROS BRIDGE + WEBSOCKET
==========================================
Combines:
- ROS2 publishing to real robot (from ROS Bridge)
- Latency monitoring and safety failsafe (from ROS Bridge)
- WebSocket telemetry broadcasting (from WS Bridge)
- Digital Twin Interface integration (from WS Bridge)

Features:
- Real-time ping monitoring to physical robot
- Auto-stop on high latency (>100ms)
- ROS2 /cmd_vel publishing
- WebSocket telemetry at 5Hz
- Power and torque calculation
- Joystick control with smoothing
"""

import sys
import os
import math
import asyncio
import json
import threading
import queue
from datetime import datetime

# Import base ROS Bridge controller
sys.path.insert(0, '/home/codename-hydra/Documents/BroneRoda/controllers/DITER_Roda_ros_bridge')
from DITER_Roda_ros_bridge import BroneDiterController

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip3 install websockets")
    sys.exit(1)


class DITERRosWebSocketBridge(BroneDiterController):
    """
    Hybrid controller extending ROS Bridge with WebSocket capabilities
    """
    
    def __init__(self, ws_server_url='ws://localhost:8765'):
        # Initialize base ROS Bridge controller
        super().__init__()
        
        # WebSocket Configuration
        self.ws_server_url = ws_server_url
        self.ws_connected = False
        self.last_broadcast_time = 0.0
        self.broadcast_interval = 0.2  # 5Hz (200ms)
        
        # Queue for sending telemetry from main thread to WebSocket thread
        self.telemetry_queue = queue.Queue(maxsize=10)
        
        
        # Battery Tracking Variables
        self.SAVE_FILE = "brone_battery_state.txt"
        self.BATT_CAPACITY_MAH = 5200.0
        self.CELL_COUNT = 6  # Default 6S (22.2V)
        
        # Dynamic Voltage Thresholds (calculated from cell count)
        self.FULL_VOLTAGE = 4.2 * self.CELL_COUNT
        self.EMPTY_VOLTAGE = 3.0 * self.CELL_COUNT
        self.NOMINAL_VOLTAGE = 3.7 * self.CELL_COUNT
        self.VOLTAGE_RANGE = self.FULL_VOLTAGE - self.EMPTY_VOLTAGE
        
        self.R_INTERNAL = 0.05
        
        # Battery energy tracking
        self.total_energy_capacity = (21.0 * (self.BATT_CAPACITY_MAH / 1000.0)) * 3600.0  # Joules
        self.current_energy = self.total_energy_capacity
        
        # Motor specifications for power calculation
        self.I_IDLE = 0.4
        self.I_STALL = 6.0
        self.TORQUE_STALL = 1.96
        self.K_T = self.TORQUE_STALL / (self.I_STALL - self.I_IDLE)
        self.DRIVER_EFFICIENCY = 0.92
        self.P_STATIC = 8.0  # Static power (sensors, computer)
        
        # Power averaging for runtime estimation
        self.avg_power_window = []
        
        # Robot control state (for start/stop program)
        self.robot_enabled = True  # Start enabled by default
        
        # Start WebSocket client in background thread
        self.ws_thread = threading.Thread(target=self._run_ws_client, daemon=True)
        self.ws_thread.start()
        
        print(">Data> WEBSOCKET BRIDGE INITIALIZED")
        print(f"   Server URL: {self.ws_server_url}")
        print(f"   Battery: 6S LiPo {self.BATT_CAPACITY_MAH}mAh")
    
    def _run_ws_client(self):
        """Run WebSocket client in separate thread"""
        asyncio.run(self._ws_client_loop())
    
    async def _ws_client_loop(self):
        """WebSocket client with auto-reconnect and command handling"""
        reconnect_delay = 3.0  # Initial delay
        max_reconnect_delay = 30.0  # Cap at 30 seconds
        connection_attempts = 0
        
        while True:
            try:
                connection_attempts += 1
                if connection_attempts > 1:
                    print(f">> WEBSOCKET: Reconnection attempt #{connection_attempts} (waiting {reconnect_delay:.1f}s)...")
                else:
                    print(f">> WEBSOCKET: Connecting to {self.ws_server_url}...")
                
                async with websockets.connect(
                    self.ws_server_url,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    self.ws_connected = True
                    connection_attempts = 0  # Reset on successful connection
                    reconnect_delay = 3.0  # Reset delay
                    print(">> WEBSOCKET CONNECTED ✓")
                    
                    # Create tasks for both receiving and sending
                    receive_task = asyncio.create_task(self._receive_messages(websocket))
                    send_task = asyncio.create_task(self._send_telemetry(websocket))
                    
                    # Wait for either task to complete (on error or disconnect)
                    done, pending = await asyncio.wait(
                        [receive_task, send_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel pending tasks
                    for task in pending:
                        task.cancel()
                        
            except Exception as e:
                if self.ws_connected:
                    print(f"!! WEBSOCKET DISCONNECTED: {e}")
                elif connection_attempts == 1:
                    print(f"!! WEBSOCKET: Cannot connect to {self.ws_server_url}")
                    print(f"!! WEBSOCKET: Make sure ws_server.py is running!")
                
                self.ws_connected = False
                
                # Wait before reconnect with exponential backoff
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
    
    async def _receive_messages(self, websocket):
        """Receive and handle incoming messages"""
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle commands from frontend (silent unless it's a command)
                if "command" in data:
                    print(f"[CMD] <<< {data.get('command')}")
                    self.handle_command(data)
            except json.JSONDecodeError:
                pass  # Ignore non-JSON messages
    
    async def _send_telemetry(self, websocket):
        """Send queued telemetry data"""
        while True:
            # Check queue periodically
            await asyncio.sleep(0.05)  # 20Hz check rate
            
            while not self.telemetry_queue.empty():
                try:
                    telemetry = self.telemetry_queue.get_nowait()
                    await websocket.send(json.dumps(telemetry))
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"!! Error sending telemetry: {e}")
                    raise  # Will trigger reconnect
    
    def handle_command(self, data):
        """Handle commands received from frontend"""
        command = data.get("command")
        
        if command == "start_program":
            print(">Data> RECEIVED START PROGRAM COMMAND")
            # Enable robot control (could add a flag to enable/disable control)
            self.robot_enabled = True
            
        elif command == "stop_program":
            print(">Data> RECEIVED STOP PROGRAM COMMAND")
            # Disable robot and stop all motors
            self.robot_enabled = False
            for wheel in self.wheels:
                wheel.setVelocity(0.0)
            # Reset smoothing
            self.cur_vx = 0.0
            self.cur_vy = 0.0
            self.cur_w = 0.0
        
        elif command == "emergency_stop":
            print(">> RECEIVED EMERGENCY STOP COMMAND")
            # Stop all motors immediately
            for wheel in self.wheels:
                wheel.setVelocity(0.0)
            # Reset smoothing
            self.cur_vx = 0.0
            self.cur_vy = 0.0
            self.cur_w = 0.0
            
        elif command == "reset_system":
            print(">Data> RECEIVED RESET COMMAND")
            # Reset internal state
            self.cur_vx = 0.0
            self.cur_vy = 0.0
            self.cur_w = 0.0
            # Reset battery to full
            self.current_energy = self.total_energy_capacity
            self.avg_power_window = []
            self.save_battery_state()
            print(">Data> System reset complete - battery restored to 100%")
            
        elif command == "update_battery_config":
            battery_type = data.get("battery_type", "3S")
            series_count = int(data.get("series_count", 1))
            
            # Parse cell count from string (e.g. "3S" -> 3)
            try:
                cells_per_pack = int(battery_type.replace("S", ""))
            except:
                cells_per_pack = 3
                
            self.CELL_COUNT = cells_per_pack * series_count
            
            # Recalculate voltage thresholds
            self.FULL_VOLTAGE = 4.2 * self.CELL_COUNT
            self.EMPTY_VOLTAGE = 3.0 * self.CELL_COUNT
            self.NOMINAL_VOLTAGE = 3.7 * self.CELL_COUNT
            self.VOLTAGE_RANGE = self.FULL_VOLTAGE - self.EMPTY_VOLTAGE
            
            # Update total energy capacity (assuming same mAh, just different voltage)
            # Energy (J) = Voltage (V) * Capacity (Ah) * 3600
            self.total_energy_capacity = (self.NOMINAL_VOLTAGE * (self.BATT_CAPACITY_MAH / 1000.0)) * 3600.0
            
            # Reset current energy to full on config change?
            # Or scale it? Let's reset to full for safety/simplicity
            self.current_energy = self.total_energy_capacity
            
            print(f">Data> RECEIVED BATTERY CONFIG: {battery_type} x{series_count} -> {self.CELL_COUNT}S ({self.NOMINAL_VOLTAGE:.1f}V)")
    
    def save_battery_state(self):
        """Save current battery energy to file"""
        try:
            with open(self.SAVE_FILE, "w") as f:
                f.write(str(self.current_energy))
        except Exception as e:
            print(f"Warning: Could not save battery state: {e}")
    
    def load_battery_state(self):
        """Load battery energy from file"""
        if not os.path.exists(self.SAVE_FILE):
            return None
        try:
            with open(self.SAVE_FILE, "r") as f:
                return float(f.read())
        except Exception as e:
            print(f"Warning: Could not load battery state: {e}")
            return None
    
    def calculate_diter_metrics(self, dt, torques):
        """
        Calculate battery metrics based on torque load
        Returns: (power, current, voltage)
        """
        # Calculate State of Charge
        # Calculate State of Charge
        soc = max(0.0, self.current_energy / self.total_energy_capacity)
        v_open_circuit = self.EMPTY_VOLTAGE + (self.VOLTAGE_RANGE * soc)
        
        # Calculate motor current from torque
        i_motors_pure = 0.0
        for tau in torques:
            i_load = abs(tau) / self.K_T
            i_motors_pure += (i_load + self.I_IDLE)
        
        # Account for driver efficiency
        i_motors_drawn = i_motors_pure / self.DRIVER_EFFICIENCY
        
        # Add static current (sensors, computer)
        i_static = self.P_STATIC / v_open_circuit
        i_total = i_motors_drawn + i_static
        
        # Calculate terminal voltage (voltage sag)
        v_terminal = v_open_circuit - (i_total * self.R_INTERNAL)
        if v_terminal < 0:
            v_terminal = 0.0
        
        # Calculate power and energy consumption
        total_power = v_terminal * i_total
        consumed_joules = total_power * dt
        self.current_energy -= consumed_joules
        
        # Update power averaging for runtime estimation
        self.avg_power_window.append(total_power)
        if len(self.avg_power_window) > (5.0 / dt):
            self.avg_power_window.pop(0)
        
        return total_power, i_total, v_terminal
    
    def estimate_runtime(self):
        """Estimate remaining runtime in hours"""
        if len(self.avg_power_window) == 0:
            return 24.0  # Default estimate
        
        avg_power = sum(self.avg_power_window) / len(self.avg_power_window)
        if avg_power < 1.0:
            return 999.0  # Essentially infinite at idle
        
        remaining_wh = self.current_energy / 3600.0
        return remaining_wh / avg_power
    
    def calculate_rpm_from_velocity(self, angular_velocity_rad_s):
        """Convert wheel angular velocity to RPM"""
        # RPM = (rad/s) * (60 / 2π)
        return angular_velocity_rad_s * 60.0 / (2.0 * math.pi)
    
    def prepare_telemetry_data(self, power, current, voltage, wheel_velocities):
        """
        Prepare telemetry data in format expected by Digital Twin Interface
        """
        # Calculate cell voltage (assuming 6S battery)
        cell_voltage = voltage / 6.0
        
        # Get motor torques
        torques = [abs(wheel.getTorqueFeedback()) for wheel in self.wheels]
        
        # Calculate RPM for each wheel
        wheel_rpms = {
            'FL': round(self.calculate_rpm_from_velocity(wheel_velocities[0])),
            'FR': round(self.calculate_rpm_from_velocity(wheel_velocities[1])),
            'RL': round(self.calculate_rpm_from_velocity(wheel_velocities[2])),
            'RR': round(self.calculate_rpm_from_velocity(wheel_velocities[3]))
        }
        
        # Use absolute values for average - mecanum wheels rotate in opposite directions
        avg_rpm = round(sum([abs(rpm) for rpm in wheel_rpms.values()]) / 4.0)
        
        # Build complete telemetry packet
        data = {
            "timestamp": datetime.now().isoformat(),
            "electrical": {
                "voltage": round(voltage, 2),
                "current": round(current, 2),
                "power": round(power, 2),
                "cell_voltage": round(cell_voltage, 3)
            },
            "battery": {
                "soc": round(max(0.0, min(100.0, (self.current_energy / self.total_energy_capacity) * 100.0)), 1),
                "runtime_hours": round(self.estimate_runtime(), 2)
            },
            "motors": {
                "torques": {
                    "FL": round(torques[0], 3),
                    "FR": round(torques[1], 3),
                    "RL": round(torques[2], 3),
                    "RR": round(torques[3], 3)
                },
                "rpm": wheel_rpms,
                "avg_rpm": avg_rpm
            },
            "motion": {
                "vx": round(self.cur_vx, 3),
                "vy": round(self.cur_vy, 3),
                "w": round(self.cur_w, 3)
            },
            "system": {
                "uptime": round(self.robot.getTime(), 2),
                "ping_ms": round(self.latency_ms, 0)  # From ROS Bridge latency monitor
            }
        }
        
        return data
    
    def run(self):
        """Override run method to add WebSocket broadcasting"""
        self.attempt_connection()
        
        print("\n=== HYBRID CONTROLLER: ROS2 + WEBSOCKET ===")
        print(f"Max Latency: {self.MAX_SAFE_LATENCY}ms | Broadcast: {self.broadcast_interval*1000:.0f}ms")
        print("Time  | Status   | Power  | Ping    | Velocity | WS")
        
        step_counter = 0
        
        try:
            while self.robot.step(self.timestep) != -1:
                # 1. Get joystick input (only if enabled)
                if self.robot_enabled:
                    tvx, tvy, tw = self.get_input()
                else:
                    tvx, tvy, tw = 0.0, 0.0, 0.0
                
                # 2. SAFETY CHECK (from ROS Bridge)
                if not self.robot_enabled:
                    # PROGRAM STOPPED
                    vx, vy, w = 0.0, 0.0, 0.0
                    self.cur_vx = 0.0
                    self.cur_vy = 0.0
                    self.cur_w = 0.0
                    is_moving = False
                    status_display = "STOPPED"
                elif self.is_lagging:
                    # HIGH LATENCY: Force stop
                    vx, vy, w = 0.0, 0.0, 0.0
                    self.cur_vx = 0.0
                    self.cur_vy = 0.0
                    self.cur_w = 0.0
                    is_moving = False
                    status_display = "LAG STOP"
                else:
                    # SAFE: Normal operation
                    vx, vy, w = self.smooth(tvx, tvy, tw)
                    is_moving = (abs(tvx)>0 or abs(tvy)>0 or abs(tw)>0 or abs(vx)>0.01)
                    status_display = "RUN" if is_moving else "IDLE"
                
                # 3. Update motors and ROS
                self.update_motors(vx, vy, w)
                self.update_ros(vx, vy, w)
                
                # 4. Get motor torques
                torques = [abs(wheel.getTorqueFeedback()) for wheel in self.wheels]
                
                # 5. Calculate power and battery metrics
                dt = self.timestep / 1000.0  # Convert to seconds
                power, current, voltage = self.calculate_diter_metrics(dt, torques)
                
                # 6. Get wheel velocities for telemetry
                vels = [
                    (-self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel,
                    (-self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel,
                    ( self.cos_a * vx - self.sin_a * vy + self.L * w) / self.r_wheel,
                    ( self.cos_a * vx + self.sin_a * vy + self.L * w) / self.r_wheel
                ]
                
                # 7. WEBSOCKET BROADCAST
                current_time = self.robot.getTime()
                if current_time - self.last_broadcast_time >= self.broadcast_interval:
                    telemetry = self.prepare_telemetry_data(power, current, voltage, vels)
                    
                    # Put in queue (non-blocking, thread-safe)
                    try:
                        self.telemetry_queue.put_nowait(telemetry)
                    except queue.Full:
                        pass  # Skip if queue full
                    
                    self.last_broadcast_time = current_time
                
                # 7. Dashboard display
                if step_counter % 20 == 0:
                    if status_display != "LAG STOP":
                        if power > 400:
                            status_display = "STALL!!"
                    
                    lat_str = f"{self.latency_ms:.0f}ms"
                    if self.latency_ms > 900:
                        lat_str = "TIMEOUT"
                    
                    ws_status = "✓" if self.ws_connected else "✗"
                    
                    print(f"{current_time:05.1f} | {status_display:^8} | {power:05.1f}W | {lat_str:\u003c7} | V:{vx:+.2f} | {ws_status}")
                
                step_counter += 1
                
                # Spin ROS (from base class)
                import rclpy
                rclpy.spin_once(self.ros_node, timeout_sec=0)
                
        except Exception as e:
            print(f"Runtime Error: {e}")
            
        print("\n>> WEBOTS RESET DETECTED. RESTARTING...")
        try:
            self.ros_node.destroy_node()
            import rclpy
            rclpy.shutdown()
            import pygame
            pygame.quit()
        except:
            pass
        sys.exit(0)


if __name__ == "__main__":
    # You can customize WebSocket server URL here
    # Default: ws://localhost:8765
    bridge = DITERRosWebSocketBridge()
    bridge.run()
