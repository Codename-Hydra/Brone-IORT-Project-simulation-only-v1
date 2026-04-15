#!/usr/bin/env bash
# ================================================================
#  BRONE Grand Simulation — One-Click Launcher
# ================================================================
#
#  Menjalankan SEMUA komponen simulasi dalam satu perintah:
#    1. Webots Simulator
#    2. OP3 Manager (simulation mode)
#    3. OP3 GUI Demo
#    4. Power Monitor Node
#    5. Simulasi Voltase (fake OpenCR voltage)
#    6. Web Dashboard (http://localhost:8080)
#    7. BRone Roda Serial Controller GUI (opsional, --controller)
#
#  Penggunaan:
#    ./start_simulation.sh               # jalankan semua
#    ./start_simulation.sh --no-gui      # tanpa OP3 GUI Demo
#    ./start_simulation.sh --voltage 12.0 # voltase simulasi custom
#    ./start_simulation.sh --controller  # + Serial Controller GUI
#
#  Tekan Ctrl+C untuk menghentikan semua proses sekaligus.
# ================================================================

set -e

# ---- Konfigurasi default ----
VOLTAGE="11.8"
LAUNCH_GUI=true
LAUNCH_CONTROLLER=false
HTTP_PORT=8080
WS_PORT=9090
WAIT_WEBOTS=8        # detik tunggu setelah Webots
WAIT_MANAGER=6       # detik tunggu setelah op3_manager
WAIT_MONITOR=3       # detik tunggu setelah power_monitor
WORKSPACE="$HOME/robotis_ws"

# ---- Warna terminal ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# ---- Parse argumen ----
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-gui)
            LAUNCH_GUI=false
            shift
            ;;
        --controller)
            LAUNCH_CONTROLLER=true
            shift
            ;;
        --voltage)
            VOLTAGE="$2"
            shift 2
            ;;
        --http-port)
            HTTP_PORT="$2"
            shift 2
            ;;
        --ws-port)
            WS_PORT="$2"
            shift 2
            ;;
        --help|-h)
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-gui          Jangan jalankan OP3 GUI Demo"
            echo "  --controller      Jalankan BRone Roda Serial Controller GUI"
            echo "  --voltage VALUE   Set voltase simulasi (default: 11.8)"
            echo "  --http-port PORT  Port HTTP dashboard (default: 8080)"
            echo "  --ws-port PORT    Port WebSocket dashboard (default: 9090)"
            echo "  -h, --help        Tampilkan bantuan ini"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Gunakan --help untuk melihat opsi."
            exit 1
            ;;
    esac
done

# ---- Array untuk menyimpan PID background ----
PIDS=()

# ---- Fungsi cleanup — dipanggil saat Ctrl+C ----
cleanup() {
    echo ""
    echo -e "${YELLOW}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  Menghentikan semua proses..."
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Kill semua child process secara terbalik (LIFO)
    for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
        local pid="${PIDS[$i]}"
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "  ${RED}Stopping PID $pid...${NC}"
            kill -INT "$pid" 2>/dev/null || true
            # Beri waktu untuk graceful shutdown
            sleep 0.5
            kill -0 "$pid" 2>/dev/null && kill -TERM "$pid" 2>/dev/null || true
        fi
    done

    # Tunggu semua selesai
    for pid in "${PIDS[@]}"; do
        wait "$pid" 2>/dev/null || true
    done

    echo -e "${GREEN}${BOLD}  ✓ Semua proses sudah dihentikan.${NC}"
    echo ""
    exit 0
}

trap cleanup SIGINT SIGTERM

