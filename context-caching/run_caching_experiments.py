"""
Unified Context Caching Experiment Runner for ADK 2.0 Harness Engineering.

Executes comparative empirical benchmarks across three high-ROI multi-query workloads:
1. Multi-Target Batch Modernization (5 distinct files against 1 shared 35.9K monorepo prefix, K=5)
2. Adversarial Red/Blue Security Debate (Multi-turn SQLi debate against 36.5K OWASP spec, K=4)
3. Multi-File Dependency Graph Modernization (Cascading refactoring of 4 modules against 36.5K ORM SDK, K=4)

Outputs detailed token telemetry, cache write/read metrics, and verified empirical savings.
"""

import os
import sys
import json
import argparse
import datetime
from typing import List, Dict, Any

from .cache_manager import ContextCacheManager
from .telemetry import ContextCacheTelemetry
from .multi_target_suite import run_multi_target_benchmark, generate_enterprise_monorepo_prefix
from .adversarial_security_debate import run_adversarial_security_debate
from .multi_file_refactoring import run_multi_file_refactoring_benchmark


def print_comparison_table(results: List[ContextCacheTelemetry]):
    """Renders a detailed empirical comparison matrix to stdout with dual pure token and cost-equivalent metrics."""
    width = 175
    print("\n" + "=" * width)
    print(" " * 55 + "CONTEXT CACHING EMPIRICAL BENCHMARK MATRIX")
    print("=" * width)
    header = (
        f"{'Case Study':<22} | {'Topology / Mode':<36} | {'Iters':<5} | "
        f"{'Cache Write':<11} | {'Cached Read':<11} | {'Dynamic In':<10} | {'Billed Total':<12} | "
        f"{'Cost-Equiv':<10} | {'Net Saved':<10} | {'Saved (%)':<9} | {'Cost Saved (%)':<14} | {'Status':<6}"
    )
    print(header)
    print("-" * width)
    
    for r in results:
        status_str = "PASS" if r.functional_test_passed else "FAIL"
        cost_equiv_str = f"{r.cost_equivalent_input_tokens:,.0f}"
        print(
            f"{r.case_study:<22} | {r.topology_name:<36} | {r.execution_iterations:<5} | "
            f"{r.cache_creation_tokens:<11,} | {r.cached_read_tokens:<11,} | {r.dynamic_input_tokens:<10,} | "
            f"{r.total_billed_input_tokens:<12,} | {cost_equiv_str:<10} | {r.tokens_saved:<10,} | "
            f"{r.token_savings_pct:>8.2f}% | {r.cost_savings_pct:>13.2f}% | {status_str:<6}"
        )
    print("=" * width + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run ADK 2.0 Context Caching Experiments")
    parser.add_argument(
        "--scenario",
        choices=["all", "multi_target", "security_debate", "multi_file"],
        default="all",
        help="Target scenario to benchmark (default: all)"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Force hermetic deterministic mock mode without contacting live GEAP endpoints"
    )
    parser.add_argument(
        "--output-dir",
        default="results",
        help="Directory to store benchmark JSON results"
    )
    args = parser.parse_args()
    
    os.makedirs(args.output_dir, exist_ok=True)
    all_telemetry: List[ContextCacheTelemetry] = []
    
    # 1. Multi-Target Batch Modernization Benchmark (K=5)
    if args.scenario in ["all", "multi_target"]:
        print("\n>>> [BENCHMARK 1/3] Multi-Target Batch Modernization Suite (5 Modules, K=5)")
        static_monorepo = generate_enterprise_monorepo_prefix()
        
        # Uncached Baseline
        cm_uncached = ContextCacheManager(force_mock=args.mock)
        uncached_multi = run_multi_target_benchmark(
            use_cache=False,
            cache_manager=cm_uncached,
            static_monorepo_prefix=static_monorepo
        )
        all_telemetry.append(uncached_multi)
        
        # Context Cached Run (Calibrated against paired uncached baseline)
        cm_cached = ContextCacheManager(force_mock=args.mock)
        cached_multi = run_multi_target_benchmark(
            use_cache=True,
            cache_manager=cm_cached,
            static_monorepo_prefix=static_monorepo
        )
        cached_multi.calculate_token_savings(uncached_multi.total_billed_input_tokens)
        all_telemetry.append(cached_multi)
        
    # 2. Adversarial Red/Blue Security Debate Benchmark (K=4)
    if args.scenario in ["all", "security_debate"]:
        print("\n>>> [BENCHMARK 2/3] Adversarial SQLi Red/Blue Security Debate (K=4)")
        # Uncached Baseline
        cm_uncached = ContextCacheManager(force_mock=args.mock)
        uncached_sec, _ = run_adversarial_security_debate(
            cache_manager=cm_uncached,
            use_cache=False,
            max_turns=4
        )
        all_telemetry.append(uncached_sec)
        
        # Context Cached Run (Calibrated against paired uncached baseline)
        cm_cached = ContextCacheManager(force_mock=args.mock)
        cached_sec, _ = run_adversarial_security_debate(
            cache_manager=cm_cached,
            use_cache=True,
            max_turns=4
        )
        cached_sec.calculate_token_savings(uncached_sec.total_billed_input_tokens)
        all_telemetry.append(cached_sec)
        
    # 3. Multi-File Dependency Graph Refactoring Benchmark (K=4)
    if args.scenario in ["all", "multi_file"]:
        print("\n>>> [BENCHMARK 3/3] Multi-File Dependency Graph Modernization (4 Modules, K=4)")
        # Uncached Baseline
        cm_uncached = ContextCacheManager(force_mock=args.mock)
        uncached_mf, _ = run_multi_file_refactoring_benchmark(
            cache_manager=cm_uncached,
            use_cache=False
        )
        all_telemetry.append(uncached_mf)
        
        # Context Cached Run (Calibrated against paired uncached baseline)
        cm_cached = ContextCacheManager(force_mock=args.mock)
        cached_mf, _ = run_multi_file_refactoring_benchmark(
            cache_manager=cm_cached,
            use_cache=True
        )
        cached_mf.calculate_token_savings(uncached_mf.total_billed_input_tokens)
        all_telemetry.append(cached_mf)
        
    # Render Granular Comparison Matrix
    print_comparison_table(all_telemetry)
    
    # Save structured telemetry artifact
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(args.output_dir, f"context_caching_experiments_{timestamp}.json")
    
    dumpable_data = [t.model_dump() for t in all_telemetry]
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump(dumpable_data, fp, indent=2, default=str)
        
    print(f"[INFO] Telemetry results saved to: {output_path}")


if __name__ == "__main__":
    main()
