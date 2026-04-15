#!/bin/bash
# ====================================================================
#  BRONE GRAND SIMULATION — Full Simulation Launcher
# ====================================================================
#  Menjalankan SEMUA komponen simulasi secara bersamaan:
#
#  [OP3 HUMANOID]
#    1. Webots OP3 Simulator + External Controller
#    2. op3_manager (simulation mode)
#    3. OP3 GUI Demo (control panel)
#    4. Power Monitor Node (live servo data)
#    5. Simulasi Voltase OpenCR
#
#  [BRONE RODA]
#    6. Webots Roda Simulator + Controller
#    7. Roda Telemetry Node
#
#  [UNIFIED DASHBOARD]
#    8. Unified Dashboard (http://localhost:8080)
#       → Pilih: 🦿 OP3 Body  atau  🛞 BRone Roda
#
#  Semua berjalan di simulasi — TIDAK ada koneksi ke hardware fisik.
#
#  Penggunaan:
#    ./start_grand_simulation.sh                  # Semua komponen
#    ./start_grand_simulation.sh --no-roda        # Tanpa Webots Roda
#    ./start_grand_simulation.sh --no-gui         # Tanpa OP3 GUI Demo
#    ./start_grand_simulation.sh --roda-dummy     # Roda pakai dummy data
#    ./start_grand_simulation.sh --voltage 12.0   # Custom voltase
#
#  Tekan Ctrl+C untuk menghentikan semua.
# ====================================================================

set -e

# ---- Defaults ----
VOLTAGE="11.8"
LAUNCH_GUI=true
LAUNCH_RODA_WEBOTS=true
RODA_DUMMY=false
# ---- Auto-detect paths ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
# Asumsikan repo di-clone di dalam folder src/ colcon workspace (misal: robotis_ws/src/repo)
WORKSPACE="$(cd "$REPO_ROOT/../../" &> /dev/null && pwd || echo "$HOME/robotis_ws")"

# Path Webots (Tetap bisa override via argumen, atau default bawaan ROS)
WEBOTS_HOME=${WEBOTS_HOME:-"$HOME/.ros/webotsR2025a/webots"}

# Path Relatif ke dalam package (Portable)
RODA_WORLD="$REPO_ROOT/simulation/webots_project/worlds/BroneRodaEstimationClosedBeta.wbt"
RODA_CONTROLLER_DIR="$REPO_ROOT/simulation/webots_project/controllers/DITER_Roda_ros_bridge"

# Timing
WAIT_WEBOTS=12
WAIT_MANAGER=8
WAIT_GUI=2
WAIT_RODA=6

# ---- Colors ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m'
BOLD='\033[1m'

# ---- Parse Arguments ----
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-gui)       LAUNCH_GUI=false; shift ;;
        --no-roda)      LAUNCH_RODA_WEBOTS=false; shift ;;
        --roda-dummy)   LAUNCH_RODA_WEBOTS=false; RODA_DUMMY=true; shift ;;
        --voltage)      VOLTAGE="$2"; shift 2 ;;
        -h|--help)
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-gui       Skip OP3 GUI Demo"
            echo "  --no-roda      Skip Webots Roda entirely"
            echo "  --roda-dummy   Roda pakai dummy data (tanpa Webots)"
            echo "  --voltage V    Set simulasi voltase (default: 11.8)"
            echo "  -h, --help     Tampilkan bantuan"
            echo ""
            exit 0
            ;;
        *) echo -e "${RED}Unknown: $1${NC}"; exit 1 ;;
    esac
done

# ---- Process tracking ----
PIDS=()
GNOME_LAUNCHED=false

