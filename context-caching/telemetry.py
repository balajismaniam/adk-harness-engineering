"""
Context Caching Telemetry Models for ADK 2.0 Harness Engineering.

This module defines strongly-typed Pydantic schemas for tracking pure token-level telemetry,
cache hit rates, latency, and prefix-invariance validation across multi-agent workflows.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class CacheLifecycleEvent(BaseModel):
    """Represents a single cache lifecycle transaction (creation, reuse, eviction, invalidation)."""
    event_type: str  # 'CREATED', 'REUSED', 'EVICTED', 'INVALIDATED'
    cache_id: str
    token_count: int
    ttl_seconds: int
    timestamp_utc: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContextCacheTelemetry(BaseModel):
    """
    Structured telemetry schema measuring pure token metrics, cache hit rates,
    and efficiency for Gemini Context Caching enabled agent harnesses.
    """
    case_study: str
    topology_name: str
    cached_enabled: bool
    cache_id: Optional[str] = None
    
    # Pure Token Metrics
    raw_context_tokens: int = 0         # Total cumulative context processed across turns
    cached_read_tokens: int = 0         # Total prefix tokens retrieved from cache
    dynamic_input_tokens: int = 0       # Total new dynamic suffix tokens sent (or full prompt if uncached)
    cache_creation_tokens: int = 0      # One-time tokens to write/create cache (0 for uncached)
    total_billed_input_tokens: int = 0  # Total fresh/transmitted input tokens billed
    cost_equivalent_input_tokens: float = 0.0  # Effective tokens applying GEAP 0.25x cached read pricing
    output_tokens_generated: int = 0    # Total output tokens generated
    tokens_saved: int = 0               # Absolute input tokens saved vs uncached baseline
    token_savings_pct: float = 0.0      # Percentage of transmitted input tokens saved (0.0% for baseline)
    cost_savings_pct: float = 0.0       # Percentage of cost-equivalent tokens saved (0.0% for baseline)
    
    # Execution & Cache Metrics
    execution_iterations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    wall_clock_latency_seconds: float = 0.0
    
    # Verification Flags
    prefix_invariance_verified: bool = True
    functional_test_passed: bool = False
    error_logs: Optional[str] = None
    
    # Lifecycle Trace
    lifecycle_events: List[CacheLifecycleEvent] = Field(default_factory=list)

    def calculate_token_savings(self, uncached_baseline_billed_tokens: int) -> float:
        """
        Calculates absolute tokens saved and percentage reduction compared to uncached baseline.
        Computes both:
        1. Transmitted token reduction (physical bandwidth savings).
        2. GEAP cost-equivalent savings (applying the 0.25x cached read discount multiplier).
        
        For uncached topologies or non-positive baseline, savings is strictly 0.00%.
        """
        if not self.cached_enabled or uncached_baseline_billed_tokens <= 0:
            self.tokens_saved = 0
            self.token_savings_pct = 0.0
            self.cost_savings_pct = 0.0
            self.cost_equivalent_input_tokens = float(self.total_billed_input_tokens)
            return 0.0
            
        saved = max(0, uncached_baseline_billed_tokens - self.total_billed_input_tokens)
        pct = (saved / uncached_baseline_billed_tokens) * 100.0
        self.tokens_saved = saved
        self.token_savings_pct = round(pct, 2)
        
        # GEAP Caching Pricing Model:
        # Cache write = 1.0x, Cached read = 0.25x (75% discount), Dynamic suffix = 1.0x
        cost_equiv = (
            self.cache_creation_tokens + 
            (0.25 * self.cached_read_tokens) + 
            self.dynamic_input_tokens
        )
        self.cost_equivalent_input_tokens = round(cost_equiv, 1)
        cost_saved = max(0.0, float(uncached_baseline_billed_tokens) - cost_equiv)
        self.cost_savings_pct = round((cost_saved / float(uncached_baseline_billed_tokens)) * 100.0, 2)
        
        return self.token_savings_pct