# ---- Fungsi helper ----
header() {
    echo ""
    echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  ⚡ BRONE GRAND SIMULATION — One-Click Launcher"
    echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

step() {
    local num="$1"
    local label="$2"
    local color="$3"
    echo -e "${color}${BOLD}  [$num] $label${NC}"
}

wait_with_progress() {
    local seconds=$1
    local label="$2"
    for (( i=seconds; i>0; i-- )); do
        printf "\r    ${YELLOW}⏳ $label... %ds ${NC}" "$i"
        sleep 1
    done
    printf "\r    ${GREEN}✓ $label — done!          ${NC}\n"
}

# ---- Source workspace ----
source_workspace() {
    if [ -f /opt/ros/jazzy/setup.bash ]; then
        source /opt/ros/jazzy/setup.bash
    elif [ -f /opt/ros/humble/setup.bash ]; then
        source /opt/ros/humble/setup.bash
    else
        echo -e "${RED}Error: ROS2 setup.bash tidak ditemukan!${NC}"
        exit 1
    fi

    if [ -f "$WORKSPACE/install/local_setup.bash" ]; then
        source "$WORKSPACE/install/local_setup.bash"
    else
        echo -e "${RED}Error: Workspace belum di-build. Jalankan:${NC}"
        echo "  cd $WORKSPACE && colcon build"
        exit 1
    fi

    # Pastikan op3_power_monitor bisa ditemukan
    local pm_prefix="$WORKSPACE/install/op3_power_monitor"
    if [ -d "$pm_prefix" ]; then
        export AMENT_PREFIX_PATH="$pm_prefix:$AMENT_PREFIX_PATH"
        export PYTHONPATH="$pm_prefix/lib/python3.12/site-packages:$PYTHONPATH"
    fi
}

# ================================================================
#  MAIN
# ================================================================

header

echo -e "  ${BOLD}Konfigurasi:${NC}"
echo -e "    Voltase simulasi : ${GREEN}${VOLTAGE}V${NC}"
echo -e "    GUI Demo         : ${LAUNCH_GUI}"
echo -e "    Serial Controller: ${LAUNCH_CONTROLLER}"
echo -e "    Dashboard        : ${GREEN}http://localhost:${HTTP_PORT}${NC}"
echo -e "    Workspace        : $WORKSPACE"
echo ""

# Source ROS2 + workspace
step "0" "Sourcing ROS2 & workspace..." "$BLUE"
source_workspace
echo -e "    ${GREEN}✓ Environment ready${NC}"

# ---- Step 1: Webots ----
step "1" "Webots Simulator" "$MAGENTA"
ros2 launch op3_webots_ros2 robot_launch.py &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
wait_with_progress $WAIT_WEBOTS "Menunggu Webots siap"

# ---- Step 2: OP3 Manager ----
step "2" "OP3 Manager (simulation mode)" "$MAGENTA"
ros2 launch op3_manager op3_simulation.launch.py &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
wait_with_progress $WAIT_MANAGER "Menunggu op3_manager siap"

# ---- Step 3: OP3 GUI Demo (opsional) ----
if [ "$LAUNCH_GUI" = true ]; then
    step "3" "OP3 GUI Demo" "$MAGENTA"
    ros2 launch op3_gui_demo op3_demo.launch.py &
    PIDS+=($!)
    echo -e "    PID: ${PIDS[-1]}"
    sleep 2
    echo -e "    ${GREEN}✓ GUI Demo started${NC}"
else
    step "3" "OP3 GUI Demo — SKIPPED (--no-gui)" "$YELLOW"
fi

# ---- Step 4: Power Monitor Node ----
step "4" "Power Monitor Node" "$GREEN"
ros2 run op3_power_monitor power_monitor_node &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
wait_with_progress $WAIT_MONITOR "Menunggu power_monitor siap"

# ---- Step 5: Simulasi Voltase ----
step "5" "Simulasi Voltase (${VOLTAGE}V @1Hz)" "$YELLOW"
ros2 topic pub --rate 1 /robotis/status robotis_controller_msgs/msg/StatusMsg \
  "{type: 1, module_name: 'SENSOR', status_msg: 'Present Volt : ${VOLTAGE}V'}" &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
echo -e "    ${GREEN}✓ Publishing voltage: ${VOLTAGE}V${NC}"

# ---- Step 6: Web Dashboard ----
step "6" "Web Dashboard" "$CYAN"
ros2 run op3_power_monitor power_dashboard \
  --ros-args -p http_port:=$HTTP_PORT -p ws_port:=$WS_PORT &
PIDS+=($!)
echo -e "    PID: ${PIDS[-1]}"
sleep 2
echo -e "    ${GREEN}✓ Dashboard ready${NC}"

# ---- Step 7: BRone Roda Serial Controller (opsional) ----
if [ "$LAUNCH_CONTROLLER" = true ]; then
    step "7" "BRone Roda Serial Controller GUI" "$YELLOW"
    ros2 run brone_roda_monitor roda_serial_controller &
    PIDS+=($!)
    echo -e "    PID: ${PIDS[-1]}"
    sleep 1
    echo -e "    ${GREEN}✓ Serial Controller GUI started${NC}"
else
    step "7" "Serial Controller — SKIPPED (tambah --controller untuk aktifkan)" "$YELLOW"
fi

# ---- Selesai ----
echo ""
echo -e "${GREEN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ✅ SEMUA KOMPONEN BERJALAN!"
echo -e "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  🌐 Buka browser: ${BOLD}${CYAN}http://localhost:${HTTP_PORT}${NC}"
echo -e "  🔋 Voltase simulasi: ${GREEN}${VOLTAGE}V${NC}"
if [ "$LAUNCH_CONTROLLER" = true ]; then
    echo -e "  🎮 Serial Controller: ${GREEN}ACTIVE${NC}"
fi
echo ""
echo -e "  Proses aktif (${#PIDS[@]}):"
for (( i=0; i<${#PIDS[@]}; i++ )); do
    echo -e "    PID ${PIDS[$i]}"
done
echo ""
echo -e "  ${YELLOW}Tekan Ctrl+C untuk menghentikan semua.${NC}"
echo ""

# ---- Tunggu sampai Ctrl+C ----
wait
