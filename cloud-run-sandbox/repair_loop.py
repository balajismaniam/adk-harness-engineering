"""
Self-Correcting Code Modernization Repair Loop inside Cloud Run Sandboxes.

Demonstrates multi-turn Python 2.7 -> 3.x semantic migration of legacy_analytics.py
using Gemini 3.5 Flash and isolated micro-VM sandboxes.
"""

import os
import re
import tempfile
import time
from typing import List, Optional, Tuple

from google.genai import Client, types

try:
    from .sandbox_runner import execute_sandbox_command, is_sandbox_available
    from .telemetry import CloudRunSandboxTelemetry, ExecutionIterationTrace
except (ImportError, ValueError):
    from sandbox_runner import execute_sandbox_command, is_sandbox_available
    from telemetry import CloudRunSandboxTelemetry, ExecutionIterationTrace


def strip_markdown_code(code: str) -> str:
    """Strips markdown backticks to extract raw Python source code."""
    code = code.strip()
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        return match.group(1).strip()
    return code.strip()


# Deterministic simulated stages for mock/offline testing
MOCK_REPAIR_STAGES = [
    # Stage 1: Fixes print syntax and map iterator; still has float division & binary read mode traps
    (
        "import csv\n\n"
        "def process_historical_logs(file_path, downsample_rate):\n"
        "    print(f'Beginning log processing for: {file_path}')\n"
        "    stride = downsample_rate / 2\n"
        "    with open(file_path, 'rb') as f:\n"
        "        reader = csv.reader(f)\n"
        "        records = [row for row in reader]\n"
        "    log_data = list(map(lambda r: r, records[::stride]))\n"
        "    log_data.reverse()\n"
        "    return log_data\n"
    ),
    # Stage 2: Fixes print and floor division; still has binary read mode trap
    (
        "import csv\n\n"
        "def process_historical_logs(file_path, downsample_rate):\n"
        "    print(f'Beginning log processing for: {file_path}')\n"
        "    stride = max(1, downsample_rate // 2)\n"
        "    with open(file_path, 'rb') as f:\n"
        "        reader = csv.reader(f)\n"
        "        records = [row for row in reader]\n"
        "    log_data = list(map(lambda r: r, records[::stride]))\n"
        "    log_data.reverse()\n"
        "    return log_data\n"
    ),
    # Stage 3: Fully corrected Python 3 implementation
    (
        "import csv\n\n"
        "def process_historical_logs(file_path, downsample_rate):\n"
        "    print(f'Beginning log processing for: {file_path}')\n"
        "    stride = max(1, downsample_rate // 2)\n"
        "    try:\n"
        "        with open(file_path, 'r', encoding='utf-8') as f:\n"
        "            reader = csv.reader(f)\n"
        "            records = [row for row in reader]\n"
        "    except FileNotFoundError:\n"
        "        return []\n"
        "    log_data = list(map(lambda r: r, records[::stride]))\n"
        "    log_data.reverse()\n"
        "    return log_data\n"
    ),
]


def generate_pruned_repair_prompt(
    current_code: str,
    active_traceback: str,
    tried_hypotheses: List[str],
) -> str:
    """Assembles the pruned context prompt to guide the LLM through self-correction."""
    hypotheses_str = "\n".join(f"- {h}" for h in tried_hypotheses) if tried_hypotheses else "None"
    return (
        "You are an expert Python modernization engineer repairing legacy Python 2 code for Python 3 compatibility.\n\n"
        "### Current Code on Disk:\n"
        "```python\n"
        f"{current_code}\n"
        "```\n\n"
        "### Unit Test Failure Traceback (Captured from Sandbox):\n"
        "```\n"
        f"{active_traceback}\n"
        "```\n\n"
        "### Previously Attempted Hypotheses (Failed):\n"
        f"{hypotheses_str}\n\n"
        "Please fix legacy_analytics.py to resolve the error and satisfy all unit tests.\n"
        "Pay special attention to Python 3 integer division semantics and CSV text versus binary file modes.\n"
        "CRITICAL: Output ONLY the complete Python code block wrapped in ```python ... ```."
    )


