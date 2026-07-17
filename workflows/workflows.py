"""
Google ADK 2.0 Workflows Module (Unified blueprints)

This module defines all baseline and advanced multi-agent workflows (Case Studies 1-6)
implemented using the Google Agent Development Kit (ADK) 2.0.

It illustrates the three core ADK 2.0 workflow features:
1. Graph-based workflows: Deterministic execution architectures using explicit nodes and edges
   (demonstrated by cobol_flow and multi_file_flow).
2. Dynamic workflows: Code-based routing logic for loops, dynamic gateway pathing, and retries
   (demonstrated by loop_flow, semantic_routing, and sqli_flow).
3. Collaborative workflows: Complex peer-to-peer debates, reviews, and adversarial consensus boards
   (demonstrated by gateway_flow's consensus board and sqli_flow's Red/Blue debate).
"""

import subprocess
import os
import re
import tempfile
import shutil
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field

from google.adk import Agent, Workflow, Context
from google.adk.workflow import JoinNode, START, Edge, node, Node
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from google.genai import types


def strip_markdown_code(code: str) -> str:
    """
    Utility parser to strip markdown backticks (```python ... ```) 
    from LLM generations, obtaining raw executable python code.
    """
    code = code.strip()
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        return match.group(1).strip()
    return code.strip()


# =====================================================================
# State Context Schemas (Strict Typing & Pydantic verification)
# =====================================================================

class GatewayContext(BaseModel):
    """
    Unified state context schema representing baseline workflow states.
    
    ADK 2.0 encourages explicitly modeling workflow session states as strongly-typed Pydantic classes.
    This guarantees that:
    1. Schema validation happens automatically at node boundaries.
    2. Undefined states or typos in keys are caught early during development.
    3. LLM agent outputs can be safely mapped directly into fields.
    """
    raw_payload: str = ""
    detected_language: str = "UNKNOWN"
    modernized_code: str = ""
    parsed_structures: str = ""
    extracted_logic: str = ""
    security_review: str = ""
    performance_review: str = ""
    review_history: List[Dict[str, Any]] = Field(default_factory=list)
    security_approved: bool = False
    performance_approved: bool = False
    consensus_iterations: int = 0
    iteration_count: int = 0
    test_passed: bool = False
    feedback: str = ""
    hypotheses_summary: List[str] = Field(default_factory=list)
    pruned_hypotheses: str = ""
    latest_traceback: str = ""


class EnhancedGatewayContext(GatewayContext):
    """
    Advanced state context inheriting from GatewayContext (DRY compliance).
    
    By inheriting from GatewayContext, we avoid repeating fields like `raw_payload` or `iteration_count`.
    This maintains a clean and maintainable inheritance chain while equipping advanced graphs
    with fields for multi-file dependencies, semantic routing choice flags, and Red/Blue pentesting parameters.
    """
    dependency_map: str = ""
    
    # Original target source contents loaded during initialization
    db_helper: str = ""
    user_dao: str = ""
    admin_service_code: str = ""
    
    # Modernized source outputs written during execution steps
    modernized_db_helper: str = ""
    modernized_user_dao: str = ""
    modernized_admin_service: str = ""
    
    # Semantic Router choice
    routed_flow: str = "UNKNOWN"
    
    # SQLi Game Loop states
    sqli_vulnerable_code: str = ""
    sqli_secured_code: str = ""
    sqli_exploit_payload: str = ""
    sqli_exploit_success: bool = False
    sqli_feedback: str = ""
    sqli_iteration_count: int = 0
    sqli_defense_passed: bool = False


# =====================================================================
# Case Study 1 (Standalone) & Case Study 3 (Sub-workflow): Python Migration Loop
# =====================================================================

# 1. Agent Declaration
# We configure RefactorAgent with explicit instructions to resolve common 
# Python 2-to-3 syntactic and semantic traps. The output is mapped into the 
# state dictionary under 'modernized_code'.
refactor_agent = Agent(
    name="RefactorAgent",
    model="gemini-3.5-flash",
    instruction=(
        "You are a code migration agent. Convert the legacy Python 2.7 code to clean, standard Python 3.\n"
        "Ensure the modernized code matches the behavior of the original implementation.\n\n"
        "CRITICAL: Output ONLY valid Python code block wrapped in ```python ... ```."
    ),
    output_key="modernized_code"
)


