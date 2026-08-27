"""
Comprehensive Pytest Suite for ADK 2.0 Context Caching.

Verifies:
1. ContextCacheManager lifecycle (creation, hash reuse, TTL, extension, invalidation).
2. CachePayloadBuilder prefix invariance and prefix-breaking detection.
3. Multi-Target Batch Modernization Suite (5 distinct modules against 1 shared 35.9K monorepo cache, K=5).
4. Adversarial Red/Blue SQLi Security Debate Loop (4 turns against 36.5K OWASP spec, K=4).
5. Multi-File Dependency Graph Modernization (Cascading refactoring of 4 modules against 36.5K SDK, K=4).
6. Telemetry schema validity and token cost reduction calculations.
"""

import os
import sys
import datetime
import pytest

# Ensure workspace root is on sys.path
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

# Import context caching modules
import importlib
context_caching_pkg = importlib.import_module("context-caching")
ContextCacheManager = context_caching_pkg.ContextCacheManager
CachePayloadBuilder = context_caching_pkg.CachePayloadBuilder
CachedContentRecord = context_caching_pkg.CachedContentRecord
ContextCacheTelemetry = context_caching_pkg.ContextCacheTelemetry

multi_target_mod = importlib.import_module("context-caching.multi_target_suite")
run_multi_target_benchmark = multi_target_mod.run_multi_target_benchmark
generate_enterprise_monorepo_prefix = multi_target_mod.generate_enterprise_monorepo_prefix
execute_multi_target_sandbox = multi_target_mod.execute_multi_target_sandbox

security_mod = importlib.import_module("context-caching.adversarial_security_debate")
run_adversarial_security_debate = security_mod.run_adversarial_security_debate
execute_sqlite_security_sandbox = security_mod.execute_sqlite_security_sandbox
generate_enterprise_security_rulebook = security_mod.generate_enterprise_security_rulebook

multi_file_mod = importlib.import_module("context-caching.multi_file_refactoring")
run_multi_file_refactoring_benchmark = multi_file_mod.run_multi_file_refactoring_benchmark
execute_multi_file_integration_sandbox = multi_file_mod.execute_multi_file_integration_sandbox
generate_enterprise_orm_sdk = multi_file_mod.generate_enterprise_orm_sdk


# =====================================================================
# 1. Context Cache Manager Lifecycle Tests
# =====================================================================

def test_cache_creation_and_hash_reuse():
    """Verifies cache creation and deterministic hash-based reuse."""
    manager = ContextCacheManager(force_mock=True)
    static_content = "def helper_function(): return 42\n" * 100
    system_inst = "You are a code migration agent."
    
    # First call: Should create a new cache record
    record1 = manager.create_cache(
        static_contents=static_content,
        display_name="test_cache",
        system_instruction=system_inst,
        ttl_seconds=1800
    )
    assert record1 is not None
    assert record1.cache_id.startswith("cachedContents/adk_")
    assert record1.ttl_seconds == 1800
    assert not record1.is_expired
    assert record1.remaining_ttl_seconds > 1700
    
    # Second call with identical content: Should reuse existing active cache
    record2 = manager.get_or_create_cache(
        static_contents=static_content,
        display_name="test_cache_2",
        system_instruction=system_inst,
        ttl_seconds=1800
    )
    assert record2.cache_id == record1.cache_id
    assert record2.hit_count == 1
    
    # Check lifecycle events
    history = manager.get_lifecycle_history()
    assert len(history) >= 2
    assert history[0].event_type == "CREATED"
    assert history[1].event_type == "REUSED"


def test_cache_ttl_extension_and_invalidation():
    """Verifies TTL updates and explicit invalidation."""
    manager = ContextCacheManager(force_mock=True)
    record = manager.create_cache(
        static_contents="SELECT * FROM legacy_table;",
        display_name="sql_cache",
        ttl_seconds=600
    )
    cache_id = record.cache_id
    
    # Extend TTL
    success = manager.update_cache_ttl(cache_id, extension_seconds=7200)
    assert success is True
    updated = manager.get_cache(cache_id)
    assert updated.ttl_seconds == 7200
    assert updated.remaining_ttl_seconds > 7000
    
    # Invalidate Cache
    deleted = manager.invalidate_cache(cache_id)
    assert deleted is True
    assert manager.get_cache(cache_id) is None


# =====================================================================
# 2. Cache Payload Builder & Prefix-Breaking Prevention Tests
# =====================================================================

