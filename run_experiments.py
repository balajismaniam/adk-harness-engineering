"""
Google ADK 2.0 Consolidated Analysis Runner

This script coordinates and executes all baseline and advanced multi-agent workflow experiments 
(Case Studies 1-6) using Google ADK 2.0 and the Gemini Enterprise Agent Platform (GEAP) global endpoint.

It supports:
- Sequential execution of all Case Studies or filtering via command-line arguments.
- Instantiation of the ADK 2.0 Runner with In-Memory Session management.
- Dynamic environment/sandbox setup for subprocess validation testing.
- Token-centric telemetry reporting and transcript logging.
"""

import os
import argparse
import asyncio
import time
import uuid
import json
import subprocess
import tempfile
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk import Runner
from google.genai import types

# Validate Gemini Enterprise Agent Platform (GEAP) Backend configurations
if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") and not os.getenv("GOOGLE_GENAI_USE_ENTERPRISE"):
    print("[DEPRECATION_NOTICE] 'GOOGLE_GENAI_USE_VERTEXAI' is deprecated; automatically migrating to 'GOOGLE_GENAI_USE_ENTERPRISE=true'.")
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"
else:
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")

if not os.getenv("GOOGLE_CLOUD_PROJECT"):
    raise ValueError("Environment variable GOOGLE_CLOUD_PROJECT must be set before running experiments.")
if not os.getenv("GOOGLE_CLOUD_LOCATION"):
    raise ValueError("Environment variable GOOGLE_CLOUD_LOCATION must be set before running experiments.")

from workflows.workflows import (
    loop_flow,
    cobol_flow,
    gateway_flow,
    multi_file_flow,
    enhanced_gateway_flow,
    sqli_flow,
    strip_markdown_code
)
from workflows.telemetry_models import TopologyTelemetry


def get_execution_paths(case_study_lower: str = None) -> tuple[str, str, str]:
    """
    Computes target directories for outputs, transcripts, and results.
    Organizes directories under the execution name and task index if STORAGE_MOUNT_PATH
    is configured and exists. Otherwise, defaults to local directories.
    """
    mount_path = os.getenv("STORAGE_MOUNT_PATH")
    if mount_path and os.path.exists(mount_path):
        execution_name = os.getenv("CLOUD_RUN_EXECUTION", "local_run")
        task_index = os.getenv("CLOUD_RUN_TASK_INDEX", "0")
        attempt_num = os.getenv("CLOUD_RUN_TASK_ATTEMPT", "0")
        base_dir = os.path.join(mount_path, execution_name, f"task_{task_index}_attempt_{attempt_num}")
    else:
        base_dir = os.getcwd()
        
    results_dir = os.path.join(base_dir, "results")
    transcripts_dir = os.path.join(results_dir, "transcripts")
    
    if case_study_lower:
        output_dir = os.path.join(base_dir, "output", case_study_lower)
    else:
        output_dir = os.path.join(base_dir, "output")
        
    return output_dir, transcripts_dir, results_dir


