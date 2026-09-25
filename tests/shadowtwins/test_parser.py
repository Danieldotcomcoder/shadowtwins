import pytest

from benchcore.contracts import CompletionMeta, FinishReason
from shadowtwins.contracts import InvalidCategory
from shadowtwins.parser import MAX_RAW_CHARS, parse_answer

M = InvalidCategory.MALFORMED_JSON
T = InvalidCategory.INVALID_IDS_OR_TYPES


@pytest.mark.parametrize(
    "raw, remove, add",
    [
        ('{"remove":[2,7],"add":[4,9]}', [2, 7], [4, 9]),
        ('  \n{ "add" : [4, 9] ,\n "remove": [2,7] }\n ', [2, 7], [4, 9]),
        ('{"remove":[],"add":[]}', [], []),
        ('```json\n{"remove":[1],"add":[3]}\n```', [1], [3]),
        ('```\n{"remove":[1],"add":[3]}\n```', [1], [3]),
        ('```JSON\n  {"remove":[1],"add":[3]}  \n```', [1], [3]),
        ('```{"remove":[1],"add":[3]}```', [1], [3]),
        ('{"remove":[-1],"add":[99999999999999999999]}', [-1], [99999999999999999999]),
    ],
)
def test_accepts_one_object(raw, remove, add):
    out = parse_answer(raw)
    assert out.ok, out
    assert out.edit is not None
    assert out.edit.remove == remove and out.edit.add == add
    assert out.category is None


@pytest.mark.parametrize(
    "raw, category, detail",
    [
        ("", M, "empty"),
        ("   \n ", M, "empty"),
        ('Here is my answer: {"remove":[1],"add":[3]}', M, "prose_wrapped"),
        ('{"remove":[1],"add":[3]} I hope this helps', M, "trailing_content"),
        ('{"remove":[1],"add":[3]}\n{"remove":[],"add":[]}', M, "multiple_answers"),
        ('```json\n{"remove":[1],"add":[3]}\n```\n```json\n{"remove":[],"add":[]}\n```', M, "multiple_fences"),
        ('```python\n{"remove":[1],"add":[3]}\n```', M, "bad_fence_language"),
        ("```json\n[1,2]\n```", M, "fence_not_object"),
        ('{"remove":[1],"remove":[2],"add":[3]}', M, "duplicate_keys"),
        ('{"remove":[1],"add":[3]', M, "syntax_error"),
        ("{'remove':[1],'add':[3]}", M, "syntax_error"),
        ('{"remove":[NaN],"add":[3]}', M, "non_finite"),
        ('{"remove":[1]}', M, "missing_key"),
        ('{"remove":[1],"add":[3],"why":"x"}', M, "extra_key"),
        ('{"moves":[]}', M, "missing_key"),
        ('{"remove":true,"add":[3]}', T, "not_list"),
        ('{"remove":"1","add":[3]}', T, "not_list"),
        ('{"remove":[true],"add":[3]}', T, "boolean_id"),
        ('{"remove":[false],"add":[0]}', T, "boolean_id"),
        ('{"remove":[1.0],"add":[3]}', T, "non_integer_id"),
        ('{"remove":[1e0],"add":[3]}', T, "non_integer_id"),
        ('{"remove":["1"],"add":[3]}', T, "non_integer_id"),
        ('{"remove":[null],"add":[3]}', T, "non_integer_id"),
        ('{"remove":[[1]],"add":[3]}', T, "non_integer_id"),
        ('{"remove":[' + ",".join(["1"] * 65) + '],"add":[]}', T, "too_many_ids"),
    ],
)
def test_rejects_with_stable_category(raw, category, detail):
    out = parse_answer(raw)
    assert not out.ok
    assert out.edit is None
    assert out.category == category
    assert out.detail == detail


def test_top_level_array_is_not_object():
    out = parse_answer("[1, 2]")
    assert out.category == M  # starts with neither '{' nor a fence
    assert out.detail == "prose_wrapped"


def test_too_long_is_rejected_before_decoding():
    raw = '{"remove":[],"add":[]}' + " " * MAX_RAW_CHARS + "x"
    out = parse_answer(raw)
    assert out.category == M and out.detail == "too_long"


def test_deep_nesting_is_malformed_not_a_crash():
    raw = '{"remove":' + "[" * 5000 + "]" * 5000 + ',"add":[]}'
    out = parse_answer(raw)
    assert not out.ok and out.category in (M, T)


def test_truncated_when_length_limit_and_unusable():
    meta = CompletionMeta(finish_reason=FinishReason.LENGTH)
    for raw in ['{"remove":[1],"a', "", "Let me think step by step about the"]:
        out = parse_answer(raw, meta)
        assert out.category == InvalidCategory.TRUNCATED, raw


def test_complete_answer_despite_length_limit_is_usable():
    meta = CompletionMeta(finish_reason=FinishReason.LENGTH)
    out = parse_answer('{"remove":[1],"add":[3]}', meta)
    assert out.ok


def test_refusals_are_separate_from_malformed():
    assert parse_answer("I can't help with that.").category == InvalidCategory.REFUSAL
    assert parse_answer("I'm unable to solve puzzles like this.").category == InvalidCategory.REFUSAL
    meta = CompletionMeta(finish_reason=FinishReason.CONTENT_FILTER)
    assert parse_answer("", meta).category == InvalidCategory.REFUSAL
    meta = CompletionMeta(refusal="policy")
    assert parse_answer("", meta).category == InvalidCategory.REFUSAL


def test_refusal_heuristic_never_overrides_json_content():
    # Text containing '{' is judged as an attempted answer (malformed), never as a refusal.
    out = parse_answer("I can't be sure, but {\"remove\":[1],\"add\":[3]}")
    assert out.category == M
    # Hedged prose without a refusal phrase is malformed, not a refusal.
    assert parse_answer("The answer is to move cube 3.").category == M


def test_parser_version_recorded():
    assert parse_answer("{}").parser_version.startswith("st-parser-")