def test_prefix_invariance_verification():
    """
    Verifies that CachePayloadBuilder detects prefix corruption and guarantees alignment.
    """
    system_inst = "Standard Migration Instructions"
    codebase = "class LegacyClass: pass"
    rules = "Rule 1: Use Python 3 syntax."
    
    prefix, p_hash = CachePayloadBuilder.assemble_static_prefix(
        system_instruction=system_inst,
        static_codebase=codebase,
        modernization_rules=rules
    )
    assert len(p_hash) == 64
    
    # Scenario A: Valid payload appending dynamic suffix strictly at the end
    dynamic_suffix = CachePayloadBuilder.assemble_dynamic_suffix(
        iteration_index=1,
        active_traceback="TypeError: slice indices must be integers",
        previous_hypotheses=["Tried map() conversion"]
    )
    valid_payload = prefix + "\n\n" + dynamic_suffix
    assert CachePayloadBuilder.verify_prefix_invariance(prefix, valid_payload) is True
    
    # Scenario B: Prefix-breaking violation (e.g. timestamp or UUID prepended to start)
    corrupted_payload = f"Timestamp: 2026-08-19T18:00:00Z\n\n{prefix}\n\n{dynamic_suffix}"
    assert CachePayloadBuilder.verify_prefix_invariance(prefix, corrupted_payload) is False


# =====================================================================
# 3. Multi-Target Batch Modernization Tests (K=5)
# =====================================================================

def test_multi_target_batch_modernization():
    """
    Verifies multi-target batch modernization across 5 distinct modules against
    a single shared enterprise monorepo context cache.
    """
    monorepo = generate_enterprise_monorepo_prefix()
    manager = ContextCacheManager(force_mock=True)
    
    # Run Cached Mode
    cached = run_multi_target_benchmark(
        use_cache=True,
        cache_manager=manager,
        static_monorepo_prefix=monorepo
    )
    assert cached.functional_test_passed is True
    assert cached.execution_iterations == 5
    assert cached.cache_hits == 5
    assert cached.tokens_saved > 0
    assert cached.token_savings_pct > 70.0
    assert cached.cost_savings_pct > 50.0
    
    # Run Uncached Baseline
    uncached = run_multi_target_benchmark(
        use_cache=False,
        cache_manager=manager,
        static_monorepo_prefix=monorepo
    )
    assert uncached.functional_test_passed is True
    assert uncached.execution_iterations == 5
    assert uncached.tokens_saved == 0
    assert uncached.token_savings_pct == 0.0
    assert uncached.cost_savings_pct == 0.0
    
    assert cached.total_billed_input_tokens < uncached.total_billed_input_tokens
    print(f"Multi-Target Batch Savings: {cached.token_savings_pct}% ({cached.tokens_saved:,} tokens saved, {cached.cost_savings_pct}% cost saved)")


# =====================================================================
# 4. Adversarial Red/Blue Security Debate Tests (K=4)
# =====================================================================

def test_sqlite_security_sandbox_execution():
    """Verifies that the isolated SQLite sandbox detects SQLi breaches and validates parameterized queries."""
    # Vulnerable query with string formatting
    vuln_code = """import sqlite3
def search_user(db_path, username):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT profile_data FROM users WHERE username = '{username}'")
    res = [r[0] for r in cur.fetchall()]
    conn.close()
    return res
"""
    res_vuln = execute_sqlite_security_sandbox(vuln_code, exploit_payload="' OR '1'='1")
    assert res_vuln["exploit_succeeded"] is True
    assert res_vuln["is_secure"] is False
    
    # Secure parameterized query
    secure_code = """import sqlite3
def search_user(db_path, username):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT profile_data FROM users WHERE username = ?", (username,))
    res = [r[0] for r in cur.fetchall()]
    conn.close()
    return res
"""
    res_sec = execute_sqlite_security_sandbox(secure_code, exploit_payload="' OR '1'='1")
    assert res_sec["exploit_succeeded"] is False
    assert res_sec["is_secure"] is True
    assert res_sec["normal_query_passed"] is True


