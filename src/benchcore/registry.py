"""Registry of benchmark modules available to the suite runner."""

from __future__ import annotations

from collections.abc import Callable

from .contracts import SUITE_BENCHMARKS
from .interface import BenchmarkModule

_FACTORIES: dict[str, Callable[[], BenchmarkModule]] = {}
_CACHE: dict[str, BenchmarkModule] = {}


def register(benchmark_id: str, factory: Callable[[], BenchmarkModule]) -> None:
    _FACTORIES[benchmark_id] = factory


def get(benchmark_id: str) -> BenchmarkModule:
    if benchmark_id not in _CACHE:
        _ensure_builtin()
        if benchmark_id not in _FACTORIES:
            raise KeyError(f"unknown benchmark: {benchmark_id}")
        _CACHE[benchmark_id] = _FACTORIES[benchmark_id]()
    return _CACHE[benchmark_id]


def available() -> list[str]:
    _ensure_builtin()
    return sorted(_FACTORIES)


def suite_benchmarks() -> tuple[str, ...]:
    return SUITE_BENCHMARKS


def _ensure_builtin() -> None:
    if "shadow_twins" not in _FACTORIES:
        from shadowtwins.module import ShadowTwinsModule

        register("shadow_twins", ShadowTwinsModule)