# 2. Dynamic Verification Node
# This node demonstrates "Dynamic workflows" using code-based logic to evaluate outputs.
# It implements the harness verification step of the Harness.
# It compiles the generated code, runs tests in a sandboxed subprocess, and loops back to RefactorAgent if the tests fail.
@node
def execution_test_node(ctx: Context) -> Event:
    """
    Dynamic Workflow validation node.
    
    1. Saves the modernized code to a temporary, session-isolated sandbox folder.
    2. Runs pytest in a subprocess to isolate exceptions and avoid polluting parent memory.
    3. If tests fail, packages the traceback feedback as a new user message turn and 
       returns a 'loop_back' event to route execution back to the agent for self-correction.
    """
    # Initialize or increment loop iterations safely using safe default getter
    ctx.state["iteration_count"] = ctx.state.get("iteration_count", 0) + 1
    modernized_code = strip_markdown_code(ctx.state.get("modernized_code", ""))
    
    # Establish a temporary sandbox directory unique to this session execution.
    # This prevents parallel runs from overwriting each other's target code.
    session_dir = os.path.join(tempfile.gettempdir(), f"adk_{ctx.session.id}")
    os.makedirs(session_dir, exist_ok=True)
    
    target_file = os.path.join(session_dir, "legacy_analytics.py")
    with open(target_file, "w") as f:
        f.write(modernized_code)
        
    env = os.environ.copy()
    env["TARGETS_DIR"] = session_dir
    pytest_path = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
    res = subprocess.run([pytest_path, "tests/test_harness.py"], capture_output=True, text=True, env=env)
    
    # If the tests pass, route execution to the end of the branch
    if res.returncode == 0:
        ctx.state["test_passed"] = True
        return Event(actions=EventActions(route="END"))
    else:
        feedback = res.stderr or res.stdout
        ctx.state["feedback"] = feedback
        
        # Guardrail: Prevent infinite routing loops
        if ctx.state.get("iteration_count", 0) >= 10:
            print("  [WARN] Loop workflow exceeded max iteration count (10). Ending branch.")
            return Event(actions=EventActions(route="END"))
            
        # Return a user message containing the error feedback and route back to the agent.
        # Capturing stdout/stderr and feeding it back as an assistant context update
        # forces the LLM to analyze its compilation errors during its next turn.
        feedback_msg = (
            f"The unit tests failed with the following traceback/logs:\n\n{feedback}\n\n"
            "Please fix the code in legacy_analytics.py to resolve the error."
        )
        return Event(
            content=types.Content(role="user", parts=[types.Part(text=feedback_msg)]),
            actions=EventActions(route="loop_back")
        )
 
 
class StatePrunerNode(Node):
    """
    StatePrunerNode intercepts active session state and events history:
    - Extracts active chat/execution history array.
    - Summarizes previous intermediate model runs into high-level structural notes.
    - Truncates and purges historical, redundant stderr tracebacks from previous iterations.
    - Re-injects the pruned history, the summarized logs, and the single latest active traceback back into the ADK session.
    """
    
    async def run_node_impl(self, *, ctx: Context, node_input: Any) -> AsyncGenerator[Any, None]:
        events = ctx.session.events
        
        # 1. Extract intermediate model runs
        refactor_events = [e for e in events if e.author == "RefactorAgent"]
        
        # 2. Compile/summarize previous trials if we haven't summarized them yet
        hypotheses = ctx.state.setdefault("hypotheses_summary", [])
        
        if len(refactor_events) > len(hypotheses):
            latest_code = strip_markdown_code(refactor_events[-1].content.parts[0].text)
            original_code = ctx.state.get("raw_payload", "")
            
            if len(refactor_events) > 1:
                prev_code = strip_markdown_code(refactor_events[-2].content.parts[0].text)
            else:
                prev_code = original_code
                
            from google.genai import Client
            client = Client()
            
            prompt = (
                "Compare the original/previous code with the proposed corrected code. "
                "Summarize the main correction or hypothesis attempted in a short, single-sentence phrase "
                "(e.g., 'Attempted print parentheses fix' or 'Attempted floor division conversion').\n\n"
                f"Before:\n{prev_code}\n\n"
                f"After:\n{latest_code}\n\n"
                "Summary of change:"
            )
            
            try:
                response = client.models.generate_content(
                    model="gemini-3.5-flash",
                    contents=prompt
                )
                hyp_text = response.text.strip()
            except Exception as e:
                hyp_text = f"Code modification (Error summarizing: {e})"
                
            hypotheses.append(f"Trial {len(hypotheses) + 1}: {hyp_text} -> Failed")
            
        # 3. Extract the latest active traceback
        latest_traceback = ctx.state.get("feedback", "")
        
        # 4. Re-inject pruned state values
        ctx.state["pruned_hypotheses"] = "\n".join(hypotheses)
        ctx.state["latest_traceback"] = latest_traceback
        
        # 5. Mutate the events to clear the intermediate chat history
        # Keep only the very first user prompt
        first_event = events[0]
        events.clear()
        events.append(first_event)
        
        # 6. Yield the pruned, summarized feedback message
        original_code = ctx.state.get("raw_payload", "")
        current_code = ctx.state.get("modernized_code", "")
        if not current_code:
            current_code = original_code
            
        pruned_feedback_msg = (
            "The unit tests failed on the current code state.\n\n"
            "### Current Code State:\n"
            "```python\n"
            f"{current_code}\n"
            "```\n\n"
            "### Active Traceback/Error:\n"
            "```\n"
            f"{latest_traceback}\n"
            "```\n\n"
            "### Previously Tried Hypotheses:\n"
            f"{ctx.state['pruned_hypotheses']}\n\n"
            "Please fix the code in legacy_analytics.py to resolve the error."
        )
        
        yield Event(
            content=types.Content(role="user", parts=[types.Part(text=pruned_feedback_msg)]),
            actions=EventActions(route="proceed")
        )

