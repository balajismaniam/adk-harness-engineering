import os
import sys
import re
import subprocess
import tempfile
import shutil
from google.genai import Client
from google.genai import types

def strip_markdown_code(code: str) -> str:
    code = code.strip()
    match = re.search(r"```python\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        return match.group(1).strip()
    match = re.search(r"```\s*(.*?)\s*```", code, re.DOTALL)
    if match:
        return match.group(1).strip()
    return code.strip()

def run_tests(temp_dir: str) -> tuple[int, str]:
    pytest_path = ".venv/bin/pytest" if os.path.exists(".venv/bin/pytest") else "pytest"
    env = os.environ.copy()
    env["TARGETS_DIR"] = temp_dir
    res = subprocess.run([pytest_path, "tests/test_harness.py"], capture_output=True, text=True, env=env)
    return res.returncode, res.stdout + "\n" + res.stderr

def generate_hypothesis_summary(client: Client, original_code: str, proposed_code: str) -> tuple[str, int, int]:
    prompt = (
        "Compare the original Python code and the proposed corrected code. "
        "Summarize the main correction or hypothesis attempted in a short, single-sentence phrase "
        "(e.g., 'Attempted print parentheses fix' or 'Attempted floor division conversion').\n\n"
        f"Original:\n{original_code}\n\n"
        f"Proposed:\n{proposed_code}\n\n"
        "Summary of change:"
    )
    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=prompt
        )
        summary = response.text.strip()
        p_tok = response.usage_metadata.prompt_token_count or 0
        c_tok = response.usage_metadata.candidates_token_count or 0
        return summary, p_tok, c_tok
    except Exception as e:
        return f"Modified code behavior (Error generating summary: {e})", 0, 0

def isolate_execution_context(current_code: str, active_traceback: str, tried_hypotheses: list[str]) -> str:
    hypotheses_str = "\n".join(f"- {h}" for h in tried_hypotheses) if tried_hypotheses else "None"
    prompt = (
        "You are an AI developer tasked with repairing Python code to make it compatible with Python 3.\n\n"
        "Here is the code currently on disk:\n"
        "```python\n"
        f"{current_code}\n"
        "```\n\n"
        "When running the unit tests, we encountered the following active error/traceback:\n"
        "```\n"
        f"{active_traceback}\n"
        "```\n\n"
        "Here is a summary of previously tried hypotheses that FAILED:\n"
        f"{hypotheses_str}\n\n"
        "Please fix the code to resolve the error. Ensure the logic is fully compatible with Python 3 and matches the expected behavior.\n"
        "CRITICAL: Output ONLY the complete corrected Python code block within standard ```python ... ``` backticks. Do not include any explanations, markdown notes, or code outside the code block."
    )
    return prompt

def main():
    # Setup client
    client = Client()
    
    # Establish isolated temporary directory
    temp_dir = os.path.join(tempfile.gettempdir(), "adk_hermetic_repair")
    os.makedirs(temp_dir, exist_ok=True)
    temp_target_file = os.path.join(temp_dir, "legacy_analytics.py")
    
    # Copy original target file to temporary directory
    shutil.copy("targets/legacy_analytics.py", temp_target_file)
    print(f"[INFO] Copied targets/legacy_analytics.py to {temp_target_file}")
    
    print(">>> Starting Imperative Hermetic Repair Loop...")
    tried_hypotheses = []
    max_cycles = 5
    success = False
    
    tot_input_tokens = 0
    tot_output_tokens = 0
    
    try:
        for cycle in range(1, max_cycles + 1):
            print(f"\n--- Cycle {cycle}/{max_cycles} ---")
            
            # 1. Deterministic Checker
            exit_code, output = run_tests(temp_dir)
            if exit_code == 0:
                print(f"[SUCCESS] Tests passed on cycle {cycle}!")
                with open(temp_target_file, "r") as f:
                    final_code = f.read()
                print(f"\n--- Repaired Code Output ---\n{final_code}\n")
                success = True
                break
                
            print(f"[FAIL] Tests failed with exit code {exit_code}. Pruning context...")
            
            # Read current code from the copy in temporary folder
            with open(temp_target_file, "r") as f:
                current_code = f.read()
                
            # Keep only the active traceback
            active_traceback = output.strip()
            
            # 2. Context Pruning
            prompt = isolate_execution_context(current_code, active_traceback, tried_hypotheses)
            
            # 3. Model Generation
            print("[LLM] Invoking gemini-3.5-flash to repair code...")
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt
            )
            raw_response = response.text
            new_code = strip_markdown_code(raw_response)
            
            p_tok = response.usage_metadata.prompt_token_count or 0
            c_tok = response.usage_metadata.candidates_token_count or 0
            tot_input_tokens += p_tok
            tot_output_tokens += c_tok
            
            # 4. Generate hypothesis summary for the tried hypothesis log
            hypothesis, hyp_p, hyp_c = generate_hypothesis_summary(client, current_code, new_code)
            tot_input_tokens += hyp_p
            tot_output_tokens += hyp_c
            
            tried_hypotheses.append(f"Trial {cycle}: {hypothesis} -> Failed")
            print(f"[State Log] Logged Attempt: {hypothesis}")
            
            # 5. File System Sync (to temporary copy)
            with open(temp_target_file, "w") as f:
                f.write(new_code)
                
        print(f"\n================ TELEMETRY SUMMARY ================")
        print(f"Total Input Tokens consumed:  {tot_input_tokens}")
        print(f"Total Output Tokens generated: {tot_output_tokens}")
        print(f"====================================================\n")
        
        if not success:
            print("[FAIL] Reached max cycles without resolving tests.")
            sys.exit(1)
            
    except Exception as e:
        print(f"[FATAL] Run exception encountered: {e}")
        sys.exit(1)
    finally:
        # Clean up temporary files
        try:
            shutil.rmtree(temp_dir)
            print(f"[INFO] Cleaned up temporary directory {temp_dir}")
        except Exception:
            pass

if __name__ == "__main__":
    main()
