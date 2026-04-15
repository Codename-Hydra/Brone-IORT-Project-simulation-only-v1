#!/usr/bin/env python3
"""
BRone Roda — Serial Controller GUI
========================================
Kontrol robot fisik via Gamepad → Serial (ESP32).
Menampilkan GUI tkinter untuk monitoring joystick + koneksi serial.

Mapping (Tahap 6 + ESP firmware):
  Left Stick Y (Axis 1) → Forward/Backward
  Left Stick X (Axis 0) → Strafe
  LB (Button 6)         → Putar CCW
  RB (Button 7)         → Putar CW

Fitur:
  - GUI selector untuk port COM dan baud rate
  - Visualisasi analog stick real-time
  - Motor test mode via keyboard (1-4, 0=stop)
  - Auto-detect port serial

Requires: pygame, pyserial
  pip install pygame pyserial
"""

import tkinter as tk
from tkinter import ttk
import math
import sys
import os

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

try:
    import pygame
except ImportError:
    print("❌ pygame belum terinstall!")
    print("   Install: pip install pygame")
    sys.exit(1)

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("❌ pyserial belum terinstall!")
    print("   Install: pip install pyserial")
    sys.exit(1)


# --- init pygame ---
pygame.init()
pygame.joystick.init()

# --- Variabel Global ---
joystick = None
connected = False
axis_labels = []
button_labels = []

button_frame_row1 = None
button_frame_row2 = None

left_canvas = None
right_canvas = None
left_stick_dot = None
right_stick_dot = None

# --- Variabel Serial ---
ser = None
# Variabel yang akan dihubungkan ke GUI (StringVar/IntVar)
port_var = None
baud_var = None

# Daftar baud rate standar
BAUDRATES = [
    9600, 14400, 19200, 28800, 38400, 57600, 115200
]

def get_available_ports():
    """Mengambil daftar semua port COM/Serial yang tersedia."""
    ports = serial.tools.list_ports.comports()
    return [p.device for p in ports]


def connect_serial():
    """Menginisialisasi atau memutuskan koneksi serial."""
    global ser

    if ser and ser.is_open:
        # Jika sudah terhubung, lakukan Disconnect
        try:
            ser.close()
            connect_button.config(text="Connect", state=tk.NORMAL)
            status_serial.set("Serial: Disconnected")
            print("Port serial ditutup.")
        except Exception as e:
            status_serial.set(f"Serial: Error Disconnect ({e})")
    else:
        # Jika belum terhubung, lakukan Connect
        selected_port = port_var.get()
        selected_baud = baud_var.get()
        
        if not selected_port or selected_port == "Pilih Port":
            status_serial.set("Serial: Pilih Port terlebih dahulu!")
            return

        connect_button.config(state=tk.DISABLED) # Nonaktifkan tombol saat mencoba
        status_serial.set(f"Serial: Connecting to {selected_port}...")
        root.update_idletasks()

        try:
            ser = serial.Serial(selected_port, int(selected_baud), timeout=1)
            connect_button.config(text="Disconnect", state=tk.NORMAL)
            status_serial.set(f"Serial: Connected to {selected_port}@{selected_baud}")
            print(f"Berhasil terhubung ke {selected_port}")
        except serial.SerialException as e:
            connect_button.config(text="Connect", state=tk.NORMAL)
            status_serial.set(f"Serial: FAILED! ({e})")
            ser = None # Pastikan ser kembali None jika gagal
            print(f"Gagal terhubung ke {selected_port}: {e}")

def refresh_ports():
    """Memperbarui daftar port COM yang tersedia di Combobox."""
    ports = get_available_ports()
    port_combobox['values'] = ports
    
    if ports:
        # Pilih port pertama sebagai default jika ada
        port_var.set(ports[0])
        status_serial.set(f"Serial: Found {len(ports)} ports. Ready.")
    else:
        port_var.set("Pilih Port")
        status_serial.set("Serial: No ports found.")
        