state_pruner_node = StatePrunerNode(name="StatePruner")


# 3. Compile Standalone Case Study 1 Graph Workflow
# Models a cyclic workflow where execution branches depending on node results.
# The graph utilizes a loop-back edge to route execution programmatically.
loop_flow = Workflow(
    name="loop_flow",
    edges=[
        Edge(from_node=START, to_node=refactor_agent),
        Edge(from_node=refactor_agent, to_node=execution_test_node),
        Edge(from_node=execution_test_node, to_node=state_pruner_node, route="loop_back"),
        Edge(from_node=state_pruner_node, to_node=refactor_agent, route="proceed")
    ]
)
loop_flow.state_schema = GatewayContext


# =====================================================================
# Case Study 2 (Standalone) & Case Study 3 (Sub-workflow): COBOL Modernization Loop
# =====================================================================

# 1. Parallel Agent Declarations
# These agents demonstrate "Graph-based workflows". Because they are independent, 
# the runner executes them in parallel (concurrently fanning out) once START is triggered.
structure_parser_agent = Agent(
    name="StructureParserAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Parse the DATA DIVISION of the COBOL code provided in the state's `raw_payload` field.\n"
        "Generate a clean Pydantic BaseModel to map COBOL variables. Output only the single primary record BaseModel class representing the structure.\n"
        "Do NOT generate any outer wrapper classes or nested container schemas.\n"
        "Convert COBOL COMP-3 packed decimals to python's decimal.Decimal.\n"
        "CRITICAL: Output ONLY valid Python code block wrapped in ```python ... ```."
    ),
    output_key="parsed_structures"
)

logic_extractor_agent = Agent(
    name="LogicExtractorAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Parse the PROCEDURE DIVISION of the COBOL code provided in the state's `raw_payload` field.\n"
        "Convert procedural logic into Python functions using decimal.Decimal. The logic function should accept the generated Pydantic BaseModel representation of the record as its input.\n"
        "CRITICAL: Output ONLY valid Python code block wrapped in ```python ... ```."
    ),
    output_key="extracted_logic"
)

# 2. Join Node
# Fanning back in: Wait for BOTH StructureParserAgent and LogicExtractorAgent to finish.
# JoinNode acts as a synchronization barrier, blocking execution until all incoming fanned-out
# branches write their respective outputs into the shared state schema.
join_node = JoinNode(name="join_node")

synthesis_agent = Agent(
    name="SynthesisAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Combine the Pydantic models (parsed_structures) and mathematical logic functions (extracted_logic) into a single modern Python module. Ensure the logic function accepts the primary Pydantic BaseModel instance as its argument. Include all imports at the top.\n"
        "CRITICAL: Do NOT generate any wrapper container classes or nested structures (such as AccountCalcWorkingStorage). Output ONLY the primary record-based BaseModel class and its logic function.\n"
        "CRITICAL: Output ONLY valid Python code block wrapped in ```python ... ```."
    ),
    output_key="modernized_code"
)


