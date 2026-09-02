"""
Cloud Run Sandboxes: Isolated Ephemeral Execution Package for AI Coding Agents.

This package provides:
- Low-level Cloud Run Sandbox CLI (`sandbox do`) wrappers with automatic local development fallback.
- Self-correcting iterative modernization repair loops using Google ADK 2.0 and Gemini 3.5 Flash.
- Automated token, latency, and isolation telemetry tracking.
- Automated video assembly pipelines and production-ready blog/video artifacts.
"""

from .sandbox_runner import (
    is_sandbox_available,
    get_sandbox_binary,
    execute_sandbox_command,
    verify_sandbox_security_isolation,
)
from .repair_loop import (
    strip_markdown_code,
    generate_pruned_repair_prompt,
    summarize_hypothesis,
    run_modernization_repair_loop,
)
from .telemetry import (
    ExecutionIterationTrace,
    CloudRunSandboxTelemetry,
)

__version__ = "1.0.0"
__all__ = [
    "is_sandbox_available",
    "get_sandbox_binary",
    "execute_sandbox_command",
    "verify_sandbox_security_isolation",
    "strip_markdown_code",
    "generate_pruned_repair_prompt",
    "summarize_hypothesis",
    "run_modernization_repair_loop",
    "ExecutionIterationTrace",
    "CloudRunSandboxTelemetry",
]
