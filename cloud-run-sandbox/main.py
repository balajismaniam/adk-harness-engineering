"""
Main Entrypoint for Cloud Run Sandboxes (Jobs and Services).

Automatically detected by Google Cloud Buildpacks during source deployment.
- Service Mode ($PORT is set): Launches HTTP REST server.
- Job Mode ($PORT is unset): Launches modernization repair loop benchmark runner.
"""

import json
import os
import sys

try:
    from .run_sandbox_experiments import main as run_experiments_main
    from .server import run_server
    from .sandbox_runner import is_sandbox_available
except (ImportError, ValueError):
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    from run_sandbox_experiments import main as run_experiments_main
    from server import run_server
    from sandbox_runner import is_sandbox_available


def app(environ, start_response):
    """WSGI callable fallback for gunicorn/uvicorn runners."""
    status = "200 OK"
    headers = [("Content-Type", "application/json")]
    start_response(status, headers)
    payload = json.dumps({
        "status": "ok",
        "service": "adk-sandbox-agent",
        "sandbox_available": is_sandbox_available(),
    }, indent=2)
    return [payload.encode("utf-8")]


def main():
    # Only run HTTP server if explicitly requested (--server) or running as a Cloud Run Service (K_SERVICE is set)
    is_service = "--server" in sys.argv or (
        os.environ.get("K_SERVICE") is not None
        and os.environ.get("CLOUD_RUN_JOB") is None
        and "--job" not in sys.argv
    )

    if is_service:
        port = int(os.environ.get("PORT", "8080"))
        run_server(port)
    else:
        run_experiments_main()


if __name__ == "__main__":
    main()
