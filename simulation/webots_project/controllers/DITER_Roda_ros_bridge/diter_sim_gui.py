"""
BRONE DITER TAHAP 3 — SIMULATION GUI
=====================================
Gabungan DITER_roda_tahap3 (physics + Webots) + Controller GUI (tkinter).

Berjalan sebagai Webots EXTERN controller (port 1235).
Menampilkan window GUI tkinter dengan:
  - Status baterai DITER (V, A, W, %)
  - Visualisasi analog stick
  - Tombol reset baterai

Jalankan via run_gui.sh (WEBOTS_HOME dan WEBOTS_CONTROLLER_URL harus di-set).
"""

import os
import sys
import math
import time
import threading

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = 'hide'

import tkinter as tk
from tkinter import ttk

import json
try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
except ImportError:
    sys.exit("CRITICAL: rclpy tidak ditemukan. Pastikan ROS 2 sourced.")

try:
    import pygame
except ImportError:
    sys.exit("CRITICAL: pygame tidak terinstall. Jalankan: pip install pygame")

try:
    from controller import Robot
except ImportError as e:
    sys.exit(f"CRITICAL: Webots controller tidak ditemukan. {e}\n"
             "Pastikan WEBOTS_HOME sudah di-set dan run via run_gui.sh")


# ============================================================
# DITER Physics Engine (dari Tahap 3)
# ============================================================
class DiterEngine:
    def __init__(self):
        # Baterai: 2x LiPo 3S 5200mAh seri = 6S 22.2V
        self.BATT_NOMINAL_VOLTAGE = 22.2
        self.BATT_CAPACITY_MAH    = 5200.0
        self.CUTOFF_VOLTAGE       = 19.8   # UVLO: 3.3V/cell x 6
        self.R_INTERNAL           = 0.15   # Ohm
        self.total_energy_J       = 21.0 * (self.BATT_CAPACITY_MAH / 1000.0) * 3600.0
        self.current_energy_J     = self.total_energy_J

        # Motor specs (PG36 24V)
        self.P_STATIC   = 8.0    # Watt (Orange Pi + ESP32)
        self.I_IDLE     = 0.25
        self.I_STALL    = 2.5
        self.TORQUE_STALL = 1.96
        self.K_T        = self.TORQUE_STALL / self.I_STALL
        self.MAX_SPEED  = 46.0

        # Kinematics — sesuai ESP.ino (R = jarak pusat ke roda)
        self.R_body  = 0.208   # meter (7.6cm di ESP, diskalakan ke Webots)
        self.r_wheel = 0.06
        self.S45     = math.sin(math.pi / 4)  # 0.7071
        self.C45     = math.cos(math.pi / 4)  # 0.7071

        # Rolling average power window (5 detik)
        self._power_window = []

        # Hasil metrik (thread-safe via lock)
        self.lock   = threading.Lock()
        self.voltage   = self.BATT_NOMINAL_VOLTAGE
        self.current_A = 0.0
        self.power_W   = 0.0
        self.soc_pct   = 100.0
        self.runtime_h = 99.0
        self.status    = "IDLE"
        self.uvlo      = False

    def soc(self):
        return max(0.0, self.current_energy_J / self.total_energy_J)

    def reset_full(self):
        with self.lock:
            self.current_energy_J = self.total_energy_J
            self._power_window.clear()

    def ik(self, vx, vy, w):
        """
        Inverse kinematics — Hybrid ESP.ino + Webots
        
        Translation terms: EXACT MATCH ESP.ino (mecanum X-config)
          M1 =  0.707*Vx + 0.707*Vy
          M2 =  0.707*Vx - 0.707*Vy
          M3 = -0.707*Vx - 0.707*Vy
          M4 = -0.707*Vx + 0.707*Vy
        
        Rotation term: SAMA untuk semua roda (Webots convention)
          Di ESP fisik, M2/M4 terpasang terbalik → firmware pakai +R*W.
          Di Webots, sumbu joint sudah konsisten → semua roda pakai -R*W.
          (Sesuai Tahap 3 controller yang sudah terbukti jalan di Webots)
        """
        s = self.S45
        c = self.C45
        R = self.R_body
        r = self.r_wheel

        m1 = ( s * vx + c * vy - R * w) / r
        m2 = ( s * vx - c * vy - R * w) / r  # Webots: -R*w (bukan +R*w)
        m3 = (-s * vx - c * vy - R * w) / r
        m4 = (-s * vx + c * vy - R * w) / r  # Webots: -R*w (bukan +R*w)
        return [m1, m2, m3, m4]

    def step_metrics(self, wheels, dt):
        """Hitung DITER physics untuk satu timestep."""
        s = self.soc()
        v_oc = 18.0 + (7.2 * s)

        i_motor = 0.0
        for m in wheels:
            tau = abs(m.getTorqueFeedback())
            i_motor += (tau / self.K_T) + self.I_IDLE

        i_static = self.P_STATIC / max(v_oc, 0.1)
        i_total  = i_motor + i_static
        v_term   = v_oc - (i_total * self.R_INTERNAL)
        if v_term < 0: v_term = 0.0

        i_static2 = self.P_STATIC / max(v_term, 0.1)
        i_total2  = i_motor + i_static2
        power     = v_term * i_total2
        self.current_energy_J -= power * dt

        self._power_window.append(power)
        max_win = max(1, int(5.0 / dt))
        if len(self._power_window) > max_win:
            self._power_window.pop(0)
        avg_p = sum(self._power_window) / len(self._power_window)

        soc_val   = max(0.0, self.current_energy_J / self.total_energy_J) * 100.0
        runtime_h = (self.current_energy_J / 3600.0 / avg_p) if avg_p > 1.0 else 99.0

        is_uvlo = v_term <= self.CUTOFF_VOLTAGE
        is_moving = i_motor > (self.I_IDLE * 4 + 0.05)

        with self.lock:
            self.voltage   = v_term
            self.current_A = i_total2
            self.power_W   = power
            self.soc_pct   = soc_val
            self.runtime_h = runtime_h
            self.uvlo      = is_uvlo
            self.status    = "UVLO!" if is_uvlo else ("RUN" if is_moving else "IDLE")