cleanup() {
    echo ""
    echo -e "${YELLOW}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  🛑 Menghentikan Grand Simulation..."
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
        local pid="${PIDS[$i]}"
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "  ${RED}✗${NC} Stopping PID $pid"
            kill -INT "$pid" 2>/dev/null || true
            sleep 0.3
            kill -0 "$pid" 2>/dev/null && kill -TERM "$pid" 2>/dev/null || true
        fi
    done

    # Kill any leftover webots
    pkill -f "webots" 2>/dev/null || true
    pkill -f "DITER_Roda" 2>/dev/null || true

    wait 2>/dev/null
    echo -e "${GREEN}${BOLD}  ✓ Semua proses dihentikan.${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

wait_progress() {
    local secs=$1 label="$2"
    for (( i=secs; i>0; i-- )); do
        printf "\r    ${YELLOW}⏳ %s... %ds ${NC}" "$label" "$i"
        sleep 1
    done
    printf "\r    ${GREEN}✓ %s — ready!            ${NC}\n" "$label"
}

# ---- Header ----
echo ""
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${CYAN}   🚀 BRONE GRAND SIMULATION${NC}"
echo -e "${BOLD}${CYAN}   OP3 Humanoid + BRone Roda — Full Simulation${NC}"
echo -e "${BOLD}${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  ${BOLD}Config:${NC}"
echo -e "    Voltase      : ${GREEN}${VOLTAGE}V${NC}"
echo -e "    OP3 GUI      : ${LAUNCH_GUI}"
echo -e "    Roda Webots  : ${LAUNCH_RODA_WEBOTS}"
echo -e "    Roda Dummy   : ${RODA_DUMMY}"
echo ""

# ---- Source workspace ----
echo -e "${BLUE}${BOLD}  [0/8] Sourcing ROS2 environment...${NC}"
source /opt/ros/jazzy/setup.bash
source "$WORKSPACE/install/local_setup.bash"
echo -e "    ${GREEN}✓ ROS2 Jazzy + workspace ready${NC}"

# ===================================================================
#  OP3 HUMANOID
# ===================================================================
echo ""
echo -e "${MAGENTA}${BOLD}  ═══════════ 🦿 OP3 HUMANOID ═══════════${NC}"

# [1] Webots OP3 + Extern Controller
echo -e "${MAGENTA}${BOLD}  [1/8] Webots OP3 Simulator + Extern Controller${NC}"
ros2 launch op3_webots_ros2 robot_launch.py &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
wait_progress $WAIT_WEBOTS "Menunggu Webots OP3 startup"

# Verifikasi: tunggu sampai extern controller publish joint_states
echo -e "    ${YELLOW}⏳ Menunggu extern controller (joint_states)...${NC}"
RETRY=0
MAX_RETRY=30
while [ $RETRY -lt $MAX_RETRY ]; do
    if ros2 topic list 2>/dev/null | grep -q "/robotis_op3/joint_states"; then
        # Cek ada publisher aktif
        PUB_COUNT=$(ros2 topic info /robotis_op3/joint_states 2>/dev/null | grep -c "Publisher" || echo 0)
        if [ "$PUB_COUNT" -gt 0 ]; then
            echo -e "    ${GREEN}✓ Extern controller aktif — joint_states terdeteksi!${NC}"
            break
        fi
    fi
    RETRY=$((RETRY + 1))
    sleep 1
done
if [ $RETRY -ge $MAX_RETRY ]; then
    echo -e "    ${RED}⚠ WARNING: joint_states belum terdeteksi setelah ${MAX_RETRY}s${NC}"
    echo -e "    ${RED}  op3_manager mungkin tidak bisa konek. Coba restart.${NC}"
fi

# [2] op3_manager (simulation)
echo -e "${MAGENTA}${BOLD}  [2/8] OP3 Manager (simulation mode)${NC}"
ros2 launch op3_manager op3_simulation.launch.py &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
wait_progress $WAIT_MANAGER "Menunggu op3_manager"

# Verifikasi: tunggu sampai manager menerbitkan /robotis/enable_ctrl_module
echo -e "    ${YELLOW}⏳ Menunggu op3_manager siap...${NC}"
RETRY=0
while [ $RETRY -lt 15 ]; do
    if ros2 topic list 2>/dev/null | grep -q "/robotis/enable_ctrl_module"; then
        echo -e "    ${GREEN}✓ op3_manager ready — siap menerima GUI${NC}"
        break
    fi
    RETRY=$((RETRY + 1))
    sleep 1
done

# [3] OP3 GUI Demo
if [ "$LAUNCH_GUI" = true ]; then
    echo -e "${MAGENTA}${BOLD}  [3/8] OP3 GUI Demo${NC}"
    ros2 launch op3_gui_demo op3_demo.launch.py &
    PIDS+=($!)
    echo -e "    PID: ${PIDS[-1]}"
    sleep $WAIT_GUI
    echo -e "    ${GREEN}✓ GUI Demo started${NC}"
else
    echo -e "${YELLOW}${BOLD}  [3/8] OP3 GUI Demo — SKIPPED${NC}"
fi

# [4] Power Monitor Node + [5] Simulasi Voltase — di terminal terpisah
echo -e "${GREEN}${BOLD}  [4/8] Power Monitor Node${NC}"
echo -e "${YELLOW}${BOLD}  [5/8] Simulasi Voltase (${VOLTAGE}V)${NC}"
gnome-terminal --tab --title="OP3 POWER MONITOR" -- bash -c "
    source /opt/ros/jazzy/setup.bash
    source '$WORKSPACE/install/local_setup.bash'
    echo '═══════════════════════════════════════════'
    echo '  🔋 OP3 Power Monitor + Voltage Sim'
    echo '═══════════════════════════════════════════'
    echo ''
    echo '[1] Starting voltage simulation (${VOLTAGE}V)...'
    ros2 topic pub --rate 1 /robotis/status robotis_controller_msgs/msg/StatusMsg \\
      \"{type: 1, module_name: 'SENSOR', status_msg: 'Present Volt : ${VOLTAGE}V'}\" &
    sleep 1
    echo '[2] Starting power monitor node...'
    ros2 run op3_power_monitor power_monitor_node
    exec bash
" 2>/dev/null
echo -e "    ${GREEN}✓ Power monitor + voltage sim launched (terminal terpisah)${NC}"

# ===================================================================
#  BRONE RODA
# ===================================================================
echo ""
echo -e "${BLUE}${BOLD}  ═══════════ 🛞 BRONE RODA ═══════════${NC}"

if [ "$LAUNCH_RODA_WEBOTS" = true ]; then
    # [6] Webots Roda + Controller
    echo -e "${BLUE}${BOLD}  [6/8] Webots Roda Simulator${NC}"

    # Cek apakah webots binary tersedia
    WEBOTS_BIN=""
    if [ -f "$WEBOTS_HOME/webots" ]; then
        WEBOTS_BIN="$WEBOTS_HOME/webots"
    elif command -v webots &>/dev/null; then
        WEBOTS_BIN="webots"
    elif [ -f "$HOME/.ros/webotsR2025a/webots/webots" ]; then
        WEBOTS_BIN="$HOME/.ros/webotsR2025a/webots/webots"
    fi

    if [ -z "$WEBOTS_BIN" ]; then
        echo -e "    ${RED}✗ Webots binary tidak ditemukan, fallback ke dummy${NC}"
        RODA_DUMMY=true
    elif [ ! -f "$RODA_WORLD" ]; then
        echo -e "    ${RED}✗ World file tidak ditemukan, fallback ke dummy${NC}"
        RODA_DUMMY=true
    else
        gnome-terminal --tab --title="WEBOTS BRONE RODA" -- bash -c "
            source /opt/ros/jazzy/setup.bash
            '$WEBOTS_BIN' --port=1235 '$RODA_WORLD'
            exec bash
        " 2>/dev/null || {
            "$WEBOTS_BIN" --port=1235 "$RODA_WORLD" &
            PIDS+=($!)
        }
        GNOME_LAUNCHED=true
        echo -e "    ✓ Webots Roda launching on port 1235..."
        wait_progress $WAIT_RODA "Menunggu Webots Roda"

        # Controller
        echo -e "${BLUE}${BOLD}  [6b] Roda Controller${NC}"
        if [ -f "$RODA_CONTROLLER_DIR/run_gui.sh" ]; then
            gnome-terminal --tab --title="RODA CONTROLLER" -- bash -c "
                '$RODA_CONTROLLER_DIR/run_gui.sh'
                exec bash
            " 2>/dev/null
            echo -e "    ${GREEN}✓ Roda controller GUI started${NC}"
        else
            echo -e "    ${YELLOW}⚠ run_gui.sh not found, skipping${NC}"
        fi

        # Roda telemetry (di-handle oleh diter_sim_gui.py jika GUI muncul)
        if [ ! -f "$RODA_CONTROLLER_DIR/run_gui.sh" ]; then
            echo -e "${BLUE}${BOLD}  [7/8] Roda Telemetry Node${NC}"
            ros2 run brone_roda_monitor roda_telemetry --ros-args -p robot_ip:="127.0.0.1" &
            PIDS+=($!)
            echo -e "    ${GREEN}✓ Roda telemetry active${NC}"
        else
            echo -e "${BLUE}${BOLD}  [7/8] Roda Telemetry di-handle oleh Controller GUI${NC}"
        fi
    fi
