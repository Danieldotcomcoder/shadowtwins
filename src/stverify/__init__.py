"""Independent verifier for Shadow Twins certificates and answers (no engine imports)."""

from .core import (
    VERIFIER_VERSION,
    Puzzle,
    compare_certificate,
    evaluate_answer,
    recompute_certificate,
)

__all__ = ["VERIFIER_VERSION", "Puzzle", "compare_certificate", "evaluate_answer", "recompute_certificate"]
