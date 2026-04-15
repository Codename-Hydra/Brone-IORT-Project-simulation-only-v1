#!/usr/bin/env python3
"""
OP3 Power Dashboard — Web-based real-time power monitoring UI.

Subscribes to /op3/power/summary (published by power_monitor_node at 1Hz)
and bridges the JSON data to a WebSocket server. Also serves the static
web dashboard via a built-in HTTP server.

    WebSocket: ws://localhost:9090
    HTTP:      http://localhost:8080

Dependencies: websockets (pip3 install websockets), rclpy.
"""

import asyncio
import os
import threading
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Set

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from std_msgs.msg import String

try:
    import websockets
    import websockets.server
except ImportError:
    raise ImportError(
        "The 'websockets' library is required. Install with:\n"
        "  pip3 install websockets"
    )


# ---------------------------------------------------------------------------
# HTTP Server (serves static files from web/ directory)
# ---------------------------------------------------------------------------

class DashboardHTTPHandler(SimpleHTTPRequestHandler):
    """Serves files from the web/ directory."""

    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()


def start_http_server(web_dir: str, port: int = 8080):
    """Start HTTP server in a background thread."""
    handler = partial(DashboardHTTPHandler, directory=web_dir)
    server = HTTPServer(('0.0.0.0', port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ---------------------------------------------------------------------------
# ROS2 Node
# ---------------------------------------------------------------------------

class PowerDashboardNode(Node):
    """
    Bridges /op3/power/summary → WebSocket for the web dashboard.
    """

    def __init__(self):
        super().__init__('power_dashboard')

        self.declare_parameter('ws_port', 9090)
        self.declare_parameter('http_port', 8080)

        self._ws_port = self.get_parameter('ws_port').value
        self._http_port = self.get_parameter('http_port').value
        self._ws_clients: Set[websockets.WebSocketServerProtocol] = set()
        self._latest_data: str = '{}'
        self._loop: asyncio.AbstractEventLoop = None

        # Subscribe to the summary topic from power_monitor_node
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        self._summary_sub = self.create_subscription(
            String, '/op3/power/summary', self._on_summary, qos
        )

        # Find web directory
        self._web_dir = self._find_web_dir()

        self.get_logger().info(
            f'\n[OP3 Power Dashboard] Starting...'
            f'\n  WebSocket: ws://0.0.0.0:{self._ws_port}'
            f'\n  HTTP:      http://0.0.0.0:{self._http_port}'
            f'\n  Web dir:   {self._web_dir}'
            f'\n  Subscribed to: /op3/power/summary'
            f'\n\n  Open http://localhost:{self._http_port} in your browser!'
        )

    def _find_web_dir(self) -> str:
        """Find the web/ directory relative to this script."""
        candidates = [
            # Source tree
            Path(__file__).parent.parent / 'web',
            # Installed (share directory)
            Path(__file__).parent.parent.parent.parent.parent / 'share' / 'op3_power_monitor' / 'web',
        ]

        # Also check via ament
        try:
            from ament_index_python.packages import get_package_share_directory
            share = get_package_share_directory('op3_power_monitor')
            candidates.insert(0, Path(share) / 'web')
        except Exception:
            pass

        for p in candidates:
            if p.is_dir() and (p / 'index.html').exists():
                return str(p)

        # Fallback
        fallback = str(Path(__file__).parent.parent / 'web')
        self.get_logger().warn(f'Web directory not found, using fallback: {fallback}')
        return fallback

    def _on_summary(self, msg: String) -> None:
        """Receive JSON summary and broadcast to WebSocket clients."""
        self._latest_data = msg.data
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._broadcast(msg.data), self._loop)

    async def _broadcast(self, data: str) -> None:
        """Send data to all connected WebSocket clients."""
        if not self._ws_clients:
            return
        disconnected = set()
        for client in self._ws_clients.copy():
            try:
                await client.send(data)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception:
                disconnected.add(client)
        self._ws_clients -= disconnected

    async def _ws_handler(self, websocket, path=None) -> None:
        """Handle a new WebSocket connection."""
        peer = websocket.remote_address
        self._ws_clients.add(websocket)
        self.get_logger().info(f'[Dashboard] Client connected: {peer}')

        # Send latest data immediately
        if self._latest_data != '{}':
            try:
                await websocket.send(self._latest_data)
            except Exception:
                pass

        try:
            # Keep alive — just wait for messages (we don't expect any)
            async for _ in websocket:
                pass  # Client doesn't send data, but this keeps connection alive
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._ws_clients.discard(websocket)
            self.get_logger().info(f'[Dashboard] Client disconnected: {peer}')

    async def run_ws_server(self) -> None:
        """Start the WebSocket server."""
        self._loop = asyncio.get_event_loop()
        async with websockets.serve(
            self._ws_handler,
            '0.0.0.0',
            self._ws_port,
            ping_interval=20,
            ping_timeout=20,
        ):
            await asyncio.Future()  # Run forever


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main(args=None) -> None:
    rclpy.init(args=args)
    node = PowerDashboardNode()

    # Start HTTP server
    http_server = start_http_server(node._web_dir, node._http_port)

    # Run WebSocket server in a background thread
    def ws_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(node.run_ws_server())

    ws = threading.Thread(target=ws_thread, daemon=True)
    ws.start()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('[OP3 Power Dashboard] Shutting down.')
    finally:
        http_server.shutdown()
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