# 3. Compile Standalone Case Study 2: Fan-out and Fan-in Parallel Workflow
# Demonstrates ADK 2.0 Graph-based concurrency:
# 1. Start triggers BOTH structure parser and logic extractor concurrently (Fan-out).
# 2. Both nodes execute in parallel to prevent monolithic context overload.
# 3. JoinNode synchronizes the results, fanning back in.
# 4. SynthesisAgent merges the structured representations into a unified module.
cobol_flow = Workflow(
    name="cobol_flow",
    edges=[
        Edge(from_node=START, to_node=structure_parser_agent),
        Edge(from_node=START, to_node=logic_extractor_agent),
        Edge(from_node=structure_parser_agent, to_node=join_node),
        Edge(from_node=logic_extractor_agent, to_node=join_node),
        Edge(from_node=join_node, to_node=synthesis_agent)
    ]
)
cobol_flow.state_schema = GatewayContext


# =====================================================================
# Case Study 3: Enterprise Gateway & Consensus Board (Collaborative Workflows)
# =====================================================================

# 1. Router Node
# Categorizes incoming payload and forwards execution to python or cobol sub-workflows,
# demonstrating code-based Dynamic Routing.
@node
def language_router_node(ctx: Context) -> Event:
    """
    Dynamic routing node. Classifies input payload and routes 
    execution to python or cobol sub-workflows.
    """
    code = ctx.state.get("raw_payload", "").strip()
    if "IDENTIFICATION DIVISION" in code or "PROGRAM-ID" in code:
        ctx.state["detected_language"] = "COBOL"
        return Event(actions=EventActions(route="route_to_cobol_subgraph"))
    elif "print " in code or "urllib2" in code or "Legacy log processing" in code or "process_historical_logs" in code:
        ctx.state["detected_language"] = "PYTHON_2"
        return Event(actions=EventActions(route="route_to_python_subgraph"))
    else:
        ctx.state["detected_language"] = "UNSUPPORTED"
        return Event(actions=EventActions(route="route_to_terminal_failure"))


# 2. Collaborative Review Agents
# These agents run concurrently to perform independent verification checks.
security_auditor = Agent(
    name="SecurityAuditor",
    model="gemini-3.5-flash",
    instruction=(
        "Review modernized_code for vulnerabilities. If approved, output 'SECURITY_APPROVED'.\n"
        "Otherwise, specify concrete corrections targeting your peers."
    ),
    output_key="security_review"
)

performance_engineer = Agent(
    name="PerformanceEngineer",
    model="gemini-3.5-flash",
    instruction=(
        "Review modernized_code for typing, algorithmic, and decimal math efficiency.\n"
        "If approved, output 'PERFORMANCE_APPROVED'. Otherwise, specify concrete critiques."
    ),
    output_key="performance_review"
)

consensus_join = JoinNode(name="consensus_join")


# 3. Consensus Verification Gate
# This node enforces "Collaborative workflows". It inspects peer review comments 
# and loops back to debate if both roles do not explicitly approve the source.
@node
def evaluation_consensus_edge(ctx: Context, node_input: dict[str, Any]) -> Event:
    """
    Collaborative Workflow gate. Ensures both review roles approve 
    the modernization output before exiting the debate loop.
    """
    security_output = node_input.get("SecurityAuditor", "")
    performance_output = node_input.get("PerformanceEngineer", "")
    
    review_history = ctx.state.setdefault("review_history", [])
    review_history.append({
        "SecurityAuditor": security_output,
        "PerformanceEngineer": performance_output
    })
    
    security_approved = "SECURITY_APPROVED" in security_output
    performance_approved = "PERFORMANCE_APPROVED" in performance_output
    
    # Consensus board succeeds: route to END
    if security_approved and performance_approved:
        ctx.state["security_approved"] = True
        ctx.state["performance_approved"] = True
        return Event(actions=EventActions(route="END_WORKFLOW_SUCCESS"))
        
    consensus_iterations = ctx.state.setdefault("consensus_iterations", 0)
    if consensus_iterations >= 10:
        return Event(actions=EventActions(route="ROUTE_TO_HUMAN_EXCEPT"))
        
    ctx.state["consensus_iterations"] = consensus_iterations + 1
    
    # Consensus board fails: request corrections and route back to peer reviewers
    feedback_msg = (
        f"Consensus review feedback (Iteration {consensus_iterations}):\n"
        f"Security Auditor feedback: {security_output}\n"
        f"Performance Engineer feedback: {performance_output}\n"
        "Please update the modernized code accordingly."
    )
    return Event(
        content=types.Content(role="user", parts=[types.Part(text=feedback_msg)]),
        actions=EventActions(route="CONTINUE_BOARD_DEBATE")
    )


