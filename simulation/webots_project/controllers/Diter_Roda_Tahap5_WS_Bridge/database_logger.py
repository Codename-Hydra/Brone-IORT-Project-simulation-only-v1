"""
TELEMETRY DATABASE LOGGER
=========================
SQLite database manager for persistent robot telemetry logging.

Features:
- Session management (each run = new session)
- Automatic telemetry logging
- Export to CSV
- Offline-capable (no server required)

Database: robot_telemetry.db (auto-created)
"""

import sqlite3
import csv
from datetime import datetime
from typing import Optional, Dict, Any, List


class TelemetryDatabase:
    """Manages SQLite database for robot telemetry logging"""
    
    def __init__(self, db_path: str = "robot_telemetry.db"):
        """
        Initialize database connection and create tables if needed.
        
        Args:
            db_path: Path to SQLite database file (created if not exists)
        """
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()
        print(f">> DATABASE: Initialized at {db_path}")
    
    def create_tables(self):
        """Create database tables if they don't exist"""
        
        # Sessions table - tracks each simulation run
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                initial_battery_energy REAL,
                final_battery_energy REAL,
                duration_seconds REAL,
                notes TEXT
            )
        """)
        
        # Telemetry logs table - detailed data points
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS telemetry_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp REAL,
                voltage REAL,
                current REAL,
                power REAL,
                cell_voltage REAL,
                soc REAL,
                runtime_hours REAL,
                energy_remaining REAL,
                torque_fl REAL,
                torque_fr REAL,
                torque_rl REAL,
                torque_rr REAL,
                rpm_fl INTEGER,
                rpm_fr INTEGER,
                rpm_rl INTEGER,
                rpm_rr INTEGER,
                motion_vx REAL,
                motion_vy REAL,
                motion_w REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            )
        """)
        
        self.conn.commit()
    
    def start_session(self, initial_energy: float, notes: str = "") -> int:
        """
        Start a new telemetry logging session.
        
        Args:
            initial_energy: Starting battery energy in Joules
            notes: Optional session notes
            
        Returns:
            session_id: ID of newly created session
        """
        self.cursor.execute("""
            INSERT INTO sessions (initial_battery_energy, notes)
            VALUES (?, ?)
        """, (initial_energy, notes))
        
        self.conn.commit()
        session_id = self.cursor.lastrowid
        
        print(f">> DATABASE: Session {session_id} started")
        return session_id
    
    def end_session(self, session_id: int, final_energy: float):
        """
        End a telemetry logging session.
        
        Args:
            session_id: ID of session to end
            final_energy: Final battery energy in Joules
        """
        # Get session start time to calculate duration
        self.cursor.execute("""
            SELECT start_time FROM sessions WHERE session_id = ?
        """, (session_id,))
        
        result = self.cursor.fetchone()
        if not result:
            print(f"!! DATABASE: Session {session_id} not found")
            return
        
        # Calculate duration
        start_time = datetime.fromisoformat(result[0])
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Update session
        self.cursor.execute("""
            UPDATE sessions 
            SET end_time = CURRENT_TIMESTAMP,
                final_battery_energy = ?,
                duration_seconds = ?
            WHERE session_id = ?
        """, (final_energy, duration, session_id))
        
        self.conn.commit()
        print(f">> DATABASE: Session {session_id} ended (duration: {duration:.1f}s)")
    
    def log_telemetry(self, session_id: int, sim_time: float, telemetry: Dict[str, Any],
                      energy_remaining: float, motion: tuple = (0, 0, 0)):
        """
        Log telemetry data point.
        
        Args:
            session_id: Active session ID
            sim_time: Simulation time in seconds
            telemetry: Telemetry dict with keys: voltage, current, power, soc, runtime, torques, rpm
            energy_remaining: Current battery energy (J)
            motion: Tuple of (vx, vy, w) velocities
        """
        vx, vy, w = motion
        
        self.cursor.execute("""
            INSERT INTO telemetry_logs (
                session_id, timestamp,
                voltage, current, power, cell_voltage,
                soc, runtime_hours, energy_remaining,
                torque_fl, torque_fr, torque_rl, torque_rr,
                rpm_fl, rpm_fr, rpm_rl, rpm_rr,
                motion_vx, motion_vy, motion_w
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, sim_time,
            telemetry.get("voltage", 0),
            telemetry.get("current", 0),
            telemetry.get("power", 0),
            telemetry.get("voltage", 0) / 6.0,  # 6S battery
            telemetry.get("soc", 0),
            telemetry.get("runtime", 0),
            energy_remaining,
            telemetry.get("torques", [0,0,0,0])[0],
            telemetry.get("torques", [0,0,0,0])[1],
            telemetry.get("torques", [0,0,0,0])[2],
            telemetry.get("torques", [0,0,0,0])[3],
            telemetry.get("rpm", [0,0,0,0])[0],
            telemetry.get("rpm", [0,0,0,0])[1],
            telemetry.get("rpm", [0,0,0,0])[2],
            telemetry.get("rpm", [0,0,0,0])[3],
            vx, vy, w
        ))
        
        self.conn.commit()
    
    def get_session_stats(self, session_id: int) -> Optional[Dict]:
        """
        Get statistics for a session.
        
        Args:
            session_id: Session ID to query
            
        Returns:
            Dict with session statistics or None if not found
        """
        self.cursor.execute("""
            SELECT 
                session_id,
                start_time,
                end_time,
                initial_battery_energy,
                final_battery_energy,
                duration_seconds,
                notes
            FROM sessions
            WHERE session_id = ?
        """, (session_id,))
        
        result = self.cursor.fetchone()
        if not result:
            return None
        
        # Get telemetry count
        self.cursor.execute("""
            SELECT COUNT(*) FROM telemetry_logs WHERE session_id = ?
        """, (session_id,))
        log_count = self.cursor.fetchone()[0]
        
        return {
            "session_id": result[0],
            "start_time": result[1],
            "end_time": result[2],
            "initial_energy": result[3],
            "final_energy": result[4],
            "duration_seconds": result[5],
            "notes": result[6],
            "log_count": log_count
        }
    
    def export_session_to_csv(self, session_id: int, output_path: str):
        """
        Export session telemetry to CSV file.
        
        Args:
            session_id: Session ID to export
            output_path: Output CSV file path
        """
        self.cursor.execute("""
            SELECT * FROM telemetry_logs 
            WHERE session_id = ?
            ORDER BY timestamp
        """, (session_id,))
        
        rows = self.cursor.fetchall()
        if not rows:
            print(f"!! DATABASE: No data found for session {session_id}")
            return
        
        # Get column names
        columns = [desc[0] for desc in self.cursor.description]
        
        # Write to CSV
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
        
        print(f">> DATABASE: Exported {len(rows)} rows to {output_path}")
    
    def list_sessions(self) -> List[Dict]:
        """
        List all sessions.
        
        Returns:
            List of session dicts
        """
        self.cursor.execute("""
            SELECT session_id, start_time, end_time, duration_seconds
            FROM sessions
            ORDER BY session_id DESC
        """)
        
        sessions = []
        for row in self.cursor.fetchall():
            sessions.append({
                "session_id": row[0],
                "start_time": row[1],
                "end_time": row[2],
                "duration": row[3]
            })
        
        return sessions
    
    def close(self):
        """Close database connection"""
        self.conn.commit()
        self.conn.close()
        print(">> DATABASE: Connection closed")


if __name__ == "__main__":
    # Test database creation
    db = TelemetryDatabase("test_telemetry.db")
    
    # Test session
    session_id = db.start_session(100000.0, "Test session")
    
    # Test logging
    test_telemetry = {
        "voltage": 24.5,
        "current": 12.3,
        "power": 301.35,
        "soc": 95.0,
        "runtime": 1.2,
        "torques": [0.1, 0.15, 0.12, 0.14],
        "rpm": [100, 105, 98, 102]
    }
    
    db.log_telemetry(session_id, 1.0, test_telemetry, 95000.0, (0.5, 0.3, 0.1))
    
    # Test stats
    stats = db.get_session_stats(session_id)
    print(f"\nSession Stats: {stats}")
    
    # End session
    db.end_session(session_id, 94500.0)
    
    # Test export
    db.export_session_to_csv(session_id, "test_export.csv")
    
    db.close()
    print("\n✓ Database test completed successfully")
