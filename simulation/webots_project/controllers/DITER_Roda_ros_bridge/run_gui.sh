#!/bin/bash
# ====================================================================
#  LAUNCHER — BRone Roda DITER Simulation GUI
# ====================================================================
export WEBOTS_HOME="$HOME/.ros/webotsR2025a/webots"

echo -e "\e[1;36m[i] Sourcing ROS 2 Jazzy...\e[0m"
source /opt/ros/jazzy/setup.bash

echo -e "\e[1;36m[i] Menyiapkan path Webots (port 1235)...\e[0m"
export PYTHONPATH="${WEBOTS_HOME}/lib/controller/python:$PYTHONPATH"
export LD_LIBRARY_PATH="${WEBOTS_HOME}/lib/controller:$LD_LIBRARY_PATH"
export WEBOTS_CONTROLLER_URL="ipc://1235"

cd "$(dirname "$0")"

echo -e "\e[1;32m[i] Menjalankan DITER Simulation GUI...\e[0m"
python3 diter_sim_gui.py