# --- fungsi untuk update data joystick ---
def update_joystick():
    global connected, joystick, axis_labels, button_labels
    global left_stick_dot, right_stick_dot

    if pygame.joystick.get_count() > 0:
        if not connected:
            joystick = pygame.joystick.Joystick(0)
            joystick.init()
            connected = True
            status_var.set(f"Controller connected: {joystick.get_name()}")

            # 1. AXIS
            for lbl in axis_labels:
                lbl.destroy()
            axis_labels.clear()
            for i in range(joystick.get_numaxes()):
                lbl = tk.Label(axis_frame, text=f"Axis {i}: 0.000", width=15, anchor="w")
                lbl.pack(anchor="w")
                axis_labels.append(lbl)

            # 2. BUTTONS
            for lbl in button_labels:
                lbl.destroy()
            button_labels.clear()
            num_buttons = joystick.get_numbuttons()
            split_point = math.ceil(num_buttons / 2.0)
            for i in range(num_buttons):
                parent_frame = button_frame_row1 if i < split_point else button_frame_row2
                lbl = tk.Label(parent_frame, text=f"B{i}: 0", width=8, anchor="w")
                lbl.pack(side="left")
                button_labels.append(lbl)

            # 3. VISUALISASI
            left_canvas.delete("all")
            right_canvas.delete("all")
            left_canvas.create_oval(10, 10, 90, 90, outline='grey', width=2)
            right_canvas.create_oval(10, 10, 90, 90, outline='grey', width=2)
            left_stick_dot = left_canvas.create_oval(45, 45, 55, 55, fill='blue', outline='blue')
            right_stick_dot = right_canvas.create_oval(45, 45, 55, 55, fill='blue', outline='blue')

    else:
        if connected:
            connected = False
            joystick = None
            status_var.set("Controller disconnected")
            for lbl in axis_labels:
                lbl.destroy()
            axis_labels.clear()
            for lbl in button_labels:
                lbl.destroy()
            button_labels.clear()
            if left_canvas:
                left_canvas.delete("all")
            if right_canvas:
                right_canvas.delete("all")
            left_stick_dot = None
            right_stick_dot = None

def read_input():
    pygame.event.pump()
    
    if connected and joystick:
        try:
            # === BACA DATA JOYSTICK ===
            num_axes = joystick.get_numaxes()
            axes = [joystick.get_axis(i) for i in range(num_axes)]
            num_buttons = joystick.get_numbuttons()
            buttons = [joystick.get_button(i) for i in range(num_buttons)]
            
            # === UPDATE GUI ===
            for i, val in enumerate(axes):
                if i < len(axis_labels):
                    axis_labels[i].config(text=f"Axis {i}: {val:+.3f}")
            if num_axes >= 2 and left_stick_dot:
                x_l = 50 + (axes[0] * 40); y_l = 50 + (axes[1] * 40)
                left_canvas.coords(left_stick_dot, x_l-5, y_l-5, x_l+5, y_l+5)
            if num_axes >= 4 and right_stick_dot:
                x_r = 50 + (axes[2] * 40); y_r = 50 + (axes[3] * 40)
                right_canvas.coords(right_stick_dot, x_r-5, y_r-5, x_r+5, y_r+5)
            for i, val in enumerate(buttons):
                 if i < len(button_labels):
                    button_labels[i].config(text=f"B{i}: {val}")
            
            # --- KIRIM SERIAL ---
            # Mapping sesuai Tahap 6 + ESP firmware analysis:
            #
            # ESP firmware (ESP.ino) swaps internally:
            #   Vy = rawX - 127   (position 1 → Vy)
            #   Vx = rawY - 127   (position 2 → Vx)
            # Lalu IK: M1 = sin(45)*Vx + cos(45)*Vy - RW, dst.
            #
            # Tahap 6 approach: swap + negate untuk fix 90° rotation
            #   vx_normalized = -robot_vy    (negate Y → forward)
            #   vy_normalized =  robot_vx    (X → strafe)
            #
            # Joystick (pygame): stick up = axis1 negatif, stick right = axis0 positif

            raw_x = axes[0] if num_axes > 0 else 0.0  # Left stick X (strafe)
            raw_y = axes[1] if num_axes > 1 else 0.0  # Left stick Y (maju/mundur, inverted)

            # Deadzone
            if abs(raw_x) < 0.1: raw_x = 0.0
            if abs(raw_y) < 0.1: raw_y = 0.0

            # Mapping sesuai Tahap 6:
            # forward = -raw_y (invert pygame Y), strafe = -raw_x
            forward = -raw_y
            strafe  = -raw_x

            # Convert ke 0-255 (128 = center)
            val_x = int((strafe + 1.0) * 127.5)     # rawX → ESP Vy
            val_y = int((forward + 1.0) * 127.5)     # rawY → ESP Vx

            val_x = max(0, min(255, val_x))
            val_y = max(0, min(255, val_y))

            # Pastikan tombol ada sebelum mengakses indeks
            b6 = buttons[6] if len(buttons) > 6 else 0
            b7 = buttons[7] if len(buttons) > 7 else 0
            
            data_string = f"{val_x},{val_y},{b6},{b7}"
            final_packet = f"<{data_string}>\n"

            # print ke terminal untuk debug
            print(f"fwd={forward:+.2f} str={strafe:+.2f} → rawX={val_x} rawY={val_y} b6={b6} b7={b7}")

            if ser and ser.is_open:
                try:
                    ser.write(final_packet.encode('utf-8'))
                except serial.SerialException:
                    status_serial.set("Serial: Lost connection!")
                    connect_serial() # Coba disconnect

        except pygame.error:
            pass 

    root.after(50, read_input)


