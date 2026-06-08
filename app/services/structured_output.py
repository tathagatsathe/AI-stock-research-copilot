"""Parse and validate LLM JSON into decision-brief shapes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

DecisionVerdict = Literal["watch", "cautious", "elevated_risk"]
EvidenceQuality = Literal["high", "medium", "low"]

_VALID_VERDICTS = {"watch", "cautious", "elevated_risk"}
_VALID_EVIDENCE = {"high", "medium", "low"}


def parse_decision_brief_payload(raw: dict[str, Any], *, fallback_note: str) -> dict[str, Any]:
    """Normalize LLM output to the API decision_brief contract."""
    verdict = str(raw.get("verdict", "watch")).strip().lower()
    if verdict not in _VALID_VERDICTS:
        verdict = "cautious"

    evidence = str(raw.get("evidence_quality", "medium")).strip().lower()
    if evidence not in _VALID_EVIDENCE:
        evidence = "medium"

    bullets = _as_str_list(raw.get("summary_bullets"), max_items=3)
    if not bullets:
        bullets = [fallback_note]

    return {
        "verdict": verdict,
        "summary_bullets": bullets,
        "top_risks": _as_str_list(raw.get("top_risks"), max_items=5),
        "tensions": _as_str_list(raw.get("tensions"), max_items=3),
        "evidence_quality": evidence,
        "synthesized_at": datetime.now(timezone.utc).isoformat(),
        "news_coverage_note": str(raw.get("news_coverage_note") or fallback_note),
        "synthesis_source": "llm",
    }


def parse_ask_response(raw: dict[str, Any]) -> dict[str, Any]:
    answer = str(raw.get("answer", "")).strip()
    if not answer:
        answer = "Insufficient evidence to answer confidently."
    citations = raw.get("citations") or []
    normalized_citations: list[dict[str, str]] = []
    if isinstance(citations, list):
        for item in citations[:8]:
            if not isinstance(item, dict):
                continue
            normalized_citations.append(
                {
                    "source": str(item.get("source") or "unknown"),
                    "excerpt": str(item.get("excerpt") or "")[:500],
                    "url": str(item.get("url") or ""),
                }
            )
    confidence = raw.get("retrieval_confidence")
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"
    return {
        "answer": answer,
        "citations": normalized_citations,
        "retrieval_confidence": confidence,
    }


def _as_str_list(value: Any, *, max_items: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out
