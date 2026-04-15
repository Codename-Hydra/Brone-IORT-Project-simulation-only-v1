#!/usr/bin/env python3
"""
BRone Roda — Dashboard Node
=============================
Provides:
  - HTTP server (port 8081) to serve the web dashboard
  - WebSocket server (port 9091) to push real-time telemetry to browser

Subscribes to /brone/power/summary and relays JSON data via WebSocket.
Architecture mirrors op3_power_monitor/power_dashboard_node.py.
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


class RodaDashboardNode(Node):
    """
    Combined HTTP + WebSocket server for BRone Roda dashboard.
    """

    def __init__(self):
        super().__init__('brone_roda_dashboard')

        self._http_port = self.declare_parameter('http_port', 8081).value
        self._ws_port = self.declare_parameter('ws_port', 9091).value

        pkg_share = get_package_share_directory('brone_roda_monitor')
        self._web_dir = str(Path(pkg_share) / 'web')

        self._ws_clients = set()
        self._latest_data = None

        # Subscribe to telemetry summary
        self.create_subscription(String, '/brone/power/summary', self._summary_cb, 10)

        # Start HTTP server in background thread
        self._http_thread = threading.Thread(target=self._run_http, daemon=True)
        self._http_thread.start()

        # Start WebSocket server in background thread
        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        self._ws_thread.start()

        self.get_logger().info(
            '\n[BRone Roda Dashboard] Starting...\n'
            f'  WebSocket: ws://0.0.0.0:{self._ws_port}\n'
            f'  HTTP:      http://0.0.0.0:{self._http_port}\n'
            f'  Web dir:   {self._web_dir}\n'
            '  Subscribed to: /brone/power/summary\n'
            f'\n  Open http://localhost:{self._http_port} in your browser!\n'
        )

    # ---- ROS Callback ----

    def _summary_cb(self, msg: String):
        self._latest_data = msg.data
        # Push to all connected WebSocket clients
        asyncio.run_coroutine_threadsafe(
            self._broadcast(msg.data), self._ws_loop
        )

    # ---- WebSocket Server ----

    def _run_ws(self):
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        self._ws_loop.run_until_complete(self._ws_serve())

    async def _ws_serve(self):
        async with websockets.serve(self._ws_handler, '0.0.0.0', self._ws_port):
            await asyncio.Future()  # Run forever

    async def _ws_handler(self, websocket):
        self._ws_clients.add(websocket)
        client_addr = websocket.remote_address
        self.get_logger().info(f'[Dashboard] Client connected: {client_addr}')
        try:
            async for message in websocket:
                pass  # We don't expect incoming messages
        except websockets.ConnectionClosed:
            pass
        finally:
            self._ws_clients.discard(websocket)
            self.get_logger().info(f'[Dashboard] Client disconnected: {client_addr}')

    async def _broadcast(self, data: str):
        if not self._ws_clients:
            return
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send(data)
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    # ---- HTTP Server ----

    def _run_http(self):
        handler = partial(SimpleHTTPRequestHandler, directory=self._web_dir)
        httpd = HTTPServer(('0.0.0.0', self._http_port), handler)
        httpd.serve_forever()


def main(args=None):
    rclpy.init(args=args)
    node = RodaDashboardNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.get_logger().info('[BRone Roda Dashboard] Shutting down.')
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