fi

if [ "$RODA_DUMMY" = true ]; then
    echo -e "${BLUE}${BOLD}  [6/8] Roda — DUMMY DATA MODE 🎮${NC}"
    echo -e "${BLUE}${BOLD}  [7/8] Demo Publisher (fake data)${NC}"
    ros2 run op3_power_monitor demo_publisher &
    PIDS+=($!)
    echo -e "    ${GREEN}✓ Dummy data flowing (OP3 + Roda)${NC}"
fi

if [ "$LAUNCH_RODA_WEBOTS" = false ] && [ "$RODA_DUMMY" = false ]; then
    echo -e "${YELLOW}${BOLD}  [6/8] Roda — SKIPPED${NC}"
    echo -e "${YELLOW}${BOLD}  [7/8] Roda — SKIPPED${NC}"
fi

# ===================================================================
#  UNIFIED DASHBOARD
# ===================================================================
echo ""
echo -e "${CYAN}${BOLD}  ═══════════ 🌐 UNIFIED DASHBOARD ═══════════${NC}"
echo -e "${CYAN}${BOLD}  [8/8] Unified Dashboard (port 8080)${NC}"
ros2 run op3_power_monitor unified_dashboard &
PIDS+=($!)
sleep 2
echo -e "    ${GREEN}✓ Dashboard ready${NC}"

# ===================================================================
#  SUMMARY
# ===================================================================
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}   ✅ GRAND SIMULATION AKTIF!${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  🌐 Dashboard: ${BOLD}${CYAN}http://localhost:8080${NC}"
echo -e "     → 🦿 OP3 Body  (klik kartu pertama)"
echo -e "     → 🛞 BRone Roda (klik kartu kedua)"
echo ""
echo -e "  🤖 OP3: Webots + op3_manager + GUI + Power Monitor"
if [ "$LAUNCH_RODA_WEBOTS" = true ] && [ "$RODA_DUMMY" = false ]; then
    echo -e "  🛞 Roda: Webots + Controller + Telemetry"
elif [ "$RODA_DUMMY" = true ]; then
    echo -e "  🛞 Roda: Dummy data mode 🎮"
fi
echo -e "  🔋 Voltase: ${GREEN}${VOLTAGE}V${NC}"
echo ""
echo -e "  Active PIDs: ${#PIDS[@]}"
for pid in "${PIDS[@]}"; do
    echo -e "    └─ $pid"
done
echo ""
echo -e "  ${YELLOW}Tekan Ctrl+C untuk menghentikan semua.${NC}"
echo ""

wait
