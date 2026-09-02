"""
CLI Runner for Cloud Run Sandbox Experiments.

Usage:
  # Run live with Gemini Enterprise Agent Platform
  python -m cloud-run-sandbox.run_sandbox_experiments

  # Run offline mock mode
  python -m cloud-run-sandbox.run_sandbox_experiments --mock

  # Run security verification only
  python -m cloud-run-sandbox.run_sandbox_experiments --verify-security
"""

import argparse
import json
import os
import sys

try:
    from .repair_loop import run_modernization_repair_loop
    from .sandbox_runner import is_sandbox_available, verify_sandbox_security_isolation
except (ImportError, ValueError):
    # Ensure package directory is in sys.path when executed directly
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
    from repair_loop import run_modernization_repair_loop
    from sandbox_runner import is_sandbox_available, verify_sandbox_security_isolation


def main():
    parser = argparse.ArgumentParser(description="Cloud Run Sandbox Agent Experiments Runner")
    parser.add_argument("--mock", action="store_true", help="Run in mock/offline mode without calling LLM APIs")
    parser.add_argument("--model", type=str, default="gemini-3.5-flash", help="Model name to use for live execution")
    parser.add_argument("--verify-security", action="store_true", help="Run isolation tests (metadata & egress blocking)")
    parser.add_argument("--output-json", type=str, default="results/sandbox_telemetry.json", help="Path to save telemetry JSON")
    args = parser.parse_args()

    # Environment setup
    if not args.mock and not args.verify_security:
        if os.getenv("GOOGLE_GENAI_USE_VERTEXAI") and not os.getenv("GOOGLE_GENAI_USE_ENTERPRISE"):
            os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"
        else:
            os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = os.getenv("GOOGLE_GENAI_USE_ENTERPRISE", "true")

        if not os.getenv("GOOGLE_CLOUD_PROJECT") or not os.getenv("GOOGLE_CLOUD_LOCATION"):
            print("[WARN] GOOGLE_CLOUD_PROJECT or GOOGLE_CLOUD_LOCATION not set. Switching to --mock mode.")
            args.mock = True

    if args.verify_security:
        print("=== Verifying Cloud Run Sandbox Security Boundaries ===")
        results = verify_sandbox_security_isolation()
        print(json.dumps(results, indent=2))
        return

    # Execute repair loop
    telemetry = run_modernization_repair_loop(
        target_source_path="targets/legacy_analytics.py",
        test_harness_path="tests/test_harness.py",
        max_cycles=5,
        mock=args.mock,
        model_name=args.model,
    )

    # Save results
    os.makedirs(os.path.dirname(args.output_json), exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        f.write(telemetry.model_dump_json(indent=2))
    print(f"\n[INFO] Saved telemetry to {args.output_json}")

    if not telemetry.functional_test_passed:
        print("[ERROR] Modernization repair loop failed to pass unit tests.")
        sys.exit(1)


if __name__ == "__main__":
    main()