consensus_refactor_agent = Agent(
    name="ConsensusRefactorAgent",
    model="gemini-3.5-flash",
    instruction=(
        "You are a code refactoring agent. Review the current `modernized_code` and the feedback/critiques "
        "provided by your peers (SecurityAuditor and PerformanceEngineer) in the user message or the state.\n"
        "Refactor and update the `modernized_code` to fully resolve all identified security vulnerabilities "
        "and performance bottlenecks. Ensure the behavior remains identical to the original implementation.\n\n"
        "CRITICAL: Output ONLY valid Python code block wrapped in ```python ... ```."
    ),
    output_key="modernized_code"
)


# Compile Case Study 3 Collaborative Consensus Workflow
gateway_flow = Workflow(
    name="gateway_flow",
    edges=[
        Edge(from_node=START, to_node=language_router_node),
        Edge(from_node=language_router_node, to_node=loop_flow, route="route_to_python_subgraph"),
        Edge(from_node=language_router_node, to_node=cobol_flow, route="route_to_cobol_subgraph"),
        Edge(from_node=loop_flow, to_node=security_auditor),
        Edge(from_node=loop_flow, to_node=performance_engineer),
        Edge(from_node=cobol_flow, to_node=security_auditor),
        Edge(from_node=cobol_flow, to_node=performance_engineer),
        Edge(from_node=security_auditor, to_node=consensus_join),
        Edge(from_node=performance_engineer, to_node=consensus_join),
        Edge(from_node=consensus_join, to_node=evaluation_consensus_edge),
        Edge(from_node=evaluation_consensus_edge, to_node=consensus_refactor_agent, route="CONTINUE_BOARD_DEBATE"),
        Edge(from_node=consensus_refactor_agent, to_node=security_auditor),
        Edge(from_node=consensus_refactor_agent, to_node=performance_engineer)
    ]
)
gateway_flow.state_schema = GatewayContext


# =====================================================================
# Case Study 4: Multi-File Dependency Refactoring (Graph-based Parallel)
# =====================================================================

# 1. Dependency Mapping Agent
# This agent parses import hierarchies so that the refactoring graph knows 
# which modules import db_helper.py.
dependency_analyzer_agent = Agent(
    name="DependencyAnalyzerAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Analyze import relations of the provided files: `db_helper`, `user_dao`, `admin_service_code`.\n"
        "Output a structured JSON map outlining dependencies inside a ```json ... ``` block."
    ),
    output_key="dependency_map"
)

# 2. Parallel Downstream Refactoring Agents
# Once dependencies are mapped, these three agents execute in parallel.
# They modernize db_helper and propagate signature updates to user_dao and admin_service concurrently.
refactor_db_agent = Agent(
    name="RefactorDBAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Review `db_helper` in the state.\n"
        "Refactor `get_connection` signature to require host, port, user, and password parameters: "
        "def get_connection(db_name, host='localhost', port=3306, user='root', password=''): ...\n"
        "CRITICAL: Output ONLY the modernized, raw code content of the module. Do NOT output Python file-writing scripts, file-overwriting commands, or system/shell scripts. Output must be valid Python code block wrapped in ```python ... ```."
    ),
    output_key="modernized_db_helper"
)

refactor_user_agent = Agent(
    name="RefactorUserAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Review `user_dao` in the state.\n"
        "We refactored `get_connection` in `db_helper.py` to require host, port, user, and password.\n"
        "Update `get_user_profile` usage of `get_connection` to pass valid connection credentials.\n"
        "CRITICAL: Output ONLY the modernized, raw code content of the module. Do NOT output Python file-writing scripts, file-overwriting commands, or system/shell scripts. Output must be valid Python code block wrapped in ```python ... ```."
    ),
    output_key="modernized_user_dao"
)

refactor_admin_agent = Agent(
    name="RefactorAdminAgent",
    model="gemini-3.5-flash",
    instruction=(
        "Review `admin_service_code` in the state.\n"
        "We refactored `get_connection` in `db_helper.py` to require host, port, user, and password.\n"
        "Update `run_maintenance` usage of `get_connection` to pass valid connection credentials.\n"
        "CRITICAL: Output ONLY the modernized, raw code content of the module. Do NOT output Python file-writing scripts, file-overwriting commands, or system/shell scripts. Output must be valid Python code block wrapped in ```python ... ```."
    ),
    output_key="modernized_admin_service"
)

# 3. Parallel Join Gate
# Fans-in all concurrent branches before running unit tests.
multi_file_join = JoinNode(name="multi_file_join")


