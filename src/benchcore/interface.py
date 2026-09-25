"""The reusable benchmark interface.

Every benchmark module implements the nine operations below and supplies its score semantics and
metadata. The suite runner, API and exports speak only this interface plus the generic
``EvaluationEnvelope``; benchmark geometry never leaks into them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from .contracts import (
    BenchmarkMetadata,
    CompletionMeta,
    EvaluationEnvelope,
    InstanceValidation,
    RenderedPrompt,
    VerificationReport,
)


class BenchmarkModule(ABC):
    benchmark_id: ClassVar[str]

    @abstractmethod
    def metadata(self) -> BenchmarkMetadata:
        """Display name, frozen versions and score semantics."""

    @abstractmethod
    def load_instance(self, data: dict[str, Any]) -> BaseModel:
        """Parse and integrity-check a stored instance document."""

    @abstractmethod
    def load_certificate(self, data: dict[str, Any]) -> BaseModel:
        """Parse a stored certificate document."""

    @abstractmethod
    def generate(self, seed: int, params: dict[str, Any] | None = None) -> BaseModel:
        """Produce one candidate instance deterministically from ``seed``."""

    @abstractmethod
    def validate_instance(self, instance: BaseModel) -> InstanceValidation:
        """Structural checks on an instance (not certification)."""

    @abstractmethod
    def render_prompt(self, instance: BaseModel) -> RenderedPrompt:
        """The exact authored text a model receives. Contains no optimum or solver hints."""

    @abstractmethod
    def parse_answer(self, raw_text: str, meta: CompletionMeta | None = None) -> BaseModel:
        """Strict, versioned parsing of a raw completion. Never repairs answers."""

    @abstractmethod
    def validate_answer(self, instance: BaseModel, parsed: BaseModel) -> BaseModel:
        """Legality checks on a parsed answer."""

    @abstractmethod
    def evaluate(
        self,
        instance: BaseModel,
        certificate: BaseModel,
        raw_text: str,
        meta: CompletionMeta | None = None,
    ) -> EvaluationEnvelope:
        """Parse, validate and score one raw completion against a certified instance."""

    @abstractmethod
    def certify(self, instance: BaseModel) -> BaseModel:
        """Exhaustive exact certification (optimum, witnesses, histogram, counts)."""

    @abstractmethod
    def independently_verify(
        self, instance: BaseModel, certificate: BaseModel
    ) -> VerificationReport:
        """Recompute the certificate with separately implemented code and compare."""

    @abstractmethod
    def build_replay(
        self,
        instance: BaseModel,
        certificate: BaseModel,
        evaluation: EvaluationEnvelope | None,
    ) -> BaseModel:
        """Deterministic replay document for inspection views."""