# ============================================================
# Webots thread
# ============================================================
class WebotsThread(threading.Thread):
    def __init__(self, diter: DiterEngine, gui):
        super().__init__(daemon=True)
        self.diter = diter
        self.gui   = gui
        self.robot = None
        self.wheels = []
        self.timestep = 32
        self.js = None
        self.connected_to_webots = False

        # Init ROS 2 Node
        if not rclpy.ok(): rclpy.init()
        self.ros_node = Node('diter_sim_gui_publisher')
        self.pub = self.ros_node.create_publisher(String, '/brone/power/summary', 10)

    def _connect(self):
        print(">> Menunggu Webots (port 1235)...", end='', flush=True)
        while True:
            try:
                self.robot = Robot()
                self.timestep = int(self.robot.getBasicTimeStep())
                # Setup wheels
                for name in ['wheel1', 'wheel2', 'wheel3', 'wheel4']:
                    m = self.robot.getDevice(name)
                    m.setPosition(float('inf'))
                    m.setVelocity(0.0)
                    m.enableTorqueFeedback(self.timestep)
                    self.wheels.append(m)
                print("\n>> SUKSES: Terhubung ke Webots!")
                self.connected_to_webots = True
                self.gui.set_webots_status(True)
                return
            except Exception:
                print('.', end='', flush=True)
                time.sleep(1)

    def _get_joystick(self):
        """
        Mapping sesuai ESP.ino:
          - Serial: rawX→Vy, rawY→Vx (swap di ESP)
          - pygame: axis0=X(strafe), axis1=Y(forward, inverted)
          - ESP: b6=CCW(W=-5), b7=CW(W=+5)
        
        Konvensi output (Vx, Vy, W):
          Vx positif = maju (forward)
          Vy positif = strafe kanan
          W  positif = CW
        """
        pygame.event.pump()
        vx, vy, w = 0.0, 0.0, 0.0

        js = self.js
        if js:
            raw_x = js.get_axis(0)  # Left stick horizontal
            raw_y = js.get_axis(1)  # Left stick vertical (up = negatif)
            rot = 0.0
            try:
                if js.get_button(4) or js.get_button(6): rot = -1.0  # L1 = CCW
                if js.get_button(5) or js.get_button(7): rot =  1.0  # R1 = CW
            except Exception:
                pass

            # Deadzone
            if abs(raw_x) < 0.1: raw_x = 0.0
            if abs(raw_y) < 0.1: raw_y = 0.0

            # Sesuai ESP: Vx = forward (invert pygame Y), Vy = strafe (raw_x)
            vx = -raw_y   # stick up (negatif) → Vx positif (maju)
            vy =  raw_x   # stick kanan (positif) → Vy positif

            # Rotasi: scale ke kecepatan sudut
            w = rot * 2.0  # CW positif, CCW negatif

        # Keyboard override (same convention)
        kvx, kvy, kw = self.gui.get_keyboard_input()
        if kvx != 0: vx = kvx
        if kvy != 0: vy = kvy
        if kw  != 0: w  = kw * 2.0

        return vx, vy, w

    def run(self):
        pygame.init()
        pygame.joystick.init()

        self._connect()

        last_js_check = 0.0

        while self.robot.step(self.timestep) != -1:
            dt = self.timestep / 1000.0
            t  = time.time()

            # Update joystick setiap 0.5 detik
            if t - last_js_check > 0.5:
                cnt = pygame.joystick.get_count()
                if cnt > 0 and self.js is None:
                    self.js = pygame.joystick.Joystick(0)
                    self.js.init()
                    self.gui.set_joystick_name(self.js.get_name())
                elif cnt == 0 and self.js is not None:
                    self.js = None
                    self.gui.set_joystick_name(None)
                last_js_check = t

            vx, vy, w = self._get_joystick()
            # Update GUI stick visual
            self.gui.update_stick(vy, -vx)  # canvas: X=strafe(vy), Y=forward(vx inverted)

            # Webots frame adaptation
            vels = self.diter.ik(-vy, vx, -w)
            for i, wheel in enumerate(self.wheels):
                wheel.setVelocity(max(min(vels[i], self.diter.MAX_SPEED), -self.diter.MAX_SPEED))

            self.diter.step_metrics(self.wheels, dt)

            if self.diter.uvlo:
                for wheel in self.wheels:
                    wheel.setVelocity(0.0)

            # --- PUBLISH KE WEB DASHBOARD (ROS 2) ---
            if hasattr(self, 'ros_node') and (t - getattr(self, 'last_pub_time', 0) > 0.2):
                self.last_pub_time = t
                packet = {
                    'type': 'brone_roda',
                    'battery': {
                        'voltage_V': round(self.diter.voltage, 2),
                        'current_A': round(self.diter.current_A, 2),
                        'power_W': round(self.diter.power_W, 2),
                        'soc_pct': round(self.diter.soc_pct, 1),
                        'status': self.diter.status,
                        'runtime_hours': round(self.diter.runtime_h, 2),
                        'cell_voltage_V': round(self.diter.voltage / 6.0, 3)
                    },
                    'wheels': {},
                    'motion': {
                        'vx': round(vx, 3),
                        'vy': round(vy, 3),
                        'omega': round(w, 3)
                    },
                    'system': {
                        'ping_ms': 1.0,
                        'connection_quality': 'SAFE (SIM)',
                        'robot_ip': '127.0.0.1 (SIMULATOR)'
                    },
                    'totals': {
                        'total_power_W': round(self.diter.power_W, 2),
                        'total_current_A': round(self.diter.current_A, 2),
                        'avg_rpm': 0.0
                    }
                }
                
                rpm_sum = 0.0
                wnames = ['wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR']
                for i, wname in enumerate(wnames):
                    if i < len(self.wheels):
                        m = self.wheels[i]
                        tau = abs(m.getTorqueFeedback())
                        rads = m.getVelocity()
                        rpm = rads * 60.0 / (2 * math.pi)
                        rpm_sum += abs(rpm)
                        i_l = tau / self.diter.K_T + self.diter.I_IDLE
                        pw = self.diter.voltage * i_l
                        packet['wheels'][wname] = {
                            'name': wname,
                            'torque_Nm': round(tau, 4),
                            'velocity_rad_s': round(rads, 3),
                            'rpm': round(rpm, 1),
                            'current_A': round(i_l, 4),
                            'power_W': round(pw, 3)
                        }
                if self.wheels:
                    packet['totals']['avg_rpm'] = round(rpm_sum / len(self.wheels), 1)

                msg = String()
                msg.data = json.dumps(packet)
                self.pub.publish(msg)
                rclpy.spin_once(self.ros_node, timeout_sec=0)

        print(">> Webots selesai / reset.")
        self.gui.set_webots_status(False)
        try:
            self.ros_node.destroy_node()
            rclpy.shutdown()
        except: pass


