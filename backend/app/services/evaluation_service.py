"""Report evaluation (Phase 5, §20-§22).

Metrics are computed from the *stored* report + sources so nothing is
model-fabricated:

    citation_correctness  -> fraction of in-text citations that map to a
                             stored, grounded source
    citation_completeness -> fraction of stored sources that are actually
                             cited in the report
    groundedness          -> fraction of report sentences carrying a citation
    relevance             -> mean retrieval score of the cited sources
    answer_quality        -> LLM judgement when configured, else the mean of
                             the objective metrics above

Raw explanations for every metric are persisted (``evaluation_results.metadata``)
for inspection. Evaluation never modifies the original report.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings
from app.core.logging import get_logger
from app.db.repositories.reports import EvaluationRepository

logger = get_logger(__name__)

_CITE_RE = re.compile(r"\[E(\d+)\]")
_METRICS = (
    "citation_correctness",
    "citation_completeness",
    "relevance",
    "groundedness",
    "answer_quality",
)


def _sentences(text: str) -> list[str]:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    sentences: list[str] = []
    for line in lines:
        if line.startswith("#"):
            continue  # skip headings
        sentences.extend(seg for seg in re.split(r"(?<=[.!?])\s+", line) if seg)
    return sentences


def evaluate_report_content(
    content: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute objective metrics from a report body + its stored sources."""
    content = content or ""
    sentences = _sentences(content)
    total = len(sentences)
    cited_sentences = [s for s in sentences if _CITE_RE.search(s)]

    def _num(label: str) -> int:
        digits = re.sub(r"\D", "", label)
        try:
            return int(digits)
        except ValueError:
            return -1

    # Stored grounded citation label numbers (from report_sources metadata,
    # e.g. "E0" -> 0).
    grounded_nums = {
        _num(str((s.get("metadata") or {}).get("citation_label", "")))
        for s in sources
        if (s.get("metadata") or {}).get("citation_label")
    }
    # All [E<idx>] numbers actually referenced in the body.
    referenced = {int(i) for i in map(int, _CITE_RE.findall(content))}
    grounded_nums.discard(-1)

    correctness = 0.0
    if referenced:
        correctness = len(referenced & grounded_nums) / len(referenced)

    completeness = 0.0
    if grounded_nums:
        completeness = len(referenced & grounded_nums) / len(grounded_nums)
    elif referenced:
        completeness = 0.0

    groundedness = (len(cited_sentences) / total) if total else 0.0

    scores = [
        (s.get("metadata") or {}).get("retrieval_score")
        for s in sources
        if (s.get("metadata") or {}).get("retrieval_score") is not None
    ]
    relevance = (sum(float(x) for x in scores) / len(scores)) if scores else 0.0
    relevance = max(0.0, min(1.0, relevance))

    metrics = {
        "citation_correctness": round(correctness, 4),
        "citation_completeness": round(completeness, 4),
        "relevance": round(relevance, 4),
        "groundedness": round(groundedness, 4),
        # answer_quality filled below (LLM or heuristic mean).
        "answer_quality": None,
    }

    explanations = {
        "total_sentences": total,
        "cited_sentences": len(cited_sentences),
        "referenced_labels": sorted(str(x) for x in referenced),
        "stored_grounded_labels": sorted(f"E{n}" for n in grounded_nums),
        "sources_count": len(sources),
        "retrieval_scores": [round(float(x), 4) for x in scores][:100],
    }

    llm_quality = _llm_quality(content)
    if llm_quality is not None:
        metrics["answer_quality"] = round(llm_quality, 4)
        explanations["answer_quality_source"] = "llm"
    else:
        objective = [
            m
            for name, m in metrics.items()
            if name != "answer_quality" and m is not None
        ]
        metrics["answer_quality"] = round(
            (sum(objective) / len(objective)) if objective else 0.0, 4
        )
        explanations["answer_quality_source"] = "objective_mean"

    return {"metrics": metrics, "explanations": explanations}


def _llm_quality(content: str) -> Optional[float]:
    """LLM answer-quality score, or None when OpenAI is not configured.

    Scored as a single float in [0,1]; never used to gate evaluation.
    """
    if not settings.openai_api_key:
        return None
    try:
        from app.agents.llm import chat, parse_json_object

        text = chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Rate the quality of a research report on a scale 0-1. "
                        'Respond JSON only: {"answer_quality": 0.0}'
                    ),
                },
                {"role": "user", "content": content[:8000]},
            ],
            max_tokens=60,
        )
        payload = parse_json_object(text)
        return float(payload.get("answer_quality", 0.0))
    except Exception:
        logger.debug("LLM answer-quality scoring unavailable; using objective mean.")
        return None


def persist_evaluation(
    *,
    organization_id: str,
    report_id: str,
    test_case: str,
    metrics: dict[str, Any],
    explanations: dict[str, Any],
) -> dict[str, Any] | None:
    repo = EvaluationRepository()
    run = repo.create_run(organization_id=organization_id, report_id=report_id)
    if not run:
        return None
    run_id = run["id"]
    try:
        for metric, score in metrics.items():
            if score is None:
                continue
            repo.create_result(
                run_id=run_id,
                test_case=test_case,
                metric=metric,
                score=float(score),
                actual={"score": float(score)},
                metadata={
                    "explanations": explanations.get(metric)
                    or {"detail": explanations},
                },
            )
        repo.complete_run(run_id, {"metrics": metrics, "test_case": test_case})
    except Exception:
        logger.exception("Failed to persist evaluation results for run %s", run_id)
    return run


def evaluate_report(
    *,
    organization_id: str,
    report_id: str,
    test_case: str = "report",
) -> dict[str, Any] | None:
    """Fetch a report + sources and store an evaluation run. Never mutates it."""
    from app.db.repositories.reports import ReportRepository

    report = ReportRepository().get(report_id, organization_id)
    if not report:
        return None
    sources = ReportRepository().list_sources(report_id)
    result = evaluate_report_content(report.get("content") or "", sources)
    run = persist_evaluation(
        organization_id=organization_id,
        report_id=report_id,
        test_case=test_case,
        metrics=result["metrics"],
        explanations=result["explanations"],
    )
    return {"evaluation_run_id": (run or {}).get("id"), **result}
