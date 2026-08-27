"""
Context Cache Manager & Payload Builder for Google ADK 2.0 & Gemini on Gemini Enterprise Agent Platform (GEAP).

This module manages the full lifecycle of GEAP Gemini Context Caches:
1. Creation, retrieval, update (TTL extension), and deletion/invalidation.
2. Deterministic cache key generation based on SHA-256 content hashes to reuse active caches.
3. Solving the "Prefix-Breaking" problem by enforcing strict separation between immutable
   static prefixes (cached) and dynamic execution variables (uncached suffixes).
4. Dual-mode execution: Native integration with GEAP's `client.caches` API when
   credentials/endpoints are active, alongside hermetic mock simulation for offline test sandboxes.
"""

import os
import hashlib
import time
import datetime
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field

from google.genai import types
from google.genai import Client

from .telemetry import CacheLifecycleEvent, ContextCacheTelemetry


class CachedContentRecord(BaseModel):
    """Represents an active or mock Gemini Enterprise Agent Platform (GEAP) CachedContent resource."""
    cache_id: str
    display_name: str
    model: str
    token_count: int
    system_instruction: Optional[str] = None
    static_contents: str
    content_hash: str
    created_at_utc: datetime.datetime
    expires_at_utc: datetime.datetime
    ttl_seconds: int
    is_mock: bool = False
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Determines if the cache has exceeded its time-to-live expiration."""
        return datetime.datetime.now(datetime.timezone.utc) >= self.expires_at_utc

    @property
    def remaining_ttl_seconds(self) -> float:
        """Returns the number of seconds remaining before cache expiration."""
        delta = self.expires_at_utc - datetime.datetime.now(datetime.timezone.utc)
        return max(0.0, delta.total_seconds())


class CachePayloadBuilder:
    """
    Constructs model payloads while strictly preventing the 'Prefix-Breaking' anti-pattern.
    
    The Prefix-Breaking Problem:
    Context caching in transformer architectures requires an exact byte-for-byte prefix match.
    If a system injects dynamic metadata (such as timestamps, UUIDs, or cycle iterations)
    at the beginning of system instructions or prompt prefixes, the cache key changes and
    GEAP is forced to re-tokenize and re-ingest the entire 100K+ token codebase at full price.
    
    CachePayloadBuilder guarantees:
    - Immutable static prefixes (system instructions, legacy codebases, rules, schemas) are placed first.
    - Dynamic mutable suffixes (tracebacks, cycle counts, timestamps) are strictly appended at the end.
    """

    @staticmethod
    def compute_sha256(text: str) -> str:
        """Calculates deterministic SHA-256 hash for prefix alignment verification."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Conservative token estimation (~4 characters per token for code/text).
        For production accuracy, use Client().models.count_tokens().
        """
        return max(1, len(text) // 4)

    @classmethod
    def assemble_static_prefix(
        cls,
        system_instruction: str,
        static_codebase: str,
        modernization_rules: str,
        reference_schemas: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Assembles and hashes the immutable static prefix.
        
        Returns:
            Tuple of (formatted_static_prefix, sha256_hash).
        """
        parts = [
            "### SYSTEM INSTRUCTION ###",
            system_instruction.strip(),
            "\n### STATIC REFERENCE CODEBASE & KNOWLEDGE BASE ###",
            static_codebase.strip(),
            "\n### MODERNIZATION & VERIFICATION RULES ###",
            modernization_rules.strip()
        ]
        if reference_schemas:
            parts.extend([
                "\n### REFERENCE SCHEMAS & DATA STRUCTURES ###",
                reference_schemas.strip()
            ])
            
        static_prefix = "\n\n".join(parts)
        prefix_hash = cls.compute_sha256(static_prefix)
        return static_prefix, prefix_hash

    @classmethod
    def assemble_dynamic_suffix(
        cls,
        iteration_index: int,
        active_traceback: Optional[str] = None,
        previous_hypotheses: Optional[List[str]] = None,
        current_target_code: Optional[str] = None,
        runtime_feedback: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """
        Assembles all mutable runtime execution elements into an appended suffix.
        """
        parts = [
            f"### DYNAMIC EXECUTION CONTEXT (Iteration: {iteration_index}) ###"
        ]
        if session_id:
            parts.append(f"Session Identifier: {session_id}")
            
        if current_target_code:
            parts.extend([
                "\n### CURRENT WORKING CODE STATE ###",
                f"```python\n{current_target_code.strip()}\n```"
            ])
            
        if active_traceback:
            parts.extend([
                "\n### ACTIVE RUNTIME ERROR / TEST TRACEBACK ###",
                f"```\n{active_traceback.strip()}\n```"
            ])
            
        if previous_hypotheses:
            hyp_list = "\n".join([f"- {h}" for h in previous_hypotheses])
            parts.extend([
                "\n### PREVIOUSLY FAILED HYPOTHESES (DO NOT REPEAT) ###",
                hyp_list
            ])
            
        if runtime_feedback:
            parts.extend([
                "\n### PEER/HARNESS FEEDBACK ###",
                runtime_feedback.strip()
            ])
            
        parts.append(
            "\nCRITICAL: Analyze the active error and previous failures. Output ONLY the updated corrected code in ```python ... ```."
        )
        return "\n\n".join(parts)

    @classmethod
    def verify_prefix_invariance(
        cls,
        expected_prefix: str,
        full_call_payload: str
    ) -> bool:
        """
        Validates that `full_call_payload` strictly begins with `expected_prefix`.
        Returns True if cache prefix alignment is intact, False if prefix was broken.
        """
        return full_call_payload.startswith(expected_prefix)


class ContextCacheManager:
    """
    Manages the lifecycle of Gemini Context Caches on Gemini Enterprise Agent Platform (GEAP) or in-memory mock.
    
    Capabilities:
    - `get_or_create_cache`: Looks up active cache by SHA-256 hash or creates a new one.
    - `extend_ttl`: Updates/refreshes expiration time on active caches.
    - `invalidate_cache`: Removes cache from registry and deletes from GEAP.
    - `generate_with_cache`: Invokes Gemini with cachedContent configuration.
    """

    def __init__(
        self,
        client: Optional[Client] = None,
        model_name: str = "gemini-3.5-flash",
        force_mock: bool = False,
        project: Optional[str] = None,
        location: Optional[str] = None
    ):
        self.model_name = model_name
        self.force_mock = force_mock
        self._local_registry: Dict[str, CachedContentRecord] = {}
        self._hash_to_cache_id: Dict[str, str] = {}
        self._lifecycle_history: List[CacheLifecycleEvent] = []
        
        # Initialize Google GenAI client if available for Gemini Enterprise Agent Platform (GEAP)
        self.client = client
        if not self.force_mock and self.client is None:
            os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "true"
            proj = project or os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
            if not proj:
                try:
                    import subprocess
                    cmd_res = subprocess.run(["gcloud", "config", "get-value", "project"], capture_output=True, text=True, timeout=5)
                    if cmd_res.returncode == 0 and cmd_res.stdout.strip():
                        proj = cmd_res.stdout.strip()
                except Exception:
                    pass
            loc = location or os.environ.get("GOOGLE_CLOUD_LOCATION") or "global"
            try:
                self.client = Client(enterprise=True, project=proj, location=loc)
                print(f"[GEAP] Connected to Gemini Enterprise Agent Platform (project='{proj or 'auto'}', location='{loc}', model='{self.model_name}')")
            except Exception as e:
                print(f"[CACHE_WARN] Could not initialize GEAP client ({e}). Falling back to mock mode.")
                self.force_mock = True

    def count_tokens(self, text: str, system_instruction: Optional[str] = None) -> int:
        """
        Calculates exact token count using GEAP client if available,
        otherwise falls back to deterministic heuristic estimation.
        """
        if not self.force_mock and self.client:
            try:
                config = None
                if system_instruction:
                    config = types.CountTokensConfig(system_instruction=system_instruction)
                resp = self.client.models.count_tokens(
                    model=self.model_name,
                    contents=text,
                    config=config
                )
                if resp and resp.total_tokens:
                    return resp.total_tokens
            except Exception:
                pass
        return CachePayloadBuilder.estimate_tokens(text + (system_instruction or ""))

    def _record_event(self, event_type: str, cache_id: str, token_count: int, ttl_seconds: int, metadata: Dict[str, Any] = None):
        event = CacheLifecycleEvent(
            event_type=event_type,
            cache_id=cache_id,
            token_count=token_count,
            ttl_seconds=ttl_seconds,
            timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            metadata=metadata or {}
        )
        self._lifecycle_history.append(event)

    def get_lifecycle_history(self) -> List[CacheLifecycleEvent]:
        """Returns the full audit trail of cache lifecycle events."""
        return list(self._lifecycle_history)

    def create_cache(
        self,
        static_contents: str,
        display_name: str = "adk_harness_cache",
        system_instruction: Optional[str] = None,
        ttl_seconds: int = 3600
    ) -> CachedContentRecord:
        """
        Explicitly creates a context cache on GEAP or local mock registry.
        """
        content_hash = CachePayloadBuilder.compute_sha256(
            (system_instruction or "") + "\n---DIV---\n" + static_contents
        )
        
        # Check if already active and not expired
        existing_id = self._hash_to_cache_id.get(content_hash)
        if existing_id and existing_id in self._local_registry:
            existing = self._local_registry[existing_id]
            if not existing.is_expired:
                existing.hit_count += 1
                self._record_event("REUSED", existing.cache_id, existing.token_count, existing.ttl_seconds)
                return existing
                
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)
        
        # Calculate tokens
        estimated_tokens = self.count_tokens(static_contents, system_instruction=system_instruction)
        actual_tokens = estimated_tokens
        
        cache_id = f"cachedContents/adk_{content_hash[:12]}"
        is_mock = self.force_mock
        
        if not self.force_mock and self.client:
            try:
                # Live GEAP Cache Creation via google-genai SDK
                ttl_str = f"{ttl_seconds}s"
                config = types.CreateCachedContentConfig(
                    display_name=display_name,
                    contents=[static_contents],
                    system_instruction=system_instruction,
                    ttl=ttl_str
                )
                created = self.client.caches.create(
                    model=self.model_name,
                    config=config
                )
                cache_id = created.name or cache_id
                if created.usage_metadata and created.usage_metadata.total_token_count:
                    actual_tokens = created.usage_metadata.total_token_count
                else:
                    actual_tokens = estimated_tokens
                is_mock = False
            except Exception as e:
                # Graceful fallback to mock mode with warning
                is_mock = True
                print(f"[CACHE_WARN] Live GEAP cache creation failed ({e}). Running in deterministic mock mode.")
                actual_tokens = estimated_tokens
                
        record = CachedContentRecord(
            cache_id=cache_id,
            display_name=display_name,
            model=self.model_name,
            token_count=actual_tokens,
            system_instruction=system_instruction,
            static_contents=static_contents,
            content_hash=content_hash,
            created_at_utc=now,
            expires_at_utc=expires_at,
            ttl_seconds=ttl_seconds,
            is_mock=is_mock,
            hit_count=0
        )
        
        self._local_registry[cache_id] = record
        self._hash_to_cache_id[content_hash] = cache_id
        self._record_event("CREATED", cache_id, actual_tokens, ttl_seconds, {"display_name": display_name, "is_mock": is_mock})
        return record

    def get_or_create_cache(
        self,
        static_contents: str,
        display_name: str = "adk_harness_cache",
        system_instruction: Optional[str] = None,
        ttl_seconds: int = 3600
    ) -> CachedContentRecord:
        """
        Retrieves active cache matching content hash or creates a new one.
        """
        content_hash = CachePayloadBuilder.compute_sha256(
            (system_instruction or "") + "\n---DIV---\n" + static_contents
        )
        existing_id = self._hash_to_cache_id.get(content_hash)
        if existing_id and existing_id in self._local_registry:
            record = self._local_registry[existing_id]
            if not record.is_expired:
                record.hit_count += 1
                self._record_event("REUSED", record.cache_id, record.token_count, record.ttl_seconds)
                return record
                
        return self.create_cache(
            static_contents=static_contents,
            display_name=display_name,
            system_instruction=system_instruction,
            ttl_seconds=ttl_seconds
        )

    def get_cache(self, cache_id: str) -> Optional[CachedContentRecord]:
        """Looks up a cache record by ID."""
        record = self._local_registry.get(cache_id)
        if record and record.is_expired:
            self.invalidate_cache(cache_id)
            return None
        return record

    def update_cache_ttl(self, cache_id: str, extension_seconds: int) -> bool:
        """
        Extends the expiration time of an active cache.
        """
        record = self.get_cache(cache_id)
        if not record:
            return False
            
        new_expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=extension_seconds)
        record.expires_at_utc = new_expires_at
        record.ttl_seconds = extension_seconds
        
        if not record.is_mock and self.client:
            try:
                ttl_str = f"{extension_seconds}s"
                self.client.caches.update(
                    name=cache_id,
                    config=types.UpdateCachedContentConfig(ttl=ttl_str)
                )
            except Exception as e:
                print(f"[CACHE_WARN] Failed to update live cache TTL: {e}")
                
        self._record_event("EXTENDED_TTL", cache_id, record.token_count, extension_seconds)
        return True

    def invalidate_cache(self, cache_id: str) -> bool:
        """
        Explicitly invalidates and deletes a cache resource.
        """
        record = self._local_registry.pop(cache_id, None)
        if not record:
            return False
            
        if record.content_hash in self._hash_to_cache_id:
            del self._hash_to_cache_id[record.content_hash]
            
        if not record.is_mock and self.client:
            try:
                self.client.caches.delete(name=cache_id)
            except Exception as e:
                print(f"[CACHE_WARN] Failed to delete live cache: {e}")
                
        self._record_event("INVALIDATED", cache_id, record.token_count, record.ttl_seconds)
        return True

    def clear_all(self):
        """Cleans up all managed caches."""
        cache_ids = list(self._local_registry.keys())
        for cid in cache_ids:
            self.invalidate_cache(cid)

    def generate_with_cache(
        self,
        cache_record: CachedContentRecord,
        dynamic_suffix: str,
        temperature: float = 0.2,
    ) -> Tuple[str, Dict[str, int]]:
        """
        Invokes Gemini with cachedContent configuration on GEAP or mock fallback.
        Returns:
            Tuple of (response_text, token_usage_dict)
        """
        if not cache_record.is_mock and self.client:
            try:
                config = types.GenerateContentConfig(
                    cached_content=cache_record.cache_id,
                    temperature=temperature
                )
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=dynamic_suffix,
                    config=config
                )
                text = response.text or ""
                total_prompt_tok = getattr(response.usage_metadata, "prompt_token_count", None)
                cached_tok = getattr(response.usage_metadata, "cached_content_token_count", 0) or 0
                
                if total_prompt_tok is not None:
                    if cached_tok > 0:
                        dynamic_prompt_tok = max(0, total_prompt_tok - cached_tok)
                        cached_read_val = cached_tok
                    else:
                        # Live cache miss (0 cached tokens returned from GEAP)
                        dynamic_prompt_tok = total_prompt_tok
                        cached_read_val = 0
                else:
                    dynamic_prompt_tok = self.count_tokens(dynamic_suffix)
                    cached_read_val = cache_record.token_count
                    
                resp_tok = getattr(response.usage_metadata, "candidates_token_count", None) or getattr(response.usage_metadata, "response_token_count", None) or CachePayloadBuilder.estimate_tokens(text)
                return text, {
                    "prompt_tokens": dynamic_prompt_tok,
                    "cached_tokens": cached_read_val,
                    "total_prompt_tokens": total_prompt_tok or (dynamic_prompt_tok + cached_read_val),
                    "response_tokens": resp_tok
                }
            except Exception as e:
                print(f"[CACHE_WARN] Live cached generation failed ({e}).")
        
        suffix_tokens = CachePayloadBuilder.estimate_tokens(dynamic_suffix)
        return "", {
            "prompt_tokens": suffix_tokens,
            "cached_tokens": cache_record.token_count,
            "total_prompt_tokens": suffix_tokens + cache_record.token_count,
            "response_tokens": 0
        }

    def generate_uncached(
        self,
        full_payload: str,
        temperature: float = 0.2,
    ) -> Tuple[str, Dict[str, int]]:
        """
        Invokes Gemini without context caching.
        Returns:
            Tuple of (response_text, token_usage_dict)
        """
        if not self.force_mock and self.client:
            try:
                config = types.GenerateContentConfig(temperature=temperature)
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=full_payload,
                    config=config
                )
                text = response.text or ""
                prompt_tok = getattr(response.usage_metadata, "prompt_token_count", None) or self.count_tokens(full_payload)
                resp_tok = getattr(response.usage_metadata, "candidates_token_count", None) or getattr(response.usage_metadata, "response_token_count", None) or CachePayloadBuilder.estimate_tokens(text)
                return text, {
                    "prompt_tokens": prompt_tok,
                    "cached_tokens": 0,
                    "total_prompt_tokens": prompt_tok,
                    "response_tokens": resp_tok
                }
            except Exception as e:
                print(f"[MODEL_WARN] Live uncached generation failed ({e}).")
                
        tokens = CachePayloadBuilder.estimate_tokens(full_payload)
        return "", {
            "prompt_tokens": tokens,
            "cached_tokens": 0,
            "total_prompt_tokens": tokens,
            "response_tokens": 0
        }
