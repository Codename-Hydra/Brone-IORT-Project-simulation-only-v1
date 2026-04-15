#!/usr/bin/env python3
"""
BRONE Unified Dashboard Node
=============================
Single server that hosts both OP3 Body and BRone Roda dashboards.
  - HTTP: port 8080
  - WebSocket for OP3:    port 9090
  - WebSocket for Roda:   port 9091

Subscribes to:
  /op3/power/summary    → relayed to WS:9090
  /brone/power/summary  → relayed to WS:9091
"""

import json
import asyncio
import threading
from pathlib import Path
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

try:
    import websockets
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'websockets'])
    import websockets

from ament_index_python.packages import get_package_share_directory


class UnifiedDashboardNode(Node):
    def __init__(self):
        super().__init__('brone_unified_dashboard')

        self._http_port = self.declare_parameter('http_port', 8080).value
        self._ws_op3_port = self.declare_parameter('ws_op3_port', 9090).value
        self._ws_roda_port = self.declare_parameter('ws_roda_port', 9091).value

        # Try op3_power_monitor first (has the unified web dir)
        try:
            pkg_share = get_package_share_directory('op3_power_monitor')
        except Exception:
            pkg_share = get_package_share_directory('brone_roda_monitor')
        self._web_dir = str(Path(pkg_share) / 'web')

        # WebSocket client sets
        self._op3_clients = set()
        self._roda_clients = set()

        # Subscriptions
        self.create_subscription(String, '/op3/power/summary', self._op3_cb, 10)
        self.create_subscription(String, '/brone/power/summary', self._roda_cb, 10)

        # WebSocket event loops
        self._op3_loop = None
        self._roda_loop = None

        # Start servers
        threading.Thread(target=self._run_http, daemon=True).start()
        threading.Thread(target=self._run_ws_op3, daemon=True).start()
        threading.Thread(target=self._run_ws_roda, daemon=True).start()

        self.get_logger().info(
            '\n[BRONE Unified Dashboard] Starting...\n'
            f'  HTTP:          http://0.0.0.0:{self._http_port}\n'
            f'  WS (OP3):      ws://0.0.0.0:{self._ws_op3_port}\n'
            f'  WS (Roda):     ws://0.0.0.0:{self._ws_roda_port}\n'
            f'  Web dir:       {self._web_dir}\n'
            f'\n  Open http://localhost:{self._http_port} in your browser!\n'
        )

    # ---- ROS Callbacks ----

    def _op3_cb(self, msg: String):
        if self._op3_loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast(self._op3_clients, msg.data), self._op3_loop
            )

    def _roda_cb(self, msg: String):
        if self._roda_loop:
            asyncio.run_coroutine_threadsafe(
                self._broadcast(self._roda_clients, msg.data), self._roda_loop
            )

    # ---- Broadcast ----

    async def _broadcast(self, clients, data):
        if not clients:
            return
        dead = set()
        for ws in clients:
            try:
                await ws.send(data)
            except Exception:
                dead.add(ws)
        clients -= dead

    # ---- WebSocket Servers ----

    def _run_ws_op3(self):
        self._op3_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._op3_loop)
        self._op3_loop.run_until_complete(self._ws_serve(
            self._op3_clients, self._ws_op3_port, 'OP3'
        ))

    def _run_ws_roda(self):
        self._roda_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._roda_loop)
        self._roda_loop.run_until_complete(self._ws_serve(
            self._roda_clients, self._ws_roda_port, 'Roda'
        ))

    async def _ws_serve(self, clients, port, label):
        async def handler(websocket):
            clients.add(websocket)
            addr = websocket.remote_address
            self.get_logger().info(f'[{label}] Client connected: {addr}')
            try:
                async for _ in websocket:
                    pass
            except websockets.ConnectionClosed:
                pass
            finally:
                clients.discard(websocket)
                self.get_logger().info(f'[{label}] Client disconnected: {addr}')

        async with websockets.serve(handler, '0.0.0.0', port):
            await asyncio.Future()

    # ---- HTTP Server ----

    def _run_http(self):
        handler = partial(SimpleHTTPRequestHandler, directory=self._web_dir)
        httpd = HTTPServer(('0.0.0.0', self._http_port), handler)
        httpd.serve_forever()


def main(args=None):
    rclpy.init(args=args)
    node = UnifiedDashboardNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('[Unified Dashboard] Shutting down.')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
