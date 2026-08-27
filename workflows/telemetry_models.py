from pydantic import BaseModel
from typing import Optional

class TopologyTelemetry(BaseModel):
    """
    TopologyTelemetry defines the structured Pydantic schema used to capture and report 
    high-precision metrics from different agent topologies.
    
    In multi-agent systems design, tracking absolute hardware-level metrics (such as exact token 
    usage counts and raw millisecond latencies) is preferred over tracking currency values (USD/EUR) 
    since currency prices fluctuate over time, while raw token counts remain static and comparable.
    """

    topology_name: str                 
    """The design pattern used (one of: 'Loop', 'Parallel', 'Dynamic_Gateway', 'Parallel_MultiFile', 'Dynamic_SemanticGateway', 'Adversarial_SQLiDefense')."""

    case_study: str                    
    """The code modernization scenario executed (one of: 'Python_Migration', 'COBOL_Modernization', 'Gateway_Consensus', 'Multi_File_Refactoring', 'Semantic_Routing', 'SQLi_Red_Blue_Debate')."""

    wall_clock_latency_seconds: float  
    """The total execution time from start to completion, measured in fractional seconds."""

    input_tokens_consumed: int         
    """The total prompt tokens sent to Gemini Enterprise Agent Platform (GEAP) across all agent steps in the workflow."""

    cached_tokens_consumed: int = 0
    """The total cached prompt tokens read from Gemini Enterprise Agent Platform (GEAP) across all agent steps in the workflow."""

    output_tokens_generated: int       
    """The total completion tokens returned by Gemini models in this workflow execution."""

    functional_test_passed: bool       
    """Indicates if the generated target code passed all programmatic validation unit tests."""

    execution_iterations: int          
    """The number of verification/fix iterations executed (useful for cyclic loop workflows)."""

    error_logs: Optional[str] = None   
    """Contains raw exception logs or stack traces if system execution errors occur."""

