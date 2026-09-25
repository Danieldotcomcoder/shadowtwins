"""Strict, versioned answer parser (``st-parser-1.0.0``).

Accepted forms (after stripping surrounding whitespace):

1. exactly one JSON object, or
2. exactly one Markdown code fence (```` ``` ```` or ```` ```json ````) whose body is exactly one
   JSON object.

The object must have exactly the keys ``remove`` and ``add`` (any order, any whitespace), each an
array of JSON integers. Anything else is rejected with a stable category and sub-code; answers are
never repaired, and no second model is ever consulted.

Rejections are categorized in this order:

* ``truncated``: the provider reported ``finish_reason = length`` and no complete answer parsed.
* ``refusal``: the provider reported a refusal/content filter, or the text contains no ``{`` at all
  and matches the versioned refusal phrase list below.
* ``malformed_json``: empty, too long, prose-wrapped, multiple answers, syntax errors, duplicate
  keys, non-finite numbers, non-object, missing or extra keys.
* ``invalid_ids_or_types``: values that are not arrays, elements that are not integers (booleans,
  floats such as ``2.0``, strings and nulls are all rejected), or oversized arrays.

ID range, duplicates and every geometric rule are checked afterwards by the evaluator.
"""

from __future__ import annotations

import json
import re
from typing import Any

from benchcore.contracts import CompletionMeta, FinishReason

from .contracts import Edit, InvalidCategory, ParseOutcome
from .versions import PARSER_VERSION

MAX_RAW_CHARS = 20_000
MAX_IDS_PER_LIST = 64

_FENCE = re.compile(r"\A```(?P<lang>[A-Za-z]*)[ \t]*(?:\r?\n)?(?P<body>.*?)\s*```\Z", re.DOTALL)
_REFUSAL = re.compile(
    r"\b(i\s+can(?:not|'t|’t)\s+(?:help|assist|comply|do|provide|answer)|"
    r"i(?:\s+am|'m|’m)\s+(?:unable|not\s+able)\s+to|"
    r"i\s+(?:won't|will\s+not)\s+(?:help|assist|comply|answer)|"
    r"(?:cannot|can't|won't)\s+(?:help|assist|comply)\s+with)\b",
    re.IGNORECASE,
)
_ALLOWED_FENCE_LANGS = {"", "json", "JSON"}


