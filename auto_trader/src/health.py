"""
Tiny HTTP healthcheck endpoint so an external uptime monitor (UptimeRobot,
healthchecks.io, etc.) can alert you the moment the bot stops updating —
this is what makes "goes offline" something you find out about immediately
instead of at end of day.
"""

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer


class _Handler(BaseHTTPRequestHandler):
    status_ref = {}

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.status_ref).encode())

    def log_message(self, format, *args):
        pass


def start_health_server(port: int, status: dict) -> HTTPServer:
    _Handler.status_ref = status
    server = HTTPServer(("0.0.0.0", port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def heartbeat(status: dict):
    status["last_heartbeat"] = datetime.now().isoformat()
    status["ok"] = True
