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

def main():
    # Setup client
    client = Client()
    
    # Establish isolated temporary directory
    temp_dir = os.path.join(tempfile.gettempdir(), "adk_unpruned_repair")
    os.makedirs(temp_dir, exist_ok=True)
    temp_target_file = os.path.join(temp_dir, "legacy_analytics.py")
    
    # Copy original target file to temporary directory
    shutil.copy("targets/legacy_analytics.py", temp_target_file)
    print(f"[INFO] Copied targets/legacy_analytics.py to {temp_target_file}")
    
    print(">>> Starting Imperative Unpruned Repair Loop (standard chat history)...")
    max_cycles = 5
    success = False
    
    tot_input_tokens = 0
    tot_output_tokens = 0
    
    try:
        # Read initial code
        with open(temp_target_file, "r") as f:
            original_code = f.read()
            
        # Initialize standard Chat session (this stores history automatically)
        chat = client.chats.create(model="gemini-3.5-flash")
        
        # Build first prompt
        first_prompt = (
            "You are an AI developer tasked with repairing Python code to make it compatible with Python 3.\n\n"
            "Here is the code currently on disk:\n"
            "```python\n"
            f"{original_code}\n"
            "```\n\n"
            "Please fix the code to resolve any errors. Ensure the logic is fully compatible with Python 3 and matches the expected behavior.\n"
            "CRITICAL: Output ONLY the complete corrected Python code block within standard ```python ... ``` backticks. Do not include any explanations, markdown notes, or code outside the code block."
        )
        
        current_prompt = first_prompt
        
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
                
            print(f"[FAIL] Tests failed with exit code {exit_code}. Sending raw traceback to chat...")
            
            # If not the first cycle, construct follow-up message with the traceback
            if cycle > 1:
                current_prompt = (
                    "The unit tests failed again on the last code version you provided. Here is the active error/traceback:\n"
                    "```\n"
                    f"{output.strip()}\n"
                    "```\n\n"
                    "Please repair the code to resolve the error. Remember to output ONLY the code block."
                )
            
            # 2. Model Generation via Chat API
            print("[LLM] Sending message to Chat session...")
            response = chat.send_message(current_prompt)
            raw_response = response.text
            new_code = strip_markdown_code(raw_response)
            
            p_tok = response.usage_metadata.prompt_token_count or 0
            c_tok = response.usage_metadata.candidates_token_count or 0
            tot_input_tokens += p_tok
            tot_output_tokens += c_tok
            
            print(f"[Cycle Tokens] Input: {p_tok} | Output: {c_tok}")
            
            # 3. File System Sync (to temporary copy)
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
