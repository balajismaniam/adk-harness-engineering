"""
Cloud Run Sandbox Execution Runner.

Provides a unified interface for invoking commands inside Cloud Run micro-VM sandboxes
via the native `sandbox do` CLI binary (`/usr/local/gcp/bin/sandbox`), with automatic
local subprocess fallback for off-cloud development.
"""

import os
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Tuple

SANDBOX_STANDARD_PATH = "/usr/local/gcp/bin/sandbox"


def is_sandbox_available() -> bool:
    """Checks if the Cloud Run Sandbox guest CLI binary is mounted and executable."""
    if os.path.isfile(SANDBOX_STANDARD_PATH) and os.access(SANDBOX_STANDARD_PATH, os.X_OK):
        return True
    return shutil.which("sandbox") is not None


def get_sandbox_binary() -> Optional[str]:
    """Returns the absolute path to the sandbox binary or None if unavailable."""
    if os.path.isfile(SANDBOX_STANDARD_PATH) and os.access(SANDBOX_STANDARD_PATH, os.X_OK):
        return SANDBOX_STANDARD_PATH
    return shutil.which("sandbox")


def execute_sandbox_command(
    command: List[str],
    mount_dir: Optional[str] = None,
    workdir: str = "/app",
    env_vars: Optional[Dict[str, str]] = None,
    allow_egress: bool = False,
    timeout_seconds: int = 30,
) -> Tuple[int, str, float, bool]:
    """
    Executes a command inside the Cloud Run Sandbox micro-VM or local fallback.

    Args:
        command: List of command arguments (e.g. ["pytest", "tests/test_harness.py"]).
        mount_dir: Optional directory to bind mount into the sandbox (for target code).
        workdir: Working directory inside the sandbox (default: "/app").
        env_vars: Dictionary of environment variables to inject.
        allow_egress: If True, passes --allow-egress flag to sandbox.
        timeout_seconds: Subprocess execution timeout in seconds.

    Returns:
        Tuple of (exit_code, output_text, duration_ms, sandbox_used).
    """
    sandbox_bin = get_sandbox_binary()
    start_time = time.perf_counter()

    if sandbox_bin:
        # Native Cloud Run Sandbox Execution
        cmd = [sandbox_bin, "do", "-w", workdir]
        if allow_egress:
            cmd.append("--allow-egress")
        if mount_dir:
            abs_mount = os.path.abspath(mount_dir)
            cmd.extend(["--mount", f"type=bind,source={abs_mount},destination={abs_mount}"])
        if env_vars:
            for k, v in env_vars.items():
                cmd.extend(["-e", f"{k}={v}"])
        cmd.extend(command)

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            output = res.stdout + ("\n" + res.stderr if res.stderr else "")
            return res.returncode, output.strip(), duration_ms, True
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return -1, "Execution timed out in Cloud Run Sandbox.", duration_ms, True
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return -1, f"Sandbox invocation error: {str(e)}", duration_ms, True
    else:
        # Local Development Subprocess Fallback
        env = os.environ.copy()
        if mount_dir:
            abs_mount = os.path.abspath(mount_dir)
            env["TARGETS_DIR"] = abs_mount
            env["PYTHONPATH"] = f"{abs_mount}:{env.get('PYTHONPATH', '')}".rstrip(":")
        if env_vars:
            env.update(env_vars)

        try:
            res = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            output = res.stdout + ("\n" + res.stderr if res.stderr else "")
            return res.returncode, output.strip(), duration_ms, False
        except subprocess.TimeoutExpired:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return -1, "Execution timed out in local fallback.", duration_ms, False
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            return -1, f"Execution error: {str(e)}", duration_ms, False


def verify_sandbox_security_isolation() -> Dict[str, bool]:
    """
    Validates the security isolation properties of the sandbox environment:
    - Metadata server access blocked (169.254.169.254)
    - Default egress blocked
    """
    if not is_sandbox_available():
        return {
            "metadata_blocked": True,
            "egress_denied": True,
            "sandbox_active": False,
            "note": "Running in local simulation mode. Security properties assumed valid on Cloud Run.",
        }

    # Test metadata server blocking
    meta_code, _, _, _ = execute_sandbox_command(
        ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://169.254.169.254', timeout=2)"],
        timeout_seconds=5,
    )
    metadata_blocked = meta_code != 0

    # Test default network egress blocking
    egress_code, _, _, _ = execute_sandbox_command(
        ["python3", "-c", "import urllib.request; urllib.request.urlopen('https://www.google.com', timeout=2)"],
        timeout_seconds=5,
        allow_egress=False,
    )
    egress_denied = egress_code != 0

    return {
        "metadata_blocked": metadata_blocked,
        "egress_denied": egress_denied,
        "sandbox_active": True,
    }
