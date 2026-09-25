"""Frozen version identifiers for Shadow Twins semantics.

Changing any behaviour covered by one of these identifiers requires bumping it, recording a
decision entry in docs/DECISIONS.md, and updating consumers. Scores are only comparable when every
version recorded alongside them matches.
"""

BENCHMARK_ID = "shadow_twins"
BENCHMARK_NAME = "Shadow Twins"

# Rules of the task itself: geometry, legality, objective and score (docs/FORMAL_RULES.md).
RULES_VERSION = "st-rules-1.0.0"
# Answer parser behaviour (docs/FORMAL_RULES.md, "Answer parsing").
PARSER_VERSION = "st-parser-1.0.0"
# Evaluator: validity check order, categories and score arithmetic.
EVALUATOR_VERSION = "st-eval-1.0.0"
# Optimized exhaustive enumerator used for certification.
SOLVER_VERSION = "st-solver-1.0.0"
# Prompt serialization (text the model receives). Owned by P2; see shadowtwins.prompt.
PROTOCOL_VERSION = "st-protocol-1.0.0"
# Seeded instance generator and admission metrics. Owned by P2; see shadowtwins.generator.
GENERATOR_VERSION = "st-gen-1.0.0"
# Replay document layout.
REPLAY_VERSION = "st-replay-1.0.0"

MIN_BUDGET = 1
MAX_BUDGET = 3
MIN_ENTRANCES = 2
MAX_ENTRANCES = 8
