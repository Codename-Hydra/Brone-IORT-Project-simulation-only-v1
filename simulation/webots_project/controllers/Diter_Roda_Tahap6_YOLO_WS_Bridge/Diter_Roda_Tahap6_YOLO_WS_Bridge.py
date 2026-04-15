#!/usr/bin/env python3
"""
DITER RODA TAHAP 6 - WEBSOCKET BRIDGE (MONITORING MODE)
========================================================
Extends Tahap 6 Monitoring Controller with WebSocket broadcasting
for real-time integration with Digital Twin Interface.

Features:
- Passive monitoring (no control output)
- Subscribe telemetry from Orange Pi (battery, motors, velocity)
- Visualize in Webots
- Broadcast to Digital Twin Interface via WebSocket
- All Tahap 5 features maintained in monitoring context

Author: Digital Twin BroneRoda Team  
Version: 6.0-Monitor-WS
"""

import os
import sys
import math
import asyncio
import json
import threading
import queue
import random # Added for simulated ping
import time
from datetime import datetime

# Import base Tahap 6 controller
sys.path.insert(0, os.path.dirname(__file__))
from Diter_Roda_Tahap6_YOLO import BroneDiterMonitor

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip3 install websockets")
    sys.exit(1)


class DITERTahap6WebSocketBridge(BroneDiterMonitor):
    """
    Extended DITER Tahap 6 Monitoring controller with WebSocket integration
    """
    
    def __init__(self, ws_server_url='ws://localhost:8765'):
        # Initialize base monitoring controller
        super().__init__()
        
        # WebSocket Configuration
        self.ws_server_url = ws_server_url
        self.ws_connected = False
        self.last_broadcast_time = 0.0
        self.broadcast_interval = 0.2  # 5Hz (200ms)
        
        # Queue for sending telemetry from main thread to WebSocket thread
        self.telemetry_queue = queue.Queue(maxsize=10)
        
        # Start WebSocket client in background thread
        self.ws_thread = threading.Thread(target=self._run_ws_client, daemon=True)
        self.ws_thread.start()
        
        print(">> WEBSOCKET BRIDGE INITIALIZED (Monitoring Mode)")
        print(f"   Server URL: {self.ws_server_url}")

        # Create Publisher for System Enable
        from std_msgs.msg import Bool
        self.enable_pub = self.telemetry_node.create_publisher(Bool, '/system/enable', 10)
        
        # Real Ping Measurement
        self.ping_ip = "10.30.117.200"  # Orange Pi
        self.current_ping_ms = 0
        self.ping_thread = threading.Thread(target=self._run_ping_monitor, daemon=True)
        self.ping_thread.start()

    def publish_enable(self, state):
        """Publish system enable state to ROS2"""
        from std_msgs.msg import Bool
        msg = Bool()
        msg.data = state
        self.enable_pub.publish(msg)
        print(f">> PUBLISHED STATE: {'ENABLED' if state else 'DISABLED'}")
    
    def _run_ping_monitor(self):
        """Monitor real network latency to Orange Pi"""
        import subprocess
        import re
        
        while True:
            try:
                # Ping with 1 packet, 1s timeout
                result = subprocess.run(
                    ['ping', '-c', '1', '-W', '1', self.ping_ip],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                if result.returncode == 0:
                    # Parse time=X.X ms
                    match = re.search(r'time=([\d.]+)', result.stdout)
                    if match:
                        self.current_ping_ms = int(float(match.group(1)))
                    else:
                        self.current_ping_ms = 0
                else:
                    self.current_ping_ms = 999  # Timeout/Unreachable
                    
            except Exception as e:
                print(f"Ping error: {e}")
                self.current_ping_ms = -1
                
            time.sleep(1.0)  # Check every 1s

    def _run_ws_client(self):
        """Run WebSocket client in separate thread"""
        asyncio.run(self._ws_client_loop())
    
    async def _ws_client_loop(self):
        """WebSocket client with auto-reconnect"""
        while True:
            try:
                async with websockets.connect(
                    self.ws_server_url,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    self.ws_connected = True
                    print(">> WEBSOCKET CONNECTED")
                    
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
                self.ws_connected = False
                
                # Wait before reconnect
                await asyncio.sleep(3.0)
    
    async def _receive_messages(self, websocket):
        """Receive and handle incoming messages"""
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle commands from frontend (monitoring mode - limited commands)
                if "command" in data:
                    command = data.get("command")
                    print(f">> RECEIVED COMMAND: {command}")
                    
                    if command == "start_program":
                        self.publish_enable(True)
                    elif command == "stop_program":
                        self.publish_enable(False)
                    elif command == "reset_system":
                        # Optional: handle reset
                        pass
                    
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
    
    def calculate_rpm_from_velocity(self, angular_velocity_rad_s):
        """Convert wheel angular velocity to RPM"""
        # RPM = (rad/s) * (60 / 2π)
        return angular_velocity_rad_s * 60.0 / (2.0 * math.pi)
    
    def prepare_telemetry_data(self, voltage, current, power, torques):
        """
        Prepare telemetry data in format expected by Digital Twin Interface
        """
        # Calculate battery metrics
        batt_percent = self.telemetry_node.battery_percentage
        
        # Calculate runtime estimation
        # Capacity: 5200mAh = 5.2Ah
        battery_capacity_ah = 5.2
        
        if current > 0.5:
            runtime = battery_capacity_ah / current
            self.last_valid_runtime = runtime
        else:
            # Use last valid runtime if available, else 99.0
            runtime = getattr(self, 'last_valid_runtime', 99.0)
        
        # Calculate cell voltage (assume 6S configuration)
        cell_voltage = voltage / 6.0
        
        # Get wheel velocities from telemetry
        wheel_vels = self.telemetry_node.wheel_velocities
        
        # Calculate RPM for each wheel
        wheel_rpms = {
            'FL': round(self.calculate_rpm_from_velocity(wheel_vels[0])),
            'FR': round(self.calculate_rpm_from_velocity(wheel_vels[1])),
            'RL': round(self.calculate_rpm_from_velocity(wheel_vels[2])),
            'RR': round(self.calculate_rpm_from_velocity(wheel_vels[3]))
        }
        
        avg_rpm = round(sum(wheel_rpms.values()) / 4.0)
        
        # Get motion data
        vx = self.telemetry_node.robot_vx
        vy = self.telemetry_node.robot_vy
        w = self.telemetry_node.robot_w
        
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
                "soc": round(batt_percent, 1),
                "runtime_hours": round(runtime, 2)
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
                "vx": round(vx, 3),
                "vy": round(vy, 3),
                "w": round(w, 3)
            },
            "system": {
                "uptime": round(self.robot.getTime(), 2),
                "ping_ms": self.current_ping_ms  # Real ICMP Ping Value
            }
        }
        
        return data
    
    def run(self):
        """Override run method to add WebSocket broadcasting"""
        print("\n=== DITER TAHAP 6: WEBSOCKET MONITORING ACTIVE ===")
        print("Mode: Passive Monitoring (No Control Output)")
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
        print("Format: [Torsi W1..W4] | Volt | Amp | Power | Batt% | WS")
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
            
            # --- D. WEBSOCKET BROADCAST ---
            if t - self.last_broadcast_time >= self.broadcast_interval:
                telemetry = self.prepare_telemetry_data(voltage, current, power, torques)
                
                # Put in queue (non-blocking, thread-safe)
                try:
                    self.telemetry_queue.put_nowait(telemetry)
                except queue.Full:
                    pass  # Skip if queue full
                
                self.last_broadcast_time = t
            
            # --- E. LOGGING DISPLAY ---
            if t - self.last_log > 0.5:  # Update every 0.5 sec
                # Format torques
                tau_str = " ".join([f"{val:+5.2f}" for val in torques])
                
                # WebSocket status
                ws_status = "✓" if self.ws_connected else "✗"
                
                # Print telemetry
                status = "✓" if self.telemetry_node.data_received else "⚠"
                print(f"[{status}] T:{t:05.1f} | Tau:[{tau_str}] Nm | {voltage:5.2f}V | {current:5.2f}A | {power:06.2f}W | Bat:{batt_percent:04.1f}% | WS:{ws_status}")
                
                self.last_log = t


if __name__ == "__main__":
    # You can customize WebSocket server URL here
    # Default: ws://localhost:8765
    bridge = DITERTahap6WebSocketBridge()
    bridge.run()
