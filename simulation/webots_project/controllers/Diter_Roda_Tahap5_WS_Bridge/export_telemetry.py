#!/usr/bin/env python3
"""
TELEMETRY DATA EXPORT TOOL
===========================
Utility to export robot telemetry data from SQLite database to CSV format.

Usage:
    python3 export_telemetry.py --session 1 --output session_1.csv
    python3 export_telemetry.py --all --output all_sessions.csv
    python3 export_telemetry.py --list
"""

import argparse
from database_logger import TelemetryDatabase


def list_sessions(db_path):
    """List all available sessions"""
    db = TelemetryDatabase(db_path)
    sessions = db.list_sessions()
    
    print("\n" + "="*80)
    print(" AVAILABLE SESSIONS ")
    print("="*80)
    print(f"{'ID':<6} {'Start Time':<22} {'End Time':<22} {'Duration (s)':<15}")
    print("-"*80)
    
    for session in sessions:
        session_id = session['session_id']
        start = session['start_time'] or "N/A"
        end = session['end_time'] or "Running"
        duration = f"{session['duration']:.1f}" if session['duration'] else "N/A"
        
        print(f"{session_id:<6} {start:<22} {end:<22} {duration:<15}")
    
    print("="*80)
    print(f"Total sessions: {len(sessions)}")
    print()
    
    db.close()


def export_session(db_path, session_id, output_path):
    """Export specific session to CSV"""
    db = TelemetryDatabase(db_path)
    
    # Get session stats
    stats = db.get_session_stats(session_id)
    
    if not stats:
        print(f"!! ERROR: Session {session_id} not found")
        db.close()
        return
    
    print(f"\n>> Exporting Session {session_id}:")
    print(f"   Start: {stats['start_time']}")
    print(f"   End: {stats['end_time']}")
    print(f"   Duration: {stats['duration_seconds']:.1f}s")
    print(f"   Log entries: {stats['log_count']}")
    
    # Export to CSV
    db.export_session_to_csv(session_id, output_path)
    print(f"\n✓ Export complete: {output_path}")
    
    db.close()


def export_all_sessions(db_path, output_path):
    """Export all sessions to a single CSV"""
    db = TelemetryDatabase(db_path)
    
    # Get all sessions
    sessions = db.list_sessions()
    
    if not sessions:
        print("!! No sessions found in database")
        db.close()
        return
    
    print(f"\n>> Exporting {len(sessions)} sessions to {output_path}...")
    
    # Query all telemetry data
    db.cursor.execute("""
        SELECT * FROM telemetry_logs
        ORDER BY session_id, timestamp
    """)
    
    rows = db.cursor.fetchall()
    columns = [desc[0] for desc in db.cursor.description]
    
    # Write to CSV
    import csv
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        writer.writerows(rows)
    
    print(f"✓ Exported {len(rows)} total log entries")
    print(f"✓ Export complete: {output_path}")
    
    db.close()


def show_session_summary(db_path, session_id):
    """Show detailed summary of a session"""
    db = TelemetryDatabase(db_path)
    
    stats = db.get_session_stats(session_id)
    
    if not stats:
        print(f"!! ERROR: Session {session_id} not found")
        db.close()
        return
    
    # Get min/max/avg stats from telemetry
    db.cursor.execute("""
        SELECT 
            MIN(voltage), MAX(voltage), AVG(voltage),
            MIN(current), MAX(current), AVG(current),
            MIN(power), MAX(power), AVG(power),
            MIN(soc), MAX(soc), AVG(soc)
        FROM telemetry_logs
        WHERE session_id = ?
    """, (session_id,))
    
    result = db.cursor.fetchone()
    
    print("\n" + "="*80)
    print(f" SESSION {session_id} SUMMARY ")
    print("="*80)
    print(f"Start Time:      {stats['start_time']}")
    print(f"End Time:        {stats['end_time']}")
    print(f"Duration:        {stats['duration_seconds']:.1f} seconds")
    print(f"Initial Energy:  {stats['initial_energy']:,.0f} J")
    print(f"Final Energy:    {stats['final_energy']:,.0f} J" if stats['final_energy'] else "N/A")
    print(f"Energy Consumed: {(stats['initial_energy'] - (stats['final_energy'] or 0)):,.0f} J")
    print(f"Log Entries:     {stats['log_count']}")
    print()
    
    if result:
        print("Electrical Statistics:")
        print(f"  Voltage:  {result[0]:.2f}V (min)  {result[1]:.2f}V (max)  {result[2]:.2f}V (avg)")
        print(f"  Current:  {result[3]:.2f}A (min)  {result[4]:.2f}A (max)  {result[5]:.2f}A (avg)")
        print(f"  Power:    {result[6]:.0f}W (min)  {result[7]:.0f}W (max)  {result[8]:.0f}W (avg)")
        print(f"  SoC:      {result[9]:.1f}% (min) {result[10]:.1f}% (max) {result[11]:.1f}% (avg)")
    
    print("="*80)
    print()
    
    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Export robot telemetry data from SQLite database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --list
  %(prog)s --session 1 --output session_1.csv
  %(prog)s --all --output all_data.csv
  %(prog)s --summary 1
        """
    )
    
    parser.add_argument('--db', default='robot_telemetry.db',
                        help='Path to SQLite database (default: robot_telemetry.db)')
    parser.add_argument('--list', action='store_true',
                        help='List all available sessions')
    parser.add_argument('--session', type=int,
                        help='Export specific session ID')
    parser.add_argument('--all', action='store_true',
                        help='Export all sessions to single CSV')
    parser.add_argument('--summary', type=int, metavar='ID',
                        help='Show detailed summary of a session')
    parser.add_argument('--output', '-o',
                        help='Output CSV file path')
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.list:
        list_sessions(args.db)
    elif args.summary:
        show_session_summary(args.db, args.summary)
    elif args.session:
        if not args.output:
            print("!! ERROR: --output required when using --session")
            return
        export_session(args.db, args.session, args.output)
    elif args.all:
        if not args.output:
            print("!! ERROR: --output required when using --all")
            return
        export_all_sessions(args.db, args.output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