def test_adversarial_security_debate_end_to_end():
    """
    Verifies multi-turn Red/Blue security debate under cached mode yields high token savings.
    """
    manager = ContextCacheManager(force_mock=True)
    
    # Run Cached Mode
    cached, passed = run_adversarial_security_debate(cache_manager=manager, use_cache=True, max_turns=4)
    assert passed is True
    assert cached.execution_iterations == 4
    assert cached.cache_hits == 4
    assert cached.tokens_saved > 0
    assert cached.token_savings_pct > 65.0
    assert cached.cost_savings_pct > 45.0
    
    # Run Uncached Mode
    uncached, passed_uncached = run_adversarial_security_debate(cache_manager=manager, use_cache=False, max_turns=4)
    assert passed_uncached is True
    assert uncached.tokens_saved == 0
    assert uncached.token_savings_pct == 0.0
    assert uncached.cost_savings_pct == 0.0
    
    assert cached.total_billed_input_tokens < uncached.total_billed_input_tokens
    print(f"Security Debate Savings: {cached.token_savings_pct}% ({cached.tokens_saved:,} tokens saved, {cached.cost_savings_pct}% cost saved)")


# =====================================================================
# 5. Multi-File Dependency Graph Refactoring Tests (K=4)
# =====================================================================

def test_multi_file_integration_sandbox_execution():
    """Verifies that the integration pytest sandbox runs and passes valid multi-file refactorings."""
    files = {
        "db_helper.py": """class ConnectionPool:
    @classmethod
    def get_connection(cls, db_name, pool_size=10):
        return f"PooledConnection({db_name}, pool_size={pool_size})"
""",
        "user_dao.py": """from db_helper import ConnectionPool
def get_user_profile(db_name, username):
    conn = ConnectionPool.get_connection(db_name)
    return f"Profile for {username} via {conn}"
""",
        "admin_service.py": """from db_helper import ConnectionPool
def audit_admin_action(db_name, admin_user, action):
    conn = ConnectionPool.get_connection(db_name, pool_size=20)
    return f"Audit log for {admin_user}: {action} via {conn}"
""",
        "analytics_service.py": """from db_helper import ConnectionPool
def aggregate_metrics(db_name, metric_name):
    conn = ConnectionPool.get_connection(db_name, pool_size=5)
    return f"Aggregated metric {metric_name} via {conn}"
"""
    }
    res = execute_multi_file_integration_sandbox(files)
    assert res["passed"] is True


def test_multi_file_refactoring_end_to_end():
    """
    Verifies cascading multi-file refactoring across 4 modules yields high token savings.
    """
    manager = ContextCacheManager(force_mock=True)
    
    # Run Cached Mode
    cached, passed = run_multi_file_refactoring_benchmark(cache_manager=manager, use_cache=True)
    assert passed is True
    assert cached.execution_iterations == 4
    assert cached.cache_hits == 4
    assert cached.tokens_saved > 0
    assert cached.token_savings_pct > 65.0
    assert cached.cost_savings_pct > 45.0
    
    # Run Uncached Mode
    uncached, passed_uncached = run_multi_file_refactoring_benchmark(cache_manager=manager, use_cache=False)
    assert passed_uncached is True
    assert uncached.tokens_saved == 0
    assert uncached.token_savings_pct == 0.0
    assert uncached.cost_savings_pct == 0.0
    
    assert cached.total_billed_input_tokens < uncached.total_billed_input_tokens
    print(f"Multi-File Refactor Savings: {cached.token_savings_pct}% ({cached.tokens_saved:,} tokens saved, {cached.cost_savings_pct}% cost saved)")


# =====================================================================
# 6. Rigorous Token Math & Pricing Invariant Tests
# =====================================================================

def test_token_math_formula_invariants():
    """
    Mathematically verifies that:
    1. T_saved = (K - 1) * T_prefix (when dynamic suffixes are equal).
    2. Savings % = (K - 1) * T_prefix / (K * T_prefix + K * T_suffix) * 100%.
    3. Total billed input = T_prefix + K * T_suffix in cached mode.
    """
    for K in [2, 3, 4, 5, 10]:
        for prefix_tokens in [10000, 36000, 50000]:
            for suffix_tokens in [100, 300, 500]:
                raw_uncached = K * (prefix_tokens + suffix_tokens)
                cached_dynamic = K * suffix_tokens
                cache_creation = prefix_tokens
                cached_billed = cache_creation + cached_dynamic
                
                expected_saved = (K - 1) * prefix_tokens
                expected_pct = round((expected_saved / raw_uncached) * 100.0, 2)
                
                telemetry = ContextCacheTelemetry(
                    case_study="Synthetic_Math_Test",
                    topology_name="Synthetic_Cached",
                    cached_enabled=True,
                    raw_context_tokens=raw_uncached,
                    cache_creation_tokens=cache_creation,
                    cached_read_tokens=K * prefix_tokens,
                    dynamic_input_tokens=cached_dynamic,
                    total_billed_input_tokens=cached_billed,
                    execution_iterations=K
                )
                
                pct = telemetry.calculate_token_savings(raw_uncached)
                assert telemetry.tokens_saved == expected_saved
                assert telemetry.token_savings_pct == expected_pct
                assert pct == expected_pct


