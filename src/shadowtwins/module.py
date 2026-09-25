"""Shadow Twins implementation of the reusable benchmark interface."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any, ClassVar

from pydantic import BaseModel

from benchcore.contracts import (
    BenchmarkMetadata,
    CompletionMeta,
    EvaluationEnvelope,
    InstanceValidation,
    RenderedPrompt,
    ScoreSemantics,
    VerificationReport,
)
from benchcore.interface import BenchmarkModule

from . import evaluate as ev
from . import prompt, replay, solver
from .contracts import (
    ParseOutcome,
    ShadowTwinsCertificate,
    ShadowTwinsEvaluation,
    ShadowTwinsInstance,
    VerificationRecord,
)
from .engine import compile_instance, structural_problems
from .parser import parse_answer
from .versions import (
    BENCHMARK_ID,
    BENCHMARK_NAME,
    EVALUATOR_VERSION,
    GENERATOR_VERSION,
    PARSER_VERSION,
    PROTOCOL_VERSION,
    REPLAY_VERSION,
    RULES_VERSION,
    SOLVER_VERSION,
)


def _as_instance(x: BaseModel) -> ShadowTwinsInstance:
    if not isinstance(x, ShadowTwinsInstance):
        raise TypeError("expected a ShadowTwinsInstance")
    return x


def _as_certificate(x: BaseModel) -> ShadowTwinsCertificate:
    if not isinstance(x, ShadowTwinsCertificate):
        raise TypeError("expected a ShadowTwinsCertificate")
    return x


def envelope(evaluation: ShadowTwinsEvaluation) -> EvaluationEnvelope:
    return EvaluationEnvelope(
        benchmark_id=BENCHMARK_ID,
        instance_id=evaluation.instance_id,
        instance_hash=evaluation.instance_hash,
        valid=evaluation.valid,
        category=evaluation.category.value if evaluation.category else None,
        score=evaluation.score,
        raw_objective=evaluation.raw_objective,
        max_objective=evaluation.v_star,
        versions=evaluation.versions,
        detail=evaluation.model_dump(mode="json"),
    )


class ShadowTwinsModule(BenchmarkModule):
    benchmark_id: ClassVar[str] = BENCHMARK_ID

    def metadata(self) -> BenchmarkMetadata:
        return BenchmarkMetadata(
            benchmark_id=BENCHMARK_ID,
            display_name=BENCHMARK_NAME,
            description=(
                "Relocate up to b cubes of a 4x4x4 voxel object to change as many entrance-pair "
                "connections as possible while keeping all three orthographic silhouettes and a "
                "single face-connected solid."
            ),
            versions={
                "rules": RULES_VERSION,
                "parser": PARSER_VERSION,
                "evaluator": EVALUATOR_VERSION,
                "solver": SOLVER_VERSION,
                "protocol": PROTOCOL_VERSION,
                "generator": GENERATOR_VERSION,
                "replay": REPLAY_VERSION,
            },
            score=ScoreSemantics(
                formula="score = 100 * v(B) / v_star; invalid answers score 0",
                notes=(
                    "v(B) counts unordered entrance pairs whose empty-cell connectivity differs "
                    "from the original. v_star is the exhaustively certified maximum over all "
                    "legal edits; instances with v_star = 0 are excluded."
                ),
            ),
        )

    def load_instance(self, data: dict[str, Any]) -> ShadowTwinsInstance:
        return ShadowTwinsInstance.model_validate(data)

    def load_certificate(self, data: dict[str, Any]) -> ShadowTwinsCertificate:
        return ShadowTwinsCertificate.model_validate(data)

    def generate(self, seed: int, params: dict[str, Any] | None = None) -> ShadowTwinsInstance:
        raise NotImplementedError("instance generation is owned by P2 (shadowtwins.generator)")

    def validate_instance(self, instance: BaseModel) -> InstanceValidation:
        problems = structural_problems(_as_instance(instance))
        return InstanceValidation(ok=not problems, problems=problems)

    def render_prompt(self, instance: BaseModel) -> RenderedPrompt:
        return prompt.render_prompt(_as_instance(instance))

    def parse_answer(self, raw_text: str, meta: CompletionMeta | None = None) -> ParseOutcome:
        return parse_answer(raw_text, meta)

    def validate_answer(self, instance: BaseModel, parsed: BaseModel):
        if not isinstance(parsed, ParseOutcome) or not parsed.ok or parsed.edit is None:
            raise ValueError("validate_answer needs a successfully parsed answer")
        return ev.validate_edit(compile_instance(_as_instance(instance)), parsed.edit)

    def evaluate(
        self,
        instance: BaseModel,
        certificate: BaseModel,
        raw_text: str,
        meta: CompletionMeta | None = None,
    ) -> EvaluationEnvelope:
        inst, cert = _as_instance(instance), _as_certificate(certificate)
        if cert.core.instance_hash != inst.content_hash:
            raise ValueError("certificate does not belong to this instance")
        if not cert.core.admissible:
            raise ValueError("instance is inadmissible (v_star = 0) and cannot be scored")
        return envelope(ev.evaluate_text(inst, cert.core.v_star, raw_text, meta))

    def certify(self, instance: BaseModel) -> ShadowTwinsCertificate:
        return solver.certify(_as_instance(instance))

    def independently_verify(self, instance: BaseModel, certificate: BaseModel) -> VerificationReport:
        from stverify import compare_certificate

        inst, cert = _as_instance(instance), _as_certificate(certificate)
        t0 = time.perf_counter()
        try:
            result = compare_certificate(inst.model_dump(mode="json"), cert.model_dump(mode="json"))
        except Exception as exc:  # pragma: no cover - surfaced as an error report
            return VerificationReport(status="error", verifier_version="stverify",
                                      runtime_ms=(time.perf_counter() - t0) * 1000,
                                      mismatches=[f"{type(exc).__name__}: {exc}"])
        return VerificationReport(
            status="verified" if not result["mismatches"] else "mismatch",
            verifier_version=result["verifier_version"],
            runtime_ms=round((time.perf_counter() - t0) * 1000, 3),
            mismatches=result["mismatches"],
            recomputed=result["recomputed"],
        )

    def build_replay(
        self,
        instance: BaseModel,
        certificate: BaseModel,
        evaluation: EvaluationEnvelope | None,
    ):
        inst, cert = _as_instance(instance), _as_certificate(certificate)
        model_eval = (ShadowTwinsEvaluation.model_validate(evaluation.detail)
                      if evaluation is not None else None)
        return replay.build_replay(inst, cert, model_eval)


def attach_verification(
    cert: ShadowTwinsCertificate, report: VerificationReport
) -> ShadowTwinsCertificate:
    """Record an independent verification result on a certificate (outside the hashed core)."""
    record = VerificationRecord(
        status=report.status,
        verifier_version=report.verifier_version,
        runtime_ms=report.runtime_ms,
        mismatches=report.mismatches,
        checked_at=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    )
    return cert.model_copy(update={"independent_verification": record})