# --- GUI setup ---
root = tk.Tk()
root.title("BRone Roda — Serial Controller (Grand Simulation)")

# 1. SERIAL CONTROL FRAME (BARU)
serial_control_frame = tk.Frame(root)
serial_control_frame.pack(fill="x", padx=10, pady=5)

# Label & Combobox PORT
tk.Label(serial_control_frame, text="PORT:").pack(side="left", padx=(0, 5))
port_var = tk.StringVar(root, value="Pilih Port")
port_combobox = ttk.Combobox(serial_control_frame, textvariable=port_var, width=15, state="readonly")
port_combobox.pack(side="left", padx=(0, 15))

# Label & Combobox BAUD
tk.Label(serial_control_frame, text="BAUD:").pack(side="left", padx=(0, 5))
baud_var = tk.StringVar(root, value=str(BAUDRATES[0])) # Default 9600
baud_combobox = ttk.Combobox(serial_control_frame, textvariable=baud_var, values=BAUDRATES, width=8, state="readonly")
baud_combobox.pack(side="left", padx=(0, 15))

# Tombol Refresh Ports (BARU)
refresh_button = tk.Button(serial_control_frame, text="Refresh Ports", command=refresh_ports)
refresh_button.pack(side="left", padx=5)

# Tombol Connect/Disconnect
connect_button = tk.Button(serial_control_frame, text="Connect", command=connect_serial)
connect_button.pack(side="left", padx=5)

# Status Serial (BARU)
status_serial = tk.StringVar(root, value="Serial: Ready")
tk.Label(serial_control_frame, textvariable=status_serial, fg="blue").pack(side="left", padx=(15, 0))


# 2. STATUS JOYSTICK FRAME
status_var = tk.StringVar()
status_var.set("Waiting for controller...")
tk.Label(root, textvariable=status_var, font=("Consolas", 10)).pack(pady=5, fill="x")

# 3. MAIN CONTENT FRAME
main_content_frame = tk.Frame(root)
main_content_frame.pack(fill="both", expand=True, padx=10, pady=10)

# AXIS FRAME
axis_frame = tk.Frame(main_content_frame, borderwidth=1, relief="sunken")
axis_frame.pack(side="left", fill="y", padx=5)
tk.Label(axis_frame, text="AXES", font=("Consolas", 10, "bold")).pack(anchor="w")

# BUTTON CONTAINER FRAME
button_container_frame = tk.Frame(main_content_frame, borderwidth=1, relief="sunken")
button_container_frame.pack(side="left", fill="y", padx=5)
tk.Label(button_container_frame, text="BUTTONS", font=("Consolas", 10, "bold")).pack(anchor="w")
button_frame_row1 = tk.Frame(button_container_frame)
button_frame_row1.pack(anchor="w")
button_frame_row2 = tk.Frame(button_container_frame)
button_frame_row2.pack(anchor="w")