# ============================================================
# GUI
# ============================================================
class ControllerGUI:
    def __init__(self, diter: DiterEngine):
        self.diter = diter

        self.root = tk.Tk()
        self.root.title("BRone Roda — DITER Simulation Controller")
        self.root.configure(bg='#1a1a2e')
        self.root.resizable(False, False)

        # Fonts
        FN = ("Consolas", 10)
        FN_BIG = ("Consolas", 22, "bold")
        FN_MED = ("Consolas", 12, "bold")

        # Colors
        BG   = '#1a1a2e'
        CARD = '#16213e'
        ACC  = '#0f3460'
        GREEN = '#00ff88'
        YELLOW = '#ffd700'
        RED  = '#ff4444'
        CYAN = '#58a6ff'
        self.GREEN = GREEN; self.YELLOW = YELLOW; self.RED = RED

        def card(parent, **kw):
            f = tk.Frame(parent, bg=CARD, bd=0, highlightbackground=ACC,
                         highlightthickness=1, **kw)
            return f

        # ---- Header ----
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill='x', padx=12, pady=(10, 4))
        tk.Label(hdr, text="🛞  BRONE RODA — DITER SIMULATION",
                 font=("Consolas", 13, "bold"), fg=CYAN, bg=BG).pack(side='left')

        self._webots_dot = tk.Label(hdr, text="●", font=("Consolas", 14),
                                    fg=RED, bg=BG)
        self._webots_dot.pack(side='right')
        self._webots_lbl = tk.Label(hdr, text="Webots: disconnected",
                                    font=FN, fg=RED, bg=BG)
        self._webots_lbl.pack(side='right', padx=(0, 4))

        # ---- Battery Row ----
        batt_row = tk.Frame(self.root, bg=BG)
        batt_row.pack(fill='x', padx=12, pady=4)

        # Voltage card
        vc = card(batt_row, padx=14, pady=8)
        vc.pack(side='left', fill='both', expand=True, padx=(0, 4))
        tk.Label(vc, text="VOLTAGE", font=FN, fg=CYAN, bg=CARD).pack()
        self._volt_var = tk.StringVar(value="--.-  V")
        tk.Label(vc, textvariable=self._volt_var, font=FN_BIG, fg=GREEN, bg=CARD).pack()

        # Current card
        cc = card(batt_row, padx=14, pady=8)
        cc.pack(side='left', fill='both', expand=True, padx=4)
        tk.Label(cc, text="CURRENT", font=FN, fg=CYAN, bg=CARD).pack()
        self._curr_var = tk.StringVar(value="--.-  A")
        tk.Label(cc, textvariable=self._curr_var, font=FN_BIG, fg=GREEN, bg=CARD).pack()

        # Power card
        pc = card(batt_row, padx=14, pady=8)
        pc.pack(side='left', fill='both', expand=True, padx=4)
        tk.Label(pc, text="POWER", font=FN, fg=CYAN, bg=CARD).pack()
        self._pow_var = tk.StringVar(value="---.-  W")
        tk.Label(pc, textvariable=self._pow_var, font=FN_BIG, fg=GREEN, bg=CARD).pack()

        # SOC card
        sc = card(batt_row, padx=14, pady=8)
        sc.pack(side='left', fill='both', expand=True, padx=(4, 0))
        tk.Label(sc, text="BATTERY", font=FN, fg=CYAN, bg=CARD).pack()
        self._soc_var = tk.StringVar(value="--.-  %")
        self._soc_lbl = tk.Label(sc, textvariable=self._soc_var, font=FN_BIG,
                                  fg=GREEN, bg=CARD)
        self._soc_lbl.pack()

        # ---- Progress bar ----
        prog_frame = tk.Frame(self.root, bg=BG)
        prog_frame.pack(fill='x', padx=12, pady=2)
        self._soc_bar = ttk.Progressbar(prog_frame, length=450, mode='determinate',
                                        maximum=100, value=100)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("green.Horizontal.TProgressbar",
                        troughcolor='#333', background=GREEN, thickness=18)
        self._soc_bar.configure(style="green.Horizontal.TProgressbar")
        self._soc_bar.pack(fill='x')

        # ---- Status bar ----
        stat_row = tk.Frame(self.root, bg=BG)
        stat_row.pack(fill='x', padx=12, pady=4)

        self._status_var = tk.StringVar(value="Status: —")
        self._status_lbl = tk.Label(stat_row, textvariable=self._status_var,
                                    font=FN_MED, fg=YELLOW, bg=BG)
        self._status_lbl.pack(side='left')

        self._runtime_var = tk.StringVar(value="Runtime: --h --m")
        tk.Label(stat_row, textvariable=self._runtime_var, font=FN,
                 fg=CYAN, bg=BG).pack(side='right')

        # ---- Joystick section ----
        js_row = tk.Frame(self.root, bg=BG)
        js_row.pack(fill='x', padx=12, pady=4)

        js_card = card(js_row, padx=10, pady=8)
        js_card.pack(side='left')
        tk.Label(js_card, text="JOYSTICK", font=FN, fg=CYAN, bg=CARD).pack()
        self._js_name_var = tk.StringVar(value="— not connected —")
        tk.Label(js_card, textvariable=self._js_name_var,
                 font=FN, fg=YELLOW, bg=CARD).pack()

        # Stick canvas
        stick_card = card(js_row, padx=10, pady=8)
        stick_card.pack(side='left', padx=(8, 0))
        tk.Label(stick_card, text="LEFT STICK", font=FN, fg=CYAN, bg=CARD).pack()
        self._canvas = tk.Canvas(stick_card, width=100, height=100,
                                 bg='#0d0d1f', highlightthickness=0)
        self._canvas.pack()
        self._canvas.create_oval(5, 5, 95, 95, outline='#444', width=2)
        self._canvas.create_line(50, 5, 50, 95, fill='#333')
        self._canvas.create_line(5, 50, 95, 50, fill='#333')
        self._dot = self._canvas.create_oval(45, 45, 55, 55, fill=GREEN, outline=GREEN)

        # ---- Buttons ----
        btn_row = tk.Frame(self.root, bg=BG)
        btn_row.pack(fill='x', padx=12, pady=8)
        tk.Button(btn_row, text="🔋 Reset Baterai (Full)", font=FN,
                  bg='#0f3460', fg=GREEN, activebackground='#1a5276',
                  relief='flat', padx=10, pady=6,
                  command=self._reset_battery).pack(side='left', padx=(0, 8))

        # ---- Keyboard setup ----
        self.keys = {'w': False, 'a': False, 's': False, 'd': False, 'q': False, 'e': False,
                     'Up': False, 'Down': False, 'Left': False, 'Right': False}
        self.root.bind('<KeyPress>', self._on_key_press)
        self.root.bind('<KeyRelease>', self._on_key_release)
        
        # Add instruction label
        tk.Label(btn_row, text="Keyboard: WASD / Arrows = Move, Q/E = Rotate", 
                 font=("Consolas", 9), fg=YELLOW, bg=BG).pack(side='right')

        # ---- Interval update ----
        self._poll()

    def _on_key_press(self, event):
        key = event.keysym
        if key in self.keys: self.keys[key] = True
        elif key.lower() in self.keys: self.keys[key.lower()] = True

    def _on_key_release(self, event):
        key = event.keysym
        if key in self.keys: self.keys[key] = False
        elif key.lower() in self.keys: self.keys[key.lower()] = False

    def get_keyboard_input(self):
        """
        Konvensi sesuai ESP.ino:
          Vx positif = maju, Vy positif = strafe kanan, W positif = CW
        """
        vx, vy, rot = 0.0, 0.0, 0.0
        # W/Up = forward (Vx+), S/Down = backward (Vx-)
        if self.keys['w'] or self.keys['Up']:    vx =  1.0
        elif self.keys['s'] or self.keys['Down']: vx = -1.0
        
        # D/Right = strafe kanan (Vy+), A/Left = strafe kiri (Vy-)
        if self.keys['d'] or self.keys['Right']:   vy =  1.0
        elif self.keys['a'] or self.keys['Left']:  vy = -1.0
        
        # Q = CCW (W-), E = CW (W+)
        if self.keys['q']:   rot = -1.0
        elif self.keys['e']: rot =  1.0
        return vx, vy, rot

    # ---- Thread-safe update helpers ----
    def set_webots_status(self, connected: bool):
        color = '#00ff88' if connected else '#ff4444'
        text  = "Webots: connected" if connected else "Webots: disconnected"
        self.root.after(0, lambda: self._webots_dot.config(fg=color))
        self.root.after(0, lambda: self._webots_lbl.config(text=text, fg=color))

    def set_joystick_name(self, name):
        n = name if name else "— not connected —"
        self.root.after(0, lambda: self._js_name_var.set(n))

    def update_stick(self, vx, vy):
        # vx = -1..1, vy = -1..1
        cx = 50 + vx * 40
        cy = 50 + vy * 40
        self.root.after(0, lambda: self._canvas.coords(
            self._dot, cx-5, cy-5, cx+5, cy+5))

    def _reset_battery(self):
        self.diter.reset_full()

    def _poll(self):
        with self.diter.lock:
            v   = self.diter.voltage
            ia  = self.diter.current_A
            pw  = self.diter.power_W
            soc = self.diter.soc_pct
            rt  = self.diter.runtime_h
            st  = self.diter.status
            uv  = self.diter.uvlo

        self._volt_var.set(f"{v:5.2f}  V")
        self._curr_var.set(f"{ia:5.2f}  A")
        self._pow_var.set(f"{pw:6.1f}  W")
        self._soc_var.set(f"{soc:5.1f}  %")
        self._soc_bar['value'] = soc

        # SOC color
        soc_color = self.GREEN if soc > 30 else (self.YELLOW if soc > 10 else self.RED)
        self._soc_lbl.config(fg=soc_color)

        # Status
        if uv:
            self._status_var.set("Status: ⚠️  LOW VOLTAGE PROTECTION!")
            self._status_lbl.config(fg=self.RED)
        else:
            self._status_var.set(f"Status: {st}")
            self._status_lbl.config(fg=self.YELLOW if st == "RUN" else '#aaa')

        # Runtime
        h = int(rt); m = int((rt - h) * 60)
        self._runtime_var.set(f"Runtime: {h}h {m}m")

        self.root.after(200, self._poll)

    def run(self):
        self.root.mainloop()


# ============================================================
# Main
# ============================================================
def main():
    diter = DiterEngine()
    gui   = ControllerGUI(diter)

    # Start Webots thread
    wt = WebotsThread(diter, gui)
    wt.start()

    # Jalankan GUI di main thread
    gui.run()


if __name__ == '__main__':
    main()