class _Reject(Exception):
    def __init__(self, category: InvalidCategory, detail: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.detail = detail
        self.message = message


class _Float:
    """Marker for JSON numbers written with a fraction or exponent (never valid IDs)."""

    def __init__(self, text: str) -> None:
        self.text = text


def _reject_constant(name: str) -> Any:
    raise _Reject(InvalidCategory.MALFORMED_JSON, "non_finite", f"non-finite number {name}")


def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _Reject(InvalidCategory.MALFORMED_JSON, "duplicate_keys",
                          f"duplicate key {key!r} makes the answer ambiguous")
        out[key] = value
    return out


_DECODER = json.JSONDecoder(
    object_pairs_hook=_pairs_hook, parse_float=_Float, parse_constant=_reject_constant
)


def _decode_single_object(text: str) -> tuple[Any, str]:
    """Decode ``text`` as exactly one JSON value with nothing but whitespace around it."""
    body = text.strip()
    try:
        value, end = _DECODER.raw_decode(body)
    except _Reject:
        raise
    except (ValueError, RecursionError) as exc:  # JSONDecodeError, int digit limits, nesting
        raise _Reject(InvalidCategory.MALFORMED_JSON, "syntax_error", f"invalid JSON: {exc}") from exc
    rest = body[end:].strip()
    if rest:
        detail = "multiple_answers" if rest.lstrip("`").lstrip().startswith("{") else "trailing_content"
        raise _Reject(InvalidCategory.MALFORMED_JSON, detail,
                      "text after the JSON object; answer must be one JSON object only")
    return value, body


def _locate(text: str) -> tuple[Any, str]:
    if text.startswith("{"):
        return _decode_single_object(text)
    if text.startswith("```"):
        if text.count("```") != 2:
            raise _Reject(InvalidCategory.MALFORMED_JSON, "multiple_fences",
                          "expected exactly one code fence")
        m = _FENCE.match(text)
        if not m:
            raise _Reject(InvalidCategory.MALFORMED_JSON, "bad_fence", "malformed code fence")
        if m.group("lang") not in _ALLOWED_FENCE_LANGS:
            raise _Reject(InvalidCategory.MALFORMED_JSON, "bad_fence_language",
                          f"code fence language {m.group('lang')!r} is not json")
        body = m.group("body").strip()
        if not body.startswith("{"):
            raise _Reject(InvalidCategory.MALFORMED_JSON, "fence_not_object",
                          "code fence does not contain a JSON object")
        return _decode_single_object(body)
    raise _Reject(InvalidCategory.MALFORMED_JSON, "prose_wrapped",
                  "answer must start with '{' or a single code fence; prose is not accepted")


def _check_ids(key: str, value: Any) -> list[int]:
    if not isinstance(value, list):
        raise _Reject(InvalidCategory.INVALID_IDS_OR_TYPES, "not_list", f"{key!r} must be an array")
    if len(value) > MAX_IDS_PER_LIST:
        raise _Reject(InvalidCategory.INVALID_IDS_OR_TYPES, "too_many_ids",
                      f"{key!r} has {len(value)} entries (max {MAX_IDS_PER_LIST})")
    out: list[int] = []
    for item in value:
        if isinstance(item, bool):
            raise _Reject(InvalidCategory.INVALID_IDS_OR_TYPES, "boolean_id",
                          f"{key!r} contains a boolean; IDs must be integers")
        if type(item) is not int:
            raise _Reject(InvalidCategory.INVALID_IDS_OR_TYPES, "non_integer_id",
                          f"{key!r} contains a non-integer value")
        out.append(item)
    return out


def _parse_strict(text: str) -> tuple[Edit, str]:
    if len(text) > MAX_RAW_CHARS:
        raise _Reject(InvalidCategory.MALFORMED_JSON, "too_long",
                      f"response longer than {MAX_RAW_CHARS} characters")
    value, json_text = _locate(text)
    if not isinstance(value, dict):
        raise _Reject(InvalidCategory.MALFORMED_JSON, "not_object", "answer must be a JSON object")
    keys = set(value)
    missing = {"remove", "add"} - keys
    if missing:
        raise _Reject(InvalidCategory.MALFORMED_JSON, "missing_key",
                      f"missing key(s): {', '.join(sorted(missing))}")
    extra = keys - {"remove", "add"}
    if extra:
        raise _Reject(InvalidCategory.MALFORMED_JSON, "extra_key",
                      f"unexpected key(s): {', '.join(sorted(extra))}")
    remove = _check_ids("remove", value["remove"])
    add = _check_ids("add", value["add"])
    return Edit(remove=remove, add=add), json_text


def parse_answer(raw: str | None, meta: CompletionMeta | None = None) -> ParseOutcome:
    meta = meta or CompletionMeta()
    text = (raw or "").strip()
    provider_refused = bool(meta.refusal) or meta.finish_reason == FinishReason.CONTENT_FILTER
    truncated = meta.finish_reason == FinishReason.LENGTH

    if text:
        try:
            edit, json_text = _parse_strict(text)
            return ParseOutcome(parser_version=PARSER_VERSION, ok=True, edit=edit, json_text=json_text)
        except _Reject as rej:
            failure = rej
    else:
        failure = _Reject(InvalidCategory.MALFORMED_JSON, "empty", "empty response")

    if truncated:
        return ParseOutcome(parser_version=PARSER_VERSION, ok=False,
                            category=InvalidCategory.TRUNCATED, detail="finish_reason_length",
                            message=f"output hit the length limit before a usable answer ({failure.detail})")
    if provider_refused:
        return ParseOutcome(parser_version=PARSER_VERSION, ok=False,
                            category=InvalidCategory.REFUSAL, detail="provider_refusal",
                            message="provider reported a refusal or content filter")
    if text and "{" not in text and _REFUSAL.search(text):
        return ParseOutcome(parser_version=PARSER_VERSION, ok=False,
                            category=InvalidCategory.REFUSAL, detail="refusal_text",
                            message="response declines the task and contains no JSON")
    return ParseOutcome(parser_version=PARSER_VERSION, ok=False, category=failure.category,
                        detail=failure.detail, message=failure.message)
