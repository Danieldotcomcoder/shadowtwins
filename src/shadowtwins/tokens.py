"""Frozen tokenizer panel for the authored-input ceiling (P2).

The ceiling is a design requirement: every authored message (all instructions, grid data and
answer-format rules) must be at most ``CEILING`` tokens under **every** tokenizer in the panel.
The panel is frozen as ``PANEL_VERSION``: each Hugging Face tokenizer is pinned to a repository
revision and the sha256 of its ``tokenizer.json``; tiktoken encodings are pinned through the
locked ``tiktoken`` version, which verifies its own BPE file hashes.

Counts are of the raw message text without special tokens or chat templates. Provider formatting
adds template tokens, and closed-model tokenizers (e.g. Anthropic, Google) are not public, so the
offline ceiling cannot guarantee identical billed usage; provider-reported usage is recorded
separately by the runner.
"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Protocol

PANEL_VERSION = "st-tokpanel-1.0.0"
CEILING = 800


@dataclass(frozen=True)
class TokenizerSpec:
    id: str
    kind: str  # "tiktoken" | "hf"
    family: str
    name: str | None = None
    repo: str | None = None
    revision: str | None = None
    sha256: str | None = None


PANEL: tuple[TokenizerSpec, ...] = (
    TokenizerSpec("openai-o200k", "tiktoken", "OpenAI GPT-4o / o-series / GPT-5 family", name="o200k_base"),
    TokenizerSpec("openai-cl100k", "tiktoken", "OpenAI GPT-4 / GPT-3.5 family", name="cl100k_base"),
    TokenizerSpec("llama-3.1", "hf", "Meta Llama 3.x", repo="NousResearch/Meta-Llama-3.1-8B-Instruct",
                  revision="d10aef7999a2b5ba950ab3974312feeedbfe0b77",
                  sha256="79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4"),
    TokenizerSpec("qwen-2.5", "hf", "Alibaba Qwen 2.5 / 3", repo="Qwen/Qwen2.5-7B-Instruct",
                  revision="a09a35458c702b33eeacc393d103063234e8bc28",
                  sha256="c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"),
    TokenizerSpec("deepseek-v3", "hf", "DeepSeek V3 / R1", repo="deepseek-ai/DeepSeek-V3",
                  revision="e815299b0bcbac849fa540c768ef21845365c9eb",
                  sha256="621ac2e32d0dba658404412318818aaa8ce8cda492e59830109d8da6b517fb41"),
    TokenizerSpec("mistral-nemo", "hf", "Mistral (Tekken)", repo="mistralai/Mistral-Nemo-Instruct-2407",
                  revision="04d8a90549d23fc6bd7f642064003592df51e9b3",
                  sha256="e11c71726323d33da7b8d6f6f269f1988931c0a52b7122bcdd8c05042974e0db"),
    TokenizerSpec("phi-3.5", "hf", "Microsoft Phi-3.5 (SentencePiece 32k)", repo="microsoft/Phi-3.5-mini-instruct",
                  revision="2fe192450127e6a83f7441aef6e3ca586c338b77",
                  sha256="9e2ae3d66819f163cdcfedba5078f3a3af8118c2712491ed60912f77886bda6f"),
)


class _Encoder(Protocol):
    def count(self, text: str) -> int: ...


def cache_dir() -> Path:
    env = os.environ.get("ST_TOKENIZER_CACHE")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / ".tokenizer-cache"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hf_file(spec: TokenizerSpec) -> Path:
    assert spec.repo and spec.revision
    path = cache_dir() / spec.id / spec.revision / "tokenizer.json"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{spec.repo}/resolve/{spec.revision}/tokenizer.json"
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
            out.write(resp.read())
        tmp.replace(path)
    if spec.sha256 is not None and _sha256(path) != spec.sha256:
        raise RuntimeError(f"tokenizer {spec.id}: sha256 mismatch for {path}")
    return path


class _Tiktoken:
    def __init__(self, name: str) -> None:
        import tiktoken

        self.enc = tiktoken.get_encoding(name)

    def count(self, text: str) -> int:
        return len(self.enc.encode(text, disallowed_special=()))


class _HF:
    def __init__(self, path: Path) -> None:
        from tokenizers import Tokenizer

        self.tok = Tokenizer.from_file(str(path))

    def count(self, text: str) -> int:
        return len(self.tok.encode(text, add_special_tokens=False).ids)


@cache
def encoder(spec: TokenizerSpec) -> _Encoder:
    if spec.kind == "tiktoken":
        assert spec.name
        return _Tiktoken(spec.name)
    return _HF(_hf_file(spec))


def count_text(text: str) -> dict[str, int]:
    return {spec.id: encoder(spec).count(text) for spec in PANEL}


def count_messages(messages: list[dict[str, str]] | list[Any]) -> dict[str, Any]:
    """Token report for one rendered prompt: per-tokenizer totals over all messages and the max."""
    texts = [m["content"] if isinstance(m, dict) else m.content for m in messages]
    per = {spec.id: sum(encoder(spec).count(t) for t in texts) for spec in PANEL}
    worst = max(per, key=lambda k: per[k])
    return {
        "panel_version": PANEL_VERSION,
        "ceiling": CEILING,
        "counts": per,
        "max": per[worst],
        "max_tokenizer": worst,
        "within_ceiling": per[worst] <= CEILING,
        "chars": sum(len(t) for t in texts),
    }


def panel_description() -> list[dict[str, Any]]:
    out = []
    for spec in PANEL:
        entry: dict[str, Any] = {"id": spec.id, "kind": spec.kind, "family": spec.family}
        if spec.kind == "tiktoken":
            import tiktoken

            entry.update(encoding=spec.name, tiktoken_version=tiktoken.__version__)
        else:
            entry.update(repo=spec.repo, revision=spec.revision, sha256=spec.sha256)
        out.append(entry)
    return out
