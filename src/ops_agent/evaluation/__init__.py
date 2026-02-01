"""OpsAgent Evaluation Module.

응답 품질 평가 및 자기 수정(Self-Correcting) 시스템.

Reference: docs/evaluation-design.md
"""

from ops_agent.evaluation.evaluator import OpsAgentEvaluator
from ops_agent.evaluation.models import (
    CheckResult,
    EvalResult,
    EvalVerdict,
    ToolResult,
    ToolType,
)

__all__ = [
    "OpsAgentEvaluator",
    "CheckResult",
    "EvalResult",
    "EvalVerdict",
    "ToolResult",
    "ToolType",
]