async def run_flow_experiment(
    topology_name: str, 
    case_study: str, 
    flow_node, 
    initial_payload: str, 
    initial_state: dict = None,
    expected_route: str = None,
    output_mappings: dict = None
) -> TopologyTelemetry:
    """
    Executes a single workflow graph and returns high-precision telemetry metrics.
    Accumulates Gemini API token metrics and handles sandboxed subprocess testing.
    """
    session_service = InMemorySessionService()
    runner = Runner(
        app_name=f"run_{topology_name.lower()}",
        node=flow_node,
        session_service=session_service,
        auto_create_session=True
    )
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    
    state_delta = {"raw_payload": initial_payload}
    if initial_state:
        state_delta.update(initial_state)
        
    # Track raw absolute latency
    start_time = time.perf_counter()
    
    # Initialize token counters for tracking billing costs across all graph turns.
    # Token-centric tracking is preferred over currency values since API pricing fluctuates.
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    
    error_logs = None
    test_passed = False
    iterations = 1
    
    print(f"\n>>> Running Experiment: {topology_name} / {case_study}...")
    
    try:
        # Asynchronously stream workflow graph events
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(parts=[types.Part(text=initial_payload)]),
            state_delta=state_delta
        ):
            # Accumulate Gemini usage metrics turn-by-turn.
            # 
            # To ensure metric accuracy:
            # 1. No Double Counting: ADK 2.0 structural/routing nodes do not yield usage_metadata. 
            #    Only Agent nodes making actual LLM API calls yield usage_metadata, ensuring we sum 
            #    only actual model invocation transactions.
            # 2. Loop Accumulation: Cyclic loops (like python migration loops and Red/Blue debates)
            #    will yield new events for each retry cycle. This accumulator sums all cycles 
            #    to report the absolute final cost of the session.
            if event.usage_metadata:
                input_tokens += event.usage_metadata.prompt_token_count or 0
                output_tokens += event.usage_metadata.candidates_token_count or 0
                cached_tokens += getattr(event.usage_metadata, "cached_content_token_count", 0) or 0
            
            if event.error_code:
                error_logs = f"Error event from {event.author}: {event.error_code} - {event.error_message}"
                print(f"  [ERROR] {error_logs}")
            elif event.content and event.content.parts:
                txt = "".join([p.text or "" for p in event.content.parts if p.text and not p.thought])
                if txt and len(txt.strip()) > 0:
                    print(f"  [{event.author}] Output length: {len(txt.strip())}")
                    
    except Exception as e:
        error_logs = str(e)
        print(f"  [FATAL ERROR] Run exception encountered: {e}")
        
    latency = time.perf_counter() - start_time
    
    # Retrieve the final session context to capture results
    final_session = await session_service.get_session(
        app_name=runner.app_name,
        user_id=user_id,
        session_id=session_id
    )
    final_state = final_session.state if final_session else {}
    
    # Evaluate metric mappings based on Case Study characteristics
    test_passed = final_state.get("test_passed", False)
    iterations = final_state.get("iteration_count", 0)
    
    # Custom post-run evaluations (isolated sandbox runs or consensus checks).
    # Since the agents generate target code dynamically, we execute their functional checks
    # inside a runtime-generated temporary folder to isolate execution environments.
    if case_study == "COBOL_Modernization" and not error_logs:
        modernized_code = strip_markdown_code(final_state.get("modernized_code", ""))
        if modernized_code:
            # Step 1: Create a random session-isolated subdirectory under /tmp
            session_dir = os.path.join(tempfile.gettempdir(), f"adk_cobol_test_{str(uuid.uuid4())[:8]}")
            os.makedirs(session_dir, exist_ok=True)
            
            # Step 2: Write the modernized module code to this directory
            with open(os.path.join(session_dir, "acctcalc.py"), "w") as f:
                f.write(modernized_code)
                
            # Step 3: Set env variables dynamically to load this directory as the PYTHONPATH
            env = os.environ.copy()
            env["PYTHONPATH"] = session_dir
            pytest_path = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
            
            # Step 4: Run pytest in a subprocess to isolate exceptions
            res = subprocess.run([pytest_path, "tests/test_cobol_modernization.py"], capture_output=True, text=True, env=env)
            
            if res.returncode == 0:
                test_passed = True
                print("  [INFO] Modernized COBOL Python functional test PASSED.")
            else:
                test_passed = False
                error_logs = f"COBOL functional test failed:\n{res.stdout or res.stderr}"
                print(f"  [INFO] Modernized COBOL Python functional test FAILED.")
            
            # Step 5: Clean up the session folder to free local storage space
            try:
                import shutil
                shutil.rmtree(session_dir)
            except Exception:
                pass
                
    elif case_study == "Gateway_Consensus" and not error_logs:
        security_approved = final_state.get("security_approved", False)
        performance_approved = final_state.get("performance_approved", False)
        test_passed = security_approved and performance_approved
        iterations = final_state.get("consensus_iterations", 1)
        print(f"  [INFO] Consensus status: Security={security_approved}, Performance={performance_approved}")

    elif case_study.startswith("Semantic_Routing") and not error_logs:
        choice = final_state.get("routed_flow", "UNKNOWN").strip().upper()
        # Verify classification accuracy (Step 1: Did the gateway direct the payload correctly?)
        routing_ok = (choice == expected_route.strip().upper()) if expected_route else (choice != "UNKNOWN" and choice != "UNSUPPORTED")
        
        # Verify execution accuracy of target subgraph (Step 2: Did the routed subgraph succeed functionally?)
        #
        # Architectural Pattern: End-to-End Gating.
        # Routing-only metric yields false positives if subgraphs fail. This section resolves
        # the metric gap by asserting that the target routed flow successfully modernist/refactored
        # the module (verifying test assertions and exploit defense gates).
        execution_ok = False
        if routing_ok:
            if expected_route == "PYTHON_MIGRATION":
                execution_ok = final_state.get("test_passed", False)
            elif expected_route == "MULTI_FILE_REF":
                execution_ok = final_state.get("test_passed", False)
            elif expected_route == "SQLI_DEFENSE":
                execution_ok = final_state.get("sqli_defense_passed", False)
            elif expected_route == "COBOL_MIGRATION":
                # For COBOL subgraphs, perform custom reflection checks on the output module
                modernized_code = strip_markdown_code(final_state.get("modernized_code", ""))
                if modernized_code:
                    session_dir = os.path.join(tempfile.gettempdir(), f"adk_cobol_gateway_{str(uuid.uuid4())[:8]}")
                    os.makedirs(session_dir, exist_ok=True)
                    with open(os.path.join(session_dir, "acctcalc.py"), "w") as f:
                        f.write(modernized_code)
                    env = os.environ.copy()
                    env["PYTHONPATH"] = session_dir
                    pytest_path = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
                    res = subprocess.run([pytest_path, "tests/test_cobol_modernization.py"], capture_output=True, text=True, env=env)
                    execution_ok = (res.returncode == 0)
                    try:
                        import shutil
                        shutil.rmtree(session_dir)
                    except Exception:
                        pass
            else:
                execution_ok = True  # Generic default
                
        test_passed = routing_ok and execution_ok
        if expected_route == "PYTHON_MIGRATION":
            iterations = final_state.get("iteration_count", 1)
        elif expected_route == "SQLI_DEFENSE":
            iterations = final_state.get("sqli_iteration_count", 1)
        elif expected_route == "MULTI_FILE_REF":
            iterations = final_state.get("iteration_count", 1)
        elif expected_route == "COBOL_MIGRATION":
            iterations = final_state.get("iteration_count", 1)
        else:
            iterations = 1
        print(f"  [INFO] Router choice: {choice} (Expected: {expected_route}) | End-to-End Success: {test_passed}")
        
    elif case_study == "SQLi_Red_Blue_Debate" and not error_logs:
        test_passed = final_state.get("sqli_defense_passed", False)
        iterations = final_state.get("sqli_iteration_count", 1)
        exploit_success = final_state.get("sqli_exploit_success", False)
        print(f"  [INFO] SQLi debate status: DefensePassed={test_passed}, ExploitBypassed={exploit_success}")

    # Save output source files if mapped
    if output_mappings and test_passed:
        output_dir, transcripts_dir, _ = get_execution_paths(case_study.lower())
        os.makedirs(output_dir, exist_ok=True)
        for filename, state_key in output_mappings.items():
            code = final_state.get(state_key, "")
            if code:
                cleaned_code = strip_markdown_code(code)
                dest_file = os.path.join(output_dir, filename)
                with open(dest_file, "w") as f:
                    f.write(cleaned_code)
                print(f"  [INFO] Saved modernized output to: {dest_file}")

    # Write session transcripts
    _, transcripts_dir, _ = get_execution_paths()
    os.makedirs(transcripts_dir, exist_ok=True)
    route_suffix = f"_{expected_route.lower()}" if expected_route else ""
    transcript_filename = f"transcript_{case_study.lower()}{route_suffix}_{topology_name.lower()}.json"
    transcript_path = os.path.join(transcripts_dir, transcript_filename)
    
    events_list = []
    if final_session and final_session.events:
        for ev in final_session.events:
            ev_dict = {
                "author": ev.author,
                "error_code": ev.error_code,
                "error_message": ev.error_message,
            }
            if ev.content:
                parts_list = []
                for part in ev.content.parts:
                    part_dict = {}
                    if part.text:
                        part_dict["text"] = part.text
                    if part.thought:
                        part_dict["thought"] = part.thought
                    parts_list.append(part_dict)
                ev_dict["content"] = {"parts": parts_list, "role": ev.content.role}
            events_list.append(ev_dict)
            
    with open(transcript_path, "w") as f:
        json.dump(events_list, f, indent=2)
    print(f"  [INFO] Saved session transcript to: {transcript_path}")

    case_study_name = case_study
    if case_study.startswith("Semantic_Routing") and expected_route:
        case_study_name = f"{case_study}_{expected_route}"

    return TopologyTelemetry(
        topology_name=topology_name,
        case_study=case_study_name,
        wall_clock_latency_seconds=round(latency, 3),
        input_tokens_consumed=input_tokens,
        cached_tokens_consumed=cached_tokens,
        output_tokens_generated=output_tokens,
        functional_test_passed=test_passed,
        execution_iterations=iterations,
        error_logs=error_logs
    )