@node
def multi_file_test_node(ctx: Context) -> Event:
    """
    Graph-based validation node running tests after fanning back in 
    from parallel code refactoring nodes.
    """
    ctx.state["iteration_count"] = ctx.state.get("iteration_count", 0) + 1
    
    modern_db = strip_markdown_code(ctx.state.get("modernized_db_helper", ""))
    modern_user = strip_markdown_code(ctx.state.get("modernized_user_dao", ""))
    modern_admin = strip_markdown_code(ctx.state.get("modernized_admin_service", ""))
    
    # Save all refactored modules to a temporary session folder to isolate executions
    session_dir = os.path.join(tempfile.gettempdir(), f"adk_{ctx.session.id}")
    os.makedirs(session_dir, exist_ok=True)
    
    if os.path.exists("targets"):
        for filename in os.listdir("targets"):
            src_file = os.path.join("targets", filename)
            if os.path.isfile(src_file):
                shutil.copy(src_file, session_dir)
                
    with open(os.path.join(session_dir, "db_helper.py"), "w") as f:
        f.write(modern_db)
    with open(os.path.join(session_dir, "user_dao.py"), "w") as f:
        f.write(modern_user)
    with open(os.path.join(session_dir, "admin_service.py"), "w") as f:
        f.write(modern_admin)
        
    env = os.environ.copy()
    env["PYTHONPATH"] = session_dir
    env["TARGETS_DIR"] = session_dir
    pytest_path = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
    res = subprocess.run([pytest_path, "tests/test_db_migration.py"], capture_output=True, text=True, env=env)
    
    if res.returncode == 0:
        ctx.state["test_passed"] = True
        return Event(actions=EventActions(route="END"))
    else:
        feedback = res.stderr or res.stdout
        ctx.state["feedback"] = feedback
        
        if ctx.state.get("iteration_count", 0) >= 10:
            print("  [WARN] Multi-file refactoring loop exceeded max iteration count (10). Ending branch.")
            return Event(actions=EventActions(route="END"))
            
        feedback_msg = (
            f"The unit tests failed with the following traceback/logs:\n\n{feedback}\n\n"
            "Please fix the code in db_helper.py, user_dao.py, and admin_service.py to resolve the error."
        )
        return Event(
            content=types.Content(role="user", parts=[types.Part(text=feedback_msg)]),
            actions=EventActions(route="loop_back")
        )


# Compile Case Study 4 Graph-based Parallel Flow
multi_file_flow = Workflow(
    name="multi_file_flow",
    edges=[
        Edge(from_node=START, to_node=dependency_analyzer_agent),
        Edge(from_node=dependency_analyzer_agent, to_node=refactor_db_agent),
        Edge(from_node=dependency_analyzer_agent, to_node=refactor_user_agent),
        Edge(from_node=dependency_analyzer_agent, to_node=refactor_admin_agent),
        Edge(from_node=refactor_db_agent, to_node=multi_file_join),
        Edge(from_node=refactor_user_agent, to_node=multi_file_join),
        Edge(from_node=refactor_admin_agent, to_node=multi_file_join),
        Edge(from_node=multi_file_join, to_node=multi_file_test_node),
        Edge(from_node=multi_file_test_node, to_node=refactor_db_agent, route="loop_back"),
        Edge(from_node=multi_file_test_node, to_node=refactor_user_agent, route="loop_back"),
        Edge(from_node=multi_file_test_node, to_node=refactor_admin_agent, route="loop_back")
    ]
)
multi_file_flow.state_schema = EnhancedGatewayContext


# =====================================================================
# Case Study 5: Adversarial SQLi Red/Blue Debate (Collaborative Workflows)
# =====================================================================

# 1. Blue Team (Fixer Agent)
# Instructed to secure the code using safe parameterized queries and column allowlists.
sqli_fixer_agent = Agent(
    name="SQLiFixerAgent",
    model="gemini-3.5-flash",
    instruction=(
        "You are a secure coding agent (Blue Team). Your goal is to secure `sqli_vulnerable_code` against SQLi.\n"
        "Keep function signatures, arguments, and return types matching the legacy code.\n\n"
        "CRITICAL: Output ONLY valid Python code block wrapped in ```python ... ```."
    ),
    output_key="sqli_secured_code"
)

# 2. Red Team (Exploiter Agent)
# Analyzes the Blue Team's code output and attempts to generate a SQL injection bypass payload.
sqli_exploiter_agent = Agent(
    name="SQLiExploiterAgent",
    model="gemini-3.5-flash",
    instruction=(
        "You are a penetration tester (Red Team). Bypassing SQLi defenses of `sqli_secured_code`.\n"
        "Generate a malicious exploit payload string to bypass filters or extract admin secrets.\n"
        "If you cannot find any vulnerability, return the string 'normal_user'.\n\n"
        "CRITICAL: Output ONLY the raw exploit string. Do not use markdown tags."
    ),
    output_key="sqli_exploit_payload"
)


