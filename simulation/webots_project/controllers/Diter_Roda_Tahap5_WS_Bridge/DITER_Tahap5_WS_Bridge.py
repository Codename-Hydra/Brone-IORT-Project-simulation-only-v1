#!/usr/bin/env python3
"""
DITER RODA TAHAP 5 - WEBSOCKET BRIDGE
======================================
Extends BroneDiterFusion controller with WebSocket broadcasting
for real-time integration with Digital Twin Interface.

Features:
- All DITER Tahap 5 functionality (battery monitoring, motor control)
- Real-time telemetry broadcast at 5Hz
- Auto-reconnect WebSocket client
- RPM calculation from wheel velocities
- Motion data tracking
"""

import os
import sys
import math
import asyncio
import json
import threading
import queue
from datetime import datetime

# Import original controller
sys.path.insert(0, os.path.dirname(__file__))
from Diter_Roda_Tahap5_controller import BroneDiterFusion

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip3 install websockets")
    sys.exit(1)


class DITERTahap5WebSocketBridge(BroneDiterFusion):
    """
    Extended DITER Tahap 5 controller with WebSocket integration
    """
    
    def __init__(self, ws_server_url='ws://localhost:8765'):
        # Initialize base controller
        super().__init__()
        
        # WebSocket Configuration
        self.ws_server_url = ws_server_url
        self.ws_connected = False
        self.last_broadcast_time = 0.0
        self.broadcast_interval = 0.2  # 5Hz (200ms)
        
        # Track motion data
        self.current_vx = 0.0
        self.current_vy = 0.0
        self.current_w = 0.0
        
        # Wheel velocities for RPM calculation
        self.wheel_velocities = [0.0, 0.0, 0.0, 0.0]
        
        # Start WebSocket client in background thread
        self.ws_thread = threading.Thread(target=self._run_ws_client, daemon=True)
        self.ws_thread.start()
        
        # Add reset tracking
        self.uptime_offset = 0.0  # For reset functionality
        self.websocket_connection = None  # Store active connection
        
        # Queue for sending telemetry from main thread to WebSocket thread
        self.telemetry_queue = queue.Queue(maxsize=10)
        
        print(">> WEBSOCKET BRIDGE INITIALIZED")
        print(f"   Server URL: {self.ws_server_url}")
    
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
                    self.websocket_connection = websocket
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
                self.websocket_connection = None
                
                # Wait before reconnect with exponential backoff
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
    
    async def _receive_messages(self, websocket):
        """Receive and handle incoming messages"""
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle commands from frontend
                if "command" in data:
                    await self.handle_command(data)
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
    
    async def handle_command(self, data):
        """Handle commands received from frontend"""
        command = data.get("command")
        
        if command == "reset_system":
            print(">> RECEIVED RESET COMMAND - Resetting system...")
            self.reset_system()
            
        elif command == "update_battery_config":
            battery_type = data.get("battery_type")
            series_count = data.get("series_count")
            print(f">> RECEIVED BATTERY CONFIG: {battery_type} x{series_count}")
            # Battery config update logic can be added here
            # For now, just acknowledge
    
    def reset_system(self):
        """Reset all system data and counters"""
        # Reset battery tracking
        current_time = self.robot.getTime()
        self.uptime_offset = current_time  # Set offset so uptime shows 0
        
        # Reset energy to full capacity
        self.current_energy = self.total_energy_capacity
        
        # Reset motion tracking
        self.current_vx = 0.0
        self.current_vy = 0.0
        self.current_w = 0.0
        
        # Reset wheel velocities
        self.wheel_velocities = [0.0, 0.0, 0.0, 0.0]
        
        # Stop all motors
        for wheel in self.wheels:
            wheel.setVelocity(0.0)
        
        # Save reset state
        self.save_battery_state()
        
        print(">> SYSTEM RESET COMPLETE - All data cleared")
        
        # Immediately send reset telemetry data
        telemetry = self.prepare_telemetry_data(
            voltage=self.NOMINAL_VOLTAGE,
            current=0.0,
            power=0.0,
            torques=[0.0, 0.0, 0.0, 0.0]
        )
        asyncio.run(self.broadcast_telemetry(telemetry))
    
    def calculate_rpm_from_velocity(self, angular_velocity_rad_s):
        """Convert wheel angular velocity to RPM"""
        # RPM = (rad/s) * (60 / 2π)
        return angular_velocity_rad_s * 60.0 / (2.0 * math.pi)
    
    def prepare_telemetry_data(self, voltage, current, power, torques):
        """
        Prepare telemetry data in format expected by Digital Twin Interface
        """
        # Calculate battery metrics
        soc = max(0.0, min(100.0, (self.current_energy / self.total_energy_capacity) * 100.0))
        runtime = self.estimate_runtime()
        
        # Calculate cell voltage (6S = 6 cells)
        cell_voltage = voltage / 6.0
        
        # Calculate RPM for each wheel
        wheel_rpms = {
            'FL': round(self.calculate_rpm_from_velocity(self.wheel_velocities[0])),
            'FR': round(self.calculate_rpm_from_velocity(self.wheel_velocities[1])),
            'RL': round(self.calculate_rpm_from_velocity(self.wheel_velocities[2])),
            'RR': round(self.calculate_rpm_from_velocity(self.wheel_velocities[3]))
        }
        
        avg_rpm = round(sum(wheel_rpms.values()) / 4.0)
        
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
                "soc": round(soc, 1),
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
                "vx": round(self.current_vx, 3),
                "vy": round(self.current_vy, 3),
                "w": round(self.current_w, 3)
            },
            "system": {
                "uptime": round(self.robot.getTime() - self.uptime_offset, 2),
                "ping_ms": 0  # Not applicable for simulation
            }
        }
        
        return data
    
    async def broadcast_telemetry(self, data):
        """Send telemetry data to WebSocket server using queue (thread-safe)"""
        try:
            self.telemetry_queue.put_nowait(data)
        except queue.Full:
            # Queue full, skip this data point
            pass
    
    def run(self):
        """Override run method to add WebSocket broadcasting"""
        self.wait_for_user_selection()

        print("\n=== DITER TAHAP 5: WEBSOCKET BRIDGE ACTIVE ===")
        print(f"Batt: 6S (2x 3S) | Cap: {self.BATT_CAPACITY_MAH}mAh")
        print("Time  | Torsi (Nm)      | Volt  | Amp   | Watt  | Bat% | Est. | WS")
        
        while self.robot.step(self.timestep) != -1:
            dt = self.timestep / 1000.0
            t = self.robot.getTime()
            
            # --- CONTROL ---
            vx, vy, w = self.get_input()
            
            # Store motion data for telemetry
            self.current_vx = vx
            self.current_vy = vy
            self.current_w = w
            
            vels = self.invers_kinematics(vx, vy, w)
            
            # --- ACTUATION ---
            for i, m in enumerate(self.wheels):
                correction = [self.INV_W1, self.INV_W2, self.INV_W3, self.INV_W4][i]
                target_v = vels[i] * correction
                final_v = max(min(target_v, self.MAX_SPEED), -self.MAX_SPEED)
                m.setVelocity(final_v)
                
                # Store actual velocity for RPM calculation
                self.wheel_velocities[i] = final_v

            # --- MONITORING ---
            power, current, voltage, torques = self.calculate_diter_metrics(dt)
            
            # Safety Check
            if voltage <= self.CUTOFF_VOLTAGE:
                print(f"\n!!! LOW BATTERY PROTECT: {voltage:.2f}V !!!")
                self.save_battery_state()
                for w_dev in self.wheels: w_dev.setVelocity(0)
                break

            # --- WEBSOCKET BROADCAST ---
            if t - self.last_broadcast_time >= self.broadcast_interval:
                telemetry = self.prepare_telemetry_data(voltage, current, power, torques)
                
                # Put in queue (non-blocking, thread-safe)
                try:
                    self.telemetry_queue.put_nowait(telemetry)
                except queue.Full:
                    pass  # Skip if queue full
                
                self.last_broadcast_time = t

            # --- LOGGING ---
            if t - self.last_log > 0.5:
                runtime = self.estimate_runtime()
                tau_str = " ".join([f"{v:4.1f}" for v in torques])
                t_str = f"{int(runtime)}h {int((runtime%1)*60)}m" if runtime < 24 else ">24h"
                batt_pct = (self.current_energy / self.total_energy_capacity) * 100.0
                
                ws_status = "✓" if self.ws_connected else "✗"
                
                print(f"{t:05.1f} | [{tau_str}] | {voltage:5.1f}V | {current:5.1f}A | {power:5.1f}W | {batt_pct:4.1f}% | {t_str} | {ws_status}")
                
                self.save_battery_state()
                self.last_log = t


if __name__ == "__main__":
    # You can customize WebSocket server URL here
    # Default: ws://localhost:8765
    bridge = DITERTahap5WebSocketBridge()
    bridge.run()