async def main():
    parser = argparse.ArgumentParser(description="Google ADK 2.0 Unified Analysis Runner")
    parser.add_argument(
        "--case-study",
        type=str,
        default="all",
        choices=["1", "2", "3", "4", "5", "6", "all"],
        help="Specific Case Study number to run, or 'all' to run all sequentially."
    )
    args = parser.parse_args()

    task_index_str = os.getenv("CLOUD_RUN_TASK_INDEX")
    if args.case_study == "all" and task_index_str is not None:
        assigned_case_study = str((int(task_index_str) % 6) + 1)
        print(f"  [INFO] Cloud Run Task Index {task_index_str} detected. Auto-mapping to Case Study {assigned_case_study}.")
        args.case_study = assigned_case_study

    # Load baseline target payloads
    with open("targets/legacy_analytics.py", "r") as f:
        legacy_python = f.read()
    with open("targets/ACCTCALC.cbl", "r") as f:
        legacy_cobol = f.read()
    with open("targets/db_helper.py") as f:
        db_h = f.read()
    with open("targets/user_dao.py") as f:
        usr_d = f.read()
    with open("targets/admin_service.py") as f:
        adm_s = f.read()
    with open("targets/vulnerable_query.py") as f:
        vuln_sql = f.read()

    results = []

    # Mapping of case study executions
    # Case Study 1: Loop Migration
    async def run_cs1():
        telemetry = await run_flow_experiment(
            topology_name="Loop",
            case_study="Python_Migration",
            flow_node=loop_flow,
            initial_payload=legacy_python,
            initial_state={"iteration_count": 0, "test_passed": False},
            output_mappings={"legacy_analytics.py": "modernized_code"}
        )
        results.append(telemetry)

    # Case Study 2: Parallel COBOL Parsing
    async def run_cs2():
        telemetry = await run_flow_experiment(
            topology_name="Parallel",
            case_study="COBOL_Modernization",
            flow_node=cobol_flow,
            initial_payload=legacy_cobol,
            initial_state={"iteration_count": 0, "test_passed": False},
            output_mappings={"acctcalc.py": "modernized_code"}
        )
        results.append(telemetry)

    # Case Study 3: Baseline Gateway Consensus
    async def run_cs3():
        telemetry = await run_flow_experiment(
            topology_name="Dynamic_Gateway",
            case_study="Gateway_Consensus",
            flow_node=gateway_flow,
            initial_payload=legacy_python,
            initial_state={
                "iteration_count": 0, 
                "test_passed": False, 
                "consensus_iterations": 0,
                "security_approved": False,
                "performance_approved": False
            },
            output_mappings={"legacy_analytics.py": "modernized_code"}
        )
        results.append(telemetry)

    # Case Study 4: Multi-File Dependency Refactoring
    async def run_cs4():
        telemetry = await run_flow_experiment(
            topology_name="Parallel_MultiFile",
            case_study="Multi_File_Refactoring",
            flow_node=multi_file_flow,
            initial_payload="Refactor db_helper's get_connection signature to require host, port, user, and password.",
            initial_state={
                "db_helper": db_h,
                "user_dao": usr_d,
                "admin_service_code": adm_s,
                "iteration_count": 0,
                "test_passed": False
            },
            output_mappings={
                "db_helper.py": "modernized_db_helper",
                "user_dao.py": "modernized_user_dao",
                "admin_service.py": "modernized_admin_service"
            }
        )
        results.append(telemetry)

    # Case Study 5: SQLi Red/Blue Debate Loop
    async def run_cs5():
        telemetry = await run_flow_experiment(
            topology_name="Adversarial_SQLiDefense",
            case_study="SQLi_Red_Blue_Debate",
            flow_node=sqli_flow,
            initial_payload=vuln_sql,
            initial_state={
                "sqli_vulnerable_code": vuln_sql,
                "sqli_iteration_count": 0,
                "sqli_defense_passed": False,
                "sqli_exploit_success": False
            },
            output_mappings={
                "vulnerable_query.py": "sqli_secured_code"
            }
        )
        results.append(telemetry)

    # Case Study 6: Semantic Routing Gateway fanning
    async def run_cs6():
        payloads_to_test = [
            (
                legacy_python,
                "PYTHON_MIGRATION",
                {"iteration_count": 0, "test_passed": False},
                {"legacy_analytics.py": "modernized_code"}
            ),
            (
                legacy_cobol,
                "COBOL_MIGRATION",
                {"iteration_count": 0, "test_passed": False},
                {"acctcalc.py": "modernized_code"}
            ),
            (
                "Refactor db_helper to add host and port parameters across files.",
                "MULTI_FILE_REF",
                {"db_helper": db_h, "user_dao": usr_d, "admin_service_code": adm_s, "iteration_count": 0, "test_passed": False},
                {"db_helper.py": "modernized_db_helper", "user_dao.py": "modernized_user_dao", "admin_service.py": "modernized_admin_service"}
            ),
            (
                "Secure vulnerable SQL query against injection payloads.",
                "SQLI_DEFENSE",
                {"sqli_vulnerable_code": vuln_sql, "sqli_iteration_count": 0, "sqli_defense_passed": False, "sqli_exploit_success": False},
                {"vulnerable_query.py": "sqli_secured_code"}
            )
        ]
        for payload, expected, init_state, out_maps in payloads_to_test:
            state = {"routed_flow": "UNKNOWN"}
            state.update(init_state)
            telemetry = await run_flow_experiment(
                topology_name="Dynamic_SemanticGateway",
                case_study="Semantic_Routing",
                flow_node=enhanced_gateway_flow,
                initial_payload=payload,
                initial_state=state,
                expected_route=expected,
                output_mappings=out_maps
            )
            results.append(telemetry)

    # Execute selected runs
    if args.case_study == "1":
        await run_cs1()
    elif args.case_study == "2":
        await run_cs2()
    elif args.case_study == "3":
        await run_cs3()
    elif args.case_study == "4":
        await run_cs4()
    elif args.case_study == "5":
        await run_cs5()
    elif args.case_study == "6":
        await run_cs6()
    else:
        # Run all sequentially
        await run_cs1()
        await run_cs2()
        await run_cs3()
        await run_cs4()
        await run_cs5()
        await run_cs6()

    print("\n================ EXPERIMENTS RESULTS ================")
    for r in results:
        print(r.model_dump_json(indent=2))
        
    _, _, results_dir = get_execution_paths()
    os.makedirs(results_dir, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(results_dir, f"experiments_results_{timestamp}.json")
    with open(report_path, "w") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)
    print(f"\nWritten consolidated telemetry report to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