# 3. Verification Sandbox Node
# Demonstrates "Collaborative workflows" where verification runs both static tests and
# dynamic penetration testing (injecting Red Team's payload into a real database)
# before routing control. Loops back to Blue Team if the exploit succeeds.
@node
def sqli_verification_node(ctx: Context) -> Event:
    """
    Dynamic SQLi debate validation node. Runs unit tests and attempts 
    execution of the Red Team exploit payload inside a sqlite database.
    Loops back to Blue Team if exploit succeeds.
    """
    ctx.state["sqli_iteration_count"] = ctx.state.get("sqli_iteration_count", 0) + 1
    secured_code = strip_markdown_code(ctx.state.get("sqli_secured_code", ""))
    
    session_dir = os.path.join(tempfile.gettempdir(), f"adk_{ctx.session.id}")
    os.makedirs(session_dir, exist_ok=True)
    
    if os.path.exists("targets"):
        for filename in os.listdir("targets"):
            src_file = os.path.join("targets", filename)
            if os.path.isfile(src_file):
                shutil.copy(src_file, session_dir)
                
    target_file = os.path.join(session_dir, "vulnerable_query.py")
    with open(target_file, "w") as f:
        f.write(secured_code)
        
    # Validation Step A: Run static validation tests (asserting allowlists)
    env = os.environ.copy()
    env["PYTHONPATH"] = session_dir
    env["TARGETS_DIR"] = session_dir
    pytest_path = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
    res = subprocess.run([pytest_path, "tests/test_sqli_defense.py"], capture_output=True, text=True, env=env)
    
    if res.returncode != 0:
        feedback = res.stderr or res.stdout
        ctx.state["sqli_feedback"] = f"Static test suite failed:\n{feedback}"
        
        if ctx.state.get("sqli_iteration_count", 0) >= 10:
            print("  [WARN] SQLi defense loop exceeded max iterations (10). Ending branch.")
            return Event(actions=EventActions(route="END"))
            
        feedback_msg = (
            f"Vulnerabilities were still detected by the static tests:\n\n{feedback}\n\n"
            "Please fix the code in vulnerable_query.py to prevent injection."
        )
        return Event(
            content=types.Content(role="user", parts=[types.Part(text=feedback_msg)]),
            actions=EventActions(route="loop_back")
        )
        
    # Validation Step B: Run dynamic exploit payload generated by the Adversarial Agent (Red Team)
    custom_payload = ctx.state.get("sqli_exploit_payload", "").strip()
    if custom_payload and custom_payload != "normal_user":
        escaped_payload = custom_payload.replace("'", "\\'")
        db_file = os.path.join(session_dir, "test_users.db")
        python_path = ".venv/bin/python" if os.path.exists(".venv/bin/python") else "python"
        cmd = [
            python_path, "-c",
            f"import sqlite3; "
            f"conn=sqlite3.connect('{db_file}'); "
            f"cursor=conn.cursor(); "
            f"cursor.execute('DROP TABLE IF EXISTS users'); "
            f"cursor.execute('CREATE TABLE users (username TEXT, profile TEXT)'); "
            f"cursor.execute(\"INSERT INTO users VALUES ('alice', 'Alice profile data')\"); "
            f"conn.commit(); conn.close(); "
            f"from vulnerable_query import search_user; "
            f"res=search_user('{db_file}', '{escaped_payload}'); "
            f"print('LEN:', len(res))"
        ]
        res2 = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        # If the exploit succeeded in reading data, loop back to the fixer agent
        if "LEN: 0" not in res2.stdout and "LEN: 0" not in res2.stderr:
            feedback = f"Exploiter succeeded with custom payload '{custom_payload}'. Results returned: {res2.stdout or res2.stderr}"
            ctx.state["sqli_feedback"] = feedback
            ctx.state["sqli_exploit_success"] = True
            
            if ctx.state.get("sqli_iteration_count", 0) >= 10:
                print("  [WARN] SQLi defense loop exceeded max iterations (10). Ending branch.")
                return Event(actions=EventActions(route="END"))
                
            feedback_msg = (
                f"Adversarial Exploiter bypassed your defenses with payload '{custom_payload}'!\n\n"
                "Please fix the code in vulnerable_query.py to secure it against this exploit."
            )
            return Event(
                content=types.Content(role="user", parts=[types.Part(text=feedback_msg)]),
                actions=EventActions(route="loop_back")
            )
            
    ctx.state["sqli_defense_passed"] = True
    return Event(actions=EventActions(route="END"))