def summarize_hypothesis(client: Optional[Client], prev_code: str, new_code: str, mock: bool = False) -> Tuple[str, int, int]:
    """Generates a concise summary of the hypothesis attempted in this iteration."""
    if mock or client is None:
        if "'r'" in new_code:
            return "Converted CSV file open mode from 'rb' to 'r' text mode", 70, 15
        elif "// 2" in new_code:
            return "Converted division to integer floor division (//)", 60, 12
        elif "print(" in new_code:
            return "Converted print statement to function call", 50, 10
        return "Applied incremental code adjustments", 40, 8

    prompt = (
        "Compare the previous code and the proposed updated code. "
        "Summarize the main correction or hypothesis attempted in a short, single-sentence phrase "
        "(e.g., 'Converted print statement to function call' or 'Fixed floor division for list stride').\n\n"
        f"Previous:\n{prev_code}\n\n"
        f"Proposed:\n{new_code}\n\n"
        "Summary:"
    )
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt,
        )
        summary = response.text.strip()
        p_tok = response.usage_metadata.prompt_token_count or 0
        c_tok = response.usage_metadata.candidates_token_count or 0
        return summary, p_tok, c_tok
    except Exception as e:
        return f"Code correction applied ({str(e)})", 0, 0


def run_modernization_repair_loop(
    target_source_path: str = "targets/legacy_analytics.py",
    test_harness_path: str = "tests/test_harness.py",
    max_cycles: int = 5,
    mock: bool = False,
    model_name: str = "gemini-3.5-flash",
) -> CloudRunSandboxTelemetry:
    """
    Executes the multi-turn code modernization loop with isolated sandbox execution.
    """
    start_wall_time = time.perf_counter()
    session_id = f"sandbox_session_{int(time.time())}"
    temp_dir = os.path.join(tempfile.gettempdir(), session_id)
    os.makedirs(temp_dir, exist_ok=True)

    # Read original legacy target code
    if os.path.exists(target_source_path):
        with open(target_source_path, "r", encoding="utf-8") as f:
            original_code = f.read()
    else:
        original_code = (
            "import csv\n\n"
            "def process_historical_logs(file_path, downsample_rate):\n"
            "    print \"Beginning log processing for:\", file_path\n"
            "    stride = downsample_rate / 2\n"
            "    with open(file_path, 'rb') as f:\n"
            "        reader = csv.reader(f)\n"
            "        records = [row for row in reader]\n"
            "    return records[::stride]\n"
        )

    current_target_file = os.path.join(temp_dir, "legacy_analytics.py")
    with open(current_target_file, "w", encoding="utf-8") as f:
        f.write(original_code)

    # Setup test harness in sandbox directory
    harness_target_file = os.path.join(temp_dir, "test_harness.py")
    if os.path.exists(test_harness_path):
        with open(test_harness_path, "r", encoding="utf-8") as f:
            harness_code = f.read()
    else:
        harness_code = (
            "import os\n"
            "import pytest\n"
            "from legacy_analytics import process_historical_logs\n\n"
            "def test_migration_accuracy(tmp_path):\n"
            "    log_file = tmp_path / 'test_logs.csv'\n"
            "    log_file.write_text('id,event\\n1,login\\n2,click\\n3,logout\\n4,purchase\\n5,exit')\n"
            "    try:\n"
            "        result = process_historical_logs(str(log_file), downsample_rate=5)\n"
            "        assert len(result) == 3\n"
            "        assert result[1][1] == 'click'\n"
            "        print('MIGRATION_SUCCESS: Target module functionality verified.')\n"
            "    except TypeError as e:\n"
            "        print(f'MIGRATION_RUNTIME_FAIL: {str(e)}')\n"
            "        raise e\n\n"
            "def test_empty_log_file(tmp_path):\n"
            "    log_file = tmp_path / 'empty.csv'\n"
            "    log_file.write_text('')\n"
            "    result = process_historical_logs(str(log_file), downsample_rate=2)\n"
            "    assert result == []\n\n"
            "def test_invalid_arguments(tmp_path):\n"
            "    log_file = tmp_path / 'nonexistent.csv'\n"
            "    result = process_historical_logs(str(log_file), downsample_rate=2)\n"
            "    assert result == []\n"
        )
    with open(harness_target_file, "w", encoding="utf-8") as f:
        f.write(harness_code)

    client = None
    if not mock:
        client = Client()

    pytest_bin = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
    iteration_traces: List[ExecutionIterationTrace] = []
    tried_hypotheses: List[str] = []
    current_code = original_code
    prev_code = original_code

    total_input_tokens = 0
    total_output_tokens = 0
    test_passed = False
    mock_stage_idx = 0

    print("=================================================================")
    print(f"Starting Cloud Run Sandbox Modernization Repair Loop (Mock={mock})")
    print(f"Sandbox Environment Detected: {is_sandbox_available()}")
    print("=================================================================")

    for cycle in range(1, max_cycles + 1):
        print(f"\n--- [Cycle {cycle}/{max_cycles}] Executing Verification Test in Sandbox ---")

        # 1. Execute tests inside the Sandbox Micro-VM
        exit_code, output_text, duration_ms, sandbox_used = execute_sandbox_command(
            command=[pytest_bin, harness_target_file],
            mount_dir=temp_dir,
            timeout_seconds=20,
        )

        print(f"  Execution Time: {duration_ms:.2f}ms | Sandbox Used: {sandbox_used} | Exit Code: {exit_code}")

        if exit_code == 0:
            print(f"  [SUCCESS] All unit tests passed on cycle {cycle}!")
            test_passed = True
            iteration_traces.append(
                ExecutionIterationTrace(
                    iteration_index=cycle,
                    hypothesis_attempted="All tests passed. Code verified functional.",
                    exit_code=0,
                    execution_latency_ms=duration_ms,
                    sandbox_used=sandbox_used,
                    stdout_snippet=output_text[:300],
                )
            )
            break

        # Capture failure feedback
        active_traceback = output_text
        print(f"  [FAILURE TRAPPED] Exit code {exit_code}. Raw stderr/stdout captured.")

        # 2. Generate correction hypothesis via LLM
        cycle_input_tokens = 0
        cycle_output_tokens = 0

        if mock:
            if mock_stage_idx < len(MOCK_REPAIR_STAGES):
                new_code = MOCK_REPAIR_STAGES[mock_stage_idx]
                mock_stage_idx += 1
            else:
                new_code = MOCK_REPAIR_STAGES[-1]
            cycle_input_tokens = 450 + cycle * 50
            cycle_output_tokens = 120
            hyp_desc, _, _ = summarize_hypothesis(None, prev_code, new_code, mock=True)
        else:
            prompt = generate_pruned_repair_prompt(current_code, active_traceback, tried_hypotheses)
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            new_code = strip_markdown_code(response.text)
            cycle_input_tokens = response.usage_metadata.prompt_token_count or 0
            cycle_output_tokens = response.usage_metadata.candidates_token_count or 0
            hyp_desc, sum_in, sum_out = summarize_hypothesis(client, prev_code, new_code, mock=False)
            cycle_input_tokens += sum_in
            cycle_output_tokens += sum_out

        total_input_tokens += cycle_input_tokens
        total_output_tokens += cycle_output_tokens
        tried_hypotheses.append(f"Cycle {cycle}: {hyp_desc}")

        iteration_traces.append(
            ExecutionIterationTrace(
                iteration_index=cycle,
                hypothesis_attempted=hyp_desc,
                exit_code=exit_code,
                execution_latency_ms=duration_ms,
                sandbox_used=sandbox_used,
                stdout_snippet=output_text[:300],
                stderr_snippet=active_traceback[:300],
                input_tokens=cycle_input_tokens,
                output_tokens=cycle_output_tokens,
            )
        )

        # Update disk file for next cycle
        prev_code = current_code
        current_code = new_code
        with open(current_target_file, "w", encoding="utf-8") as f:
            f.write(current_code)

    total_wall_time = time.perf_counter() - start_wall_time

    # Cleanup temporary session directory
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    telemetry = CloudRunSandboxTelemetry(
        scenario_name="Python_2_to_3_Semantic_Migration",
        target_module="legacy_analytics.py",
        total_iterations=len(iteration_traces),
        functional_test_passed=test_passed,
        sandbox_native_execution=is_sandbox_available(),
        wall_clock_latency_seconds=round(total_wall_time, 3),
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        iteration_traces=iteration_traces,
        final_repaired_code=current_code if test_passed else None,
    )

    print("\n=================================================================")
    print("Telemetry Payload:")
    print(telemetry.model_dump_json(indent=2))
    print("=================================================================")

    return telemetry
