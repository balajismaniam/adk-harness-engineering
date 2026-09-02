"""
Lightweight HTTP Server for Cloud Run Sandbox Service Deployments.

Provides health checks and REST endpoints for triggering code modernization
repair loops inside Cloud Run Sandboxes.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

try:
    from .repair_loop import run_modernization_repair_loop
    from .sandbox_runner import is_sandbox_available, verify_sandbox_security_isolation
except (ImportError, ValueError):
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    from repair_loop import run_modernization_repair_loop
    from sandbox_runner import is_sandbox_available, verify_sandbox_security_isolation


class SandboxHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler exposing health probes and sandbox run endpoints."""

    def _send_json_response(self, status_code: int, data: Dict[str, Any]):
        response_body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def do_GET(self):
        """Handles health probes and security isolation queries."""
        if self.path in ("/", "/healthz", "/health"):
            self._send_json_response(200, {
                "status": "ok",
                "service": "adk-sandbox-service",
                "sandbox_available": is_sandbox_available(),
                "endpoints": {
                    "POST /run": "Execute modernization repair loop in sandbox",
                    "GET /verify-security": "Verify metadata and egress isolation properties",
                }
            })
        elif self.path == "/verify-security":
            sec_results = verify_sandbox_security_isolation()
            self._send_json_response(200, sec_results)
        else:
            self._send_json_response(404, {"error": "Not Found", "path": self.path})

    def do_POST(self):
        """Handles requests to trigger the modernization repair loop."""
        if self.path == "/run":
            content_length = int(self.headers.get("Content-Length", 0))
            body_dict = {}
            if content_length > 0:
                try:
                    raw_body = self.rfile.read(content_length)
                    body_dict = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    body_dict = {}

            mock_mode = body_dict.get("mock", False)
            model_name = body_dict.get("model", "gemini-3.5-flash")

            try:
                telemetry = run_modernization_repair_loop(
                    target_source_path="targets/legacy_analytics.py",
                    test_harness_path="tests/test_harness.py",
                    max_cycles=5,
                    mock=mock_mode,
                    model_name=model_name,
                )
                self._send_json_response(200, telemetry.model_dump())
            except Exception as e:
                self._send_json_response(500, {
                    "status": "error",
                    "error": str(e),
                })
        else:
            self._send_json_response(404, {"error": "Not Found", "path": self.path})


def run_server(port: int = 8080):
    """Starts the HTTP server listening on the specified port."""
    server_address = ("", port)
    httpd = HTTPServer(server_address, SandboxHTTPRequestHandler)
    print(f"Cloud Run Sandbox HTTP Service listening on port {port}...")
    print(f"Sandbox native binary detected: {is_sandbox_available()}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    run_server(port)
