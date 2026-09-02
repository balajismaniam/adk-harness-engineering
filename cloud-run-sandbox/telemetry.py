"""
Telemetry schemas for Cloud Run Sandbox execution metrics.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class ExecutionIterationTrace(BaseModel):
    """Trace metrics for a single iterative repair turn."""
    iteration_index: int
    hypothesis_attempted: str
    exit_code: int
    execution_latency_ms: float
    sandbox_used: bool
    stdout_snippet: str = ""
    stderr_snippet: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class CloudRunSandboxTelemetry(BaseModel):
    """Consolidated telemetry for Cloud Run Sandbox agent experiments."""
    scenario_name: str
    target_module: str
    total_iterations: int
    functional_test_passed: bool
    sandbox_native_execution: bool
    metadata_blocked_verified: bool = True
    egress_denied_verified: bool = True
    wall_clock_latency_seconds: float
    total_input_tokens: int
    total_output_tokens: int
    iteration_traces: List[ExecutionIterationTrace] = Field(default_factory=list)
    final_repaired_code: Optional[str] = None
    error_summary: Optional[str] = None
