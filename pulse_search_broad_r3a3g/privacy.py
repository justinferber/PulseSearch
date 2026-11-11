"""Public-only payload boundaries shared by the PUKE client and the API.

This is deliberately a schema check, not a privacy classifier. Unknown nested
fields are rejected instead of being silently forwarded, and obvious personal
identifiers are refused at both boundaries. It does not replace redaction in a
provider adapter.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
SENSITIVE_KEYS = {
    "member", "member_context", "member_id", "user_context", "user_id",
    "profile_id", "account_id", "email", "phone", "address", "session",
    "session_token", "access_token", "refresh_token", "password", "secret",
    "private", "private_context", "conversation", "messages",
}
MAX_DEPTH = 8
MAX_ITEMS = 64
MAX_TEXT = 20_000


class PrivacyError(ValueError):
    pass


def _check_scalar(value, path: str) -> None:
    if not isinstance(value, str):
        return
    if len(value) > MAX_TEXT:
        raise PrivacyError(f"{path} is too long")
    if EMAIL_RE.search(value):
        raise PrivacyError(f"{path} contains an email address")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return
    if PHONE_RE.search(value):
        raise PrivacyError(f"{path} contains a phone number")


def assert_public_value(value, path: str = "payload", depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise PrivacyError(f"{path} is nested too deeply")
    if isinstance(value, dict):
        if len(value) > MAX_ITEMS:
            raise PrivacyError(f"{path} has too many fields")
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise PrivacyError(f"{path} has an invalid field name")
            normalized = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
            if normalized in SENSITIVE_KEYS or any(
                    marker in normalized for marker in
                    ("member_context", "user_context", "session_token", "access_token")):
                raise PrivacyError(f"{path}.{key} is private context and is not accepted")
            assert_public_value(item, f"{path}.{key}", depth + 1)
    elif isinstance(value, list):
        if len(value) > MAX_ITEMS:
            raise PrivacyError(f"{path} has too many items")
        for index, item in enumerate(value):
            assert_public_value(item, f"{path}[{index}]", depth + 1)
    elif isinstance(value, tuple):
        assert_public_value(list(value), path, depth)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise PrivacyError(f"{path} has an unsupported value type")
    else:
        _check_scalar(value, path)


def _strict_object(value, allowed: set[str], path: str) -> dict:
    if not isinstance(value, dict):
        raise PrivacyError(f"{path} must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise PrivacyError(f"{path} has unsupported fields: {', '.join(sorted(unknown))}")
    assert_public_value(value, path)
    return value


def public_search(payload: dict) -> dict:
    value = _strict_object(payload, {"query", "limit"}, "search")
    if not isinstance(value.get("query"), str) or not value["query"].strip():
        raise PrivacyError("search.query must be a non-empty string")
    if "limit" in value and (isinstance(value["limit"], bool) or
                             not isinstance(value["limit"], int)):
        raise PrivacyError("search.limit must be an integer")
    return {"query": value["query"], "limit": value.get("limit", 8)}


def public_answer(payload: dict) -> dict:
    value = _strict_object(payload, {"question"}, "answer")
    if not isinstance(value.get("question"), str) or not value["question"].strip():
        raise PrivacyError("answer.question must be a non-empty string")
    return {"question": value["question"]}


def public_article(article: dict) -> dict:
    value = _strict_object(article, {
        "topic_id", "slug", "title", "summary", "category", "locale",
        "claims", "verified_at", "rights_class", "alias", "evidence_ref",
    }, "article")
    claims = value.get("claims")
    if not isinstance(claims, list) or not claims or len(claims) > 32:
        raise PrivacyError("article.claims must contain 1..32 objects")
    clean_claims = []
    for index, claim in enumerate(claims):
        item = _strict_object(claim, {"text", "evidence", "fact_id"},
                              f"article.claims[{index}]")
        refs = item.get("evidence")
        if not isinstance(refs, list) or not refs or not all(
                isinstance(ref, str) and ref.strip() for ref in refs):
            raise PrivacyError(f"article.claims[{index}].evidence must be non-empty strings")
        if not isinstance(item.get("fact_id"), str) or not item["fact_id"].strip():
            raise PrivacyError(f"article.claims[{index}].fact_id is required")
        clean_claims.append({"text": item["text"], "evidence": list(refs),
                             "fact_id": item["fact_id"]})
    return {**{k: value[k] for k in value if k != "claims"}, "claims": clean_claims}