def test_geap_cost_equivalent_pricing_math():
    """
    Verifies the GEAP (Gemini Enterprise Agent Platform) 0.25x cached read pricing calculation:
    Cost Equiv = Cache Write (1.0x) + Cached Reads (0.25x) + Dynamic Suffixes (1.0x).
    Cost Savings % = (Uncached Baseline - Cost Equiv) / Uncached Baseline * 100%.
    """
    prefix = 36000
    suffix = 300
    K = 4
    
    uncached_baseline = K * (prefix + suffix)  # 4 * 36,300 = 145,200
    cache_write = prefix                       # 36,000
    cached_reads = K * prefix                  # 144,000
    dynamic_in = K * suffix                    # 1,200
    
    # Expected cost equiv = 36,000 + (0.25 * 144,000) + 1,200 = 36,000 + 36,000 + 1,200 = 73,200
    expected_cost_equiv = 36000 + (0.25 * 144000) + 1200
    expected_cost_saved = uncached_baseline - expected_cost_equiv  # 145,200 - 73,200 = 72,000
    expected_cost_pct = round((expected_cost_saved / uncached_baseline) * 100.0, 2)  # 72,000 / 145,200 = 49.59%
    
    telemetry = ContextCacheTelemetry(
        case_study="Pricing_Math_Test",
        topology_name="Context_Cached",
        cached_enabled=True,
        raw_context_tokens=uncached_baseline,
        cache_creation_tokens=cache_write,
        cached_read_tokens=cached_reads,
        dynamic_input_tokens=dynamic_in,
        total_billed_input_tokens=cache_write + dynamic_in,
        execution_iterations=K
    )
    
    telemetry.calculate_token_savings(uncached_baseline)
    assert telemetry.cost_equivalent_input_tokens == expected_cost_equiv
    assert telemetry.cost_savings_pct == expected_cost_pct
    assert telemetry.tokens_saved == (K - 1) * prefix  # 3 * 36,000 = 108,000


def test_telemetry_zero_savings_for_uncached():
    """Verifies that uncached configurations guarantee strictly 0.00% savings and 0 tokens saved."""
    telemetry = ContextCacheTelemetry(
        case_study="Uncached_Sanity_Test",
        topology_name="Uncached_Baseline",
        cached_enabled=False,
        raw_context_tokens=150000,
        cache_creation_tokens=0,
        cached_read_tokens=0,
        dynamic_input_tokens=150000,
        total_billed_input_tokens=150000,
        execution_iterations=5
    )
    
    pct = telemetry.calculate_token_savings(150000)
    assert pct == 0.0
    assert telemetry.tokens_saved == 0
    assert telemetry.token_savings_pct == 0.0
    assert telemetry.cost_savings_pct == 0.0
    assert telemetry.cost_equivalent_input_tokens == 150000.0


def test_telemetry_edge_cases():
    """Verifies behavior with K=1 (single call), zero/negative baseline, and empty strings."""
    # Scenario A: K=1 single iteration (No savings since cache creation cost equals uncached cost)
    telemetry_k1 = ContextCacheTelemetry(
        case_study="Single_Iteration_Test",
        topology_name="Single_Call_Cached",
        cached_enabled=True,
        raw_context_tokens=36500,
        cache_creation_tokens=36000,
        cached_read_tokens=36000,
        dynamic_input_tokens=500,
        total_billed_input_tokens=36500,
        execution_iterations=1
    )
    telemetry_k1.calculate_token_savings(36500)
    assert telemetry_k1.tokens_saved == 0
    assert telemetry_k1.token_savings_pct == 0.0
    
    # Scenario B: Non-positive baseline guard
    telemetry_zero = ContextCacheTelemetry(
        case_study="Zero_Baseline_Test",
        topology_name="Zero_Baseline",
        cached_enabled=True
    )
    assert telemetry_zero.calculate_token_savings(0) == 0.0
    assert telemetry_zero.calculate_token_savings(-100) == 0.0