# VISUALIZATION FRAME
viz_frame = tk.Frame(main_content_frame, borderwidth=1, relief="sunken")
viz_frame.pack(side="left", fill="both", expand=True, padx=5)
tk.Label(viz_frame, text="ANALOG STICKS", font=("Consolas", 10, "bold")).pack()
stick_canvas_frame = tk.Frame(viz_frame)
stick_canvas_frame.pack(pady=10)

left_stick_frame = tk.Frame(stick_canvas_frame)
left_stick_frame.pack(side="left", padx=10, anchor="n") 
tk.Label(left_stick_frame, text="Left").pack() 
left_canvas = tk.Canvas(left_stick_frame, width=100, height=100, bg='white')
left_canvas.pack()

right_stick_frame = tk.Frame(stick_canvas_frame)
right_stick_frame.pack(side="left", padx=10, anchor="n") 
tk.Label(right_stick_frame, text="Right").pack() 
right_canvas = tk.Canvas(right_stick_frame, width=100, height=100, bg='white')
right_canvas.pack()


# --- MOTOR TEST MODE (keyboard) ---
test_mode_active = {'value': False}
test_packet = {'data': None}

def on_key_press(event):
    """
    Keyboard test mode untuk identifikasi motor:
    Berdasarkan ESP IK: M1=sin45*Vx+cos45*Vy-RW, dst.
    
    Vx=Vy  → M1 maju, M3 mundur, M2&M4 DIAM
    Vx=-Vy → M2 maju, M4 mundur, M1&M3 DIAM
    """
    global ser
    key = event.char
    
    packet = None
    info = ""
    
    if key == '1':
        # Vx=100, Vy=100 → M1 maju, M3 mundur (M2,M4 diam)
        # ESP: rawX→Vy=100 → rawX=227, rawY→Vx=100 → rawY=227
        packet = "<227,227,0,0>\n"
        info = "TEST 1: Motor1 MAJU ↑ + Motor3 MUNDUR ↓ (Motor2,4 diam)"
    elif key == '2':
        # Vx=100, Vy=-100 → M2 maju, M4 mundur (M1,M3 diam)
        # ESP: rawX→Vy=-100 → rawX=27, rawY→Vx=100 → rawY=227
        packet = "<27,227,0,0>\n"
        info = "TEST 2: Motor2 MAJU ↑ + Motor4 MUNDUR ↓ (Motor1,3 diam)"
    elif key == '3':
        # Test rotation CW
        packet = "<127,127,0,1>\n"
        info = "TEST 3: ROTASI CW (b7=1)"
    elif key == '4':
        # Test rotation CCW
        packet = "<127,127,1,0>\n"
        info = "TEST 4: ROTASI CCW (b6=1)"
    elif key == '0':
        packet = "<127,127,0,0>\n"
        info = "STOP: Semua motor berhenti"
    
    if packet and info:
        print(f"\n>>> {info}")
        print(f"    Packet: {packet.strip()}")
        test_mode_active['value'] = (key != '0')
        test_packet['data'] = packet if key != '0' else None
        
        if ser and ser.is_open:
            try:
                ser.write(packet.encode('utf-8'))
            except serial.SerialException:
                print("    Serial error!")

root.bind('<Key>', on_key_press)

# Tambah label instruksi
test_label = tk.Label(root, 
    text="MOTOR TEST: Tekan 1=M1↑M3↓  2=M2↑M4↓  3=CW  4=CCW  0=STOP",
    font=("Consolas", 9), fg="red", bg="lightyellow")
test_label.pack(fill="x", padx=10, pady=2)

# --- loop untuk cek koneksi tiap 2 detik ---
def check_connection():
    update_joystick()
    root.after(2000, check_connection)


def main():
    """Entry point untuk ROS2 console_scripts dan standalone."""
    # Pindai port saat aplikasi dimulai
    refresh_ports()
    check_connection()
    read_input()

    root.mainloop()

    # --- Cleanup ---
    print("Menutup aplikasi...")
    if ser and ser.is_open:
        ser.close()
        print("Port serial ditutup.")
    pygame.quit()


if __name__ == '__main__':
    main()
