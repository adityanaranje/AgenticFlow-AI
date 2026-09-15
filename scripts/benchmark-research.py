#!/usr/bin/env python3
"""Benchmark the research pipeline without touching real services.

A research run is a chain of dependent model calls interleaved with retrieval
and database writes. This script runs the *real* pipeline
(``app.agents.research_graph.run_research`` — planner, retriever, evidence
analyser, gap detector, synthesis, citation validator, finalizer, report
storage) while only the outermost calls are faked:

    OpenAI chat completions, embeddings, Qdrant search, PostgREST

Each fake sleeps for a configurable time, so the printed wall clock and
request counts reflect the application's own orchestration — how many round
trips it makes and how much of that work it overlaps. That is how the
research tuning knobs in ``app/core/config.py`` are chosen.

Usage (from the repository root)::

    python scripts/benchmark-research.py                        # typical run
    python scripts/benchmark-research.py --chunks-per-query 60  # big corpus
    python scripts/benchmark-research.py --llm-latency 4 --db-latency 0.05

Compare runs with different ``RETRIEVAL_CONCURRENCY``, ``EVIDENCE_BATCH_CHARS``,
``EVIDENCE_CONCURRENCY`` or ``EVIDENCE_MAX_CHUNKS`` to pick your settings.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subquestions",
        type=int,
        default=4,
        help="sub-questions the planner returns (default: 4)",
    )
    parser.add_argument(
        "--chunks-per-query",
        type=int,
        default=5,
        help="retrieved chunks per query (default: 5)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="extra retrieval/analysis iterations requested by the gap detector",
    )
    parser.add_argument(
        "--llm-latency",
        type=float,
        default=2.5,
        help="seconds per chat completion (default: 2.5)",
    )
    parser.add_argument(
        "--embed-latency",
        type=float,
        default=0.30,
        help="seconds per embeddings request (default: 0.30)",
    )
    parser.add_argument(
        "--vector-latency",
        type=float,
        default=0.10,
        help="seconds per vector search (default: 0.10)",
    )
    parser.add_argument(
        "--db-latency",
        type=float,
        default=0.020,
        help="seconds per PostgREST round trip (default: 0.02)",
    )
    parser.add_argument(
        "--context-chars",
        type=int,
        default=400_000,
        help=(
            "prompt size the fake model refuses (models reject prompts beyond "
            "their context window; default 400000 characters)"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    from app.agents import llm as llm_mod
    from app.agents import research_graph
    from app.services import embeddings, evaluation_service, vector_store

    calls: Counter[str] = Counter()
    graph_state_writes: list[int] = []

    # ---- fake research run row + repository --------------------------------
    run = {
        "id": "research-bench",
        "organization_id": "org-bench",
        "user_id": "user-bench",
        "question": "What are the risks in our cloud migration?",
        "status": "queued",
        "config": {
            "max_iterations": args.iterations,
            "top_k": args.chunks_per_query,
            "max_subquestions": args.subquestions,
        },
        "graph_state": {},
    }

    class Repo:
        """Repository double; reads/writes cost a PostgREST round trip."""

        def get_any(self, research_id):
            calls["db"] += 1
            time.sleep(args.db_latency)
            return dict(run) if research_id == run["id"] else None

        def get_status(self, research_id):
            calls["db"] += 1
            time.sleep(args.db_latency)
            return run["status"]

        def set_status(self, research_id, organization_id, status, **extra):
            calls["db"] += 1
            time.sleep(args.db_latency)
            run["status"] = status

        def update(self, research_id, organization_id, fields):
            calls["db"] += 1
            time.sleep(args.db_latency)
            graph_state = fields.get("graph_state")
            if graph_state is not None:
                graph_state_writes.append(len(json.dumps(graph_state, default=str)))
            run.update(fields)
            return dict(run)

    research_graph.ResearchRepository = Repo

    # ---- fake provider calls (the real orchestration runs on top) ----------
    chunk_size = 1400

    def fake_embed(texts):
        """Deterministic vectors: the same text always yields the same vector,
        and different texts yield different ones (so distinct queries retrieve
        distinct chunks, and dedup behaves like production)."""
        calls["embed"] += 1
        calls["embed_inputs"] += len(texts)
        time.sleep(args.embed_latency)
        return [
            [float(len(text)), float(sum(ord(char) for char in text) % 997)]
            for text in texts
        ]

    def fake_search(**kwargs):
        calls["vector"] += 1
        time.sleep(args.vector_latency)
        query_vector = kwargs.get("query_vector") or [0.0, 0.0]
        top_k = int(kwargs.get("top_k") or 5)
        base = (int(query_vector[1]) if len(query_vector) > 1 else 0) % 500
        return [
            {
                "id": f"point-{index}",
                "score": max(0.1, 0.95 - 0.01 * index),
                "payload": {
                    "document_id": f"doc-{index % 3}",
                    "document_chunk_id": f"chunk-{index}",
                    "content": "Migration risk paragraph. " * (chunk_size // 28),
                    "filename": f"policy_{index % 3}.pdf",
                    "page_number": 1 + index % 5,
                    "chunk_index": index,
                    "organization_id": kwargs.get("organization_id"),
                },
            }
            for index in range(base, base + top_k)
        ]

    def fake_chat(messages, **kwargs):
        calls["llm"] += 1
        prompt_chars = sum(len(message.get("content") or "") for message in messages)
        time.sleep(args.llm_latency)
        if prompt_chars > args.context_chars:
            # Model providers reject oversized prompts; the analyser then has
            # no usable output and the run falls back to flat evidence.
            calls["llm_context_overflow"] += 1
            raise RuntimeError(
                f"prompt is too long: {prompt_chars} characters "
                f"(limit {args.context_chars})"
            )
        system = (messages[0].get("content") or "").lower()
        if "research planner" in system:
            return json.dumps(
                {
                    "sub_questions": [
                        f"Sub-question {index}" for index in range(args.subquestions)
                    ]
                }
            )
        if "important, source-supported" in system or "retrieved document excerpts" in system:
            # One claim per excerpt group, citing the first source of the prompt.
            return json.dumps(
                {
                    "claims": [
                        {
                            "claim": "Migration carries security and cost risk.",
                            "source_key": 0,
                            "confidence": 0.8,
                        }
                    ]
                }
            )
        if "sufficient" in system and "follow_up" in system:
            calls["gap"] += 1
            follow_up = ["Follow-up query"] if calls["gap"] <= args.iterations else []
            return json.dumps(
                {
                    "sufficient": not follow_up,
                    "gaps": [],
                    "follow_up_queries": follow_up,
                }
            )
        if "grounded research report" in system:
            return "# Executive Summary\n\nGrounded finding. [E0]\n"
        raise AssertionError(f"unhandled prompt: {system[:60]}")

    embeddings.embed_texts = fake_embed
    vector_store.search_vectors = fake_search
    llm_mod.chat = fake_chat

    # ---- fake report storage -----------------------------------------------
    class ReportRepo:
        def create(self, **kwargs):
            calls["db"] += 1
            time.sleep(args.db_latency)
            return {"id": "report-bench", **kwargs}

        def create_source(self, data):
            calls["db"] += 1
            time.sleep(args.db_latency)
            return dict(data)

        def create_sources(self, rows):
            calls["db_bulk"] += 1
            time.sleep(args.db_latency + 0.002 * len(rows))
            return [{"id": f"source-{index}"} for index in range(len(rows))]

    research_graph.report_service.ReportRepository = ReportRepo

    # Evaluation is a separate, non-blocking concern (and costs another model
    # call in production); it is not part of the run's latency here.
    evaluation_service.evaluate_report = lambda **kwargs: None

    # ---- run ----------------------------------------------------------------
    started = time.perf_counter()
    result = research_graph.run_research("research-bench")
    duration = time.perf_counter() - started

    final_state = run.get("graph_state") or {}
    print(f"status           : {result.get('status')}")
    print(f"wall clock       : {duration:.2f}s")
    print(
        "workload         : "
        f"{args.subquestions} sub-questions, {args.chunks_per_query} chunks/query, "
        f"{args.iterations} extra iteration(s)"
    )
    print("remote requests  :")
    for name, count in sorted(calls.items()):
        print(f"  {name:<22} {count}")
    if graph_state_writes:
        print(
            "graph_state      : "
            f"{len(graph_state_writes)} write(s), largest "
            f"{max(graph_state_writes) / 1000:.1f} KB, total "
            f"{sum(graph_state_writes) / 1000:.1f} KB"
        )
    print(
        "final counts     : "
        f"retrieved={final_state.get('retrieved_count')} "
        f"evidence={final_state.get('evidence_count')} "
        f"citations={final_state.get('citations_count')}"
    )
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