# 4. Compile Case Study 5 Adversarial SQLi Debate Workflow
sqli_flow = Workflow(
    name="sqli_flow",
    edges=[
        Edge(from_node=START, to_node=sqli_fixer_agent),
        Edge(from_node=sqli_fixer_agent, to_node=sqli_exploiter_agent),
        Edge(from_node=sqli_exploiter_agent, to_node=sqli_verification_node),
        Edge(from_node=sqli_verification_node, to_node=sqli_fixer_agent, route="loop_back")
    ]
)
sqli_flow.state_schema = EnhancedGatewayContext


# =====================================================================
# Case Study 6: Dynamic Semantic Routing Gateway (Dynamic Workflows)
# =====================================================================

# 1. Routing Classifier Node
# Uses programmatic vertex AI calls to classify the payload without polluting chat history.
@node
def semantic_router_node(ctx: Context) -> Event:
    """
    Programmatic classification node that uses the GenAI Client directly.
    
    Architectural Pattern: History Isolation.
    Standard ADK 2.0 Agent nodes append their text completions directly as assistant turns
    in the session's shared chat history. For nested/routed workflows, this intermediate
    routing metadata pollutes the history. Downstream parser agents become confused by these
    turns and experience context drift (e.g., hallucinating generic COBOL templates).
    
    By executing the classification programmatically using the SDK client, we write the
    choice directly to `ctx.state["routed_flow"]` without writing any turns to the chat history.
    This preserves a clean history containing only the user's raw legacy code payload.
    """
    from google.genai import Client
    client = Client()
    
    raw_payload = ctx.state.get("raw_payload", "")
    
    prompt = (
        "Classify the following query/code query into exactly one of these categories:\n"
        "- `PYTHON_MIGRATION` (if single-file legacy Python 2.7 code)\n"
        "- `COBOL_MIGRATION` (if COBOL code)\n"
        "- `MULTI_FILE_REF` (if multiple database modules refactoring requested)\n"
        "- `SQLI_DEFENSE` (if dynamic query SQLi security fix requested)\n"
        "- `UNSUPPORTED` (any other queries)\n\n"
        "CRITICAL: Output ONLY the category string. Do not use markdown tags.\n\n"
        f"Input Query/Code:\n{raw_payload}"
    )
    
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt
    )
    
    choice = response.text.strip().upper()
    ctx.state["routed_flow"] = choice
    return Event(actions=EventActions(route="proceed"))


# 2. Decision Routing Node
# Programmatically inspects the agent output and returns matching Event routes.
@node
def router_edge_node(ctx: Context) -> Event:
    """
    Dynamic routing node that maps SemanticRouter classification outputs
    onto graph branch edges.
    """
    choice = ctx.state.get("routed_flow", "UNSUPPORTED").strip().upper()
    print(f"  [SemanticRouter] Routing choice determined as: {choice}")
    if "PYTHON_MIGRATION" in choice:
        return Event(actions=EventActions(route="route_to_python"))
    elif "COBOL_MIGRATION" in choice:
        return Event(actions=EventActions(route="route_to_cobol"))
    elif "MULTI_FILE_REF" in choice:
        return Event(actions=EventActions(route="route_to_multifile"))
    elif "SQLI_DEFENSE" in choice:
        return Event(actions=EventActions(route="route_to_sqli"))
    else:
        return Event(actions=EventActions(route="END"))


# 3. Compile Case Study 6 Dynamic Semantic Gateway Workflow
# Demonstrates how sub-graphs (loop_flow, cobol_flow, multi_file_flow, sqli_flow)
# are nested and executed dynamically within the gateway graph.
enhanced_gateway_flow = Workflow(
    name="enhanced_gateway_flow",
    edges=[
        Edge(from_node=START, to_node=semantic_router_node),
        Edge(from_node=semantic_router_node, to_node=router_edge_node, route="proceed"),
        Edge(from_node=router_edge_node, to_node=loop_flow, route="route_to_python"),
        Edge(from_node=router_edge_node, to_node=cobol_flow, route="route_to_cobol"),
        Edge(from_node=router_edge_node, to_node=multi_file_flow, route="route_to_multifile"),
        Edge(from_node=router_edge_node, to_node=sqli_flow, route="route_to_sqli")
    ]
)
enhanced_gateway_flow.state_schema = EnhancedGatewayContext
