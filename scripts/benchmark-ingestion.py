#!/usr/bin/env python3
"""Benchmark the document ingestion pipeline without touching real services.

Uploads and chunking wait on remote calls: OpenAI embeddings, Supabase
Storage/PostgREST and Qdrant. This script runs the *real* pipeline
(``app.workers.document_worker.process_document`` — parsing, chunking, id
linkage, status transitions) against fakes that sleep for a configurable
amount of time per request. It reports the wall-clock time and the number of
remote requests each stage issues, which is how the ingestion tuning knobs in
``app/core/config.py`` are chosen.

Usage (from the repository root)::

    python scripts/benchmark-ingestion.py                     # 300 paragraphs
    python scripts/benchmark-ingestion.py --paragraphs 2000
    python scripts/benchmark-ingestion.py --embed-latency 0.4 --db-latency 0.03

Options let you model your providers, e.g. a slow PostgREST (``--db-latency``)
or a rate-limited embeddings endpoint (``--embed-latency``). Compare runs with
different ``EMBEDDING_CONCURRENCY`` / ``CHUNK_INSERT_BATCH_SIZE`` environment
values to pick settings for your deployment.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from typing import ClassVar

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--paragraphs",
        type=int,
        default=300,
        help="paragraphs in the synthetic document (default: 300)",
    )
    parser.add_argument(
        "--db-latency",
        type=float,
        default=0.020,
        help="seconds per PostgREST round trip (default: 0.02)",
    )
    parser.add_argument(
        "--storage-latency",
        type=float,
        default=0.120,
        help="seconds to download the file from storage (default: 0.12)",
    )
    parser.add_argument(
        "--embed-latency",
        type=float,
        default=0.300,
        help="seconds per OpenAI embeddings request (default: 0.3)",
    )
    parser.add_argument(
        "--qdrant-latency",
        type=float,
        default=0.150,
        help="seconds per Qdrant request (default: 0.15)",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    from app.core.config import settings
    from app.services.document_parser import ParsedDocument, ParsedPage
    from app.workers import document_worker

    # ---- synthetic document -------------------------------------------------
    paragraph = (
        "Paragraph {} discusses tenant isolation, retrieval quality, evidence "
        "handling and the citation contract enforced by the platform."
    )
    text = "\n\n".join(paragraph.format(i) * 2 for i in range(args.paragraphs))
    parsed = ParsedDocument(
        filename="benchmark.pdf",
        file_type="pdf",
        pages=[ParsedPage(text=text, page_number=None)],
    )

    calls: Counter[str] = Counter()

    # ---- latency-simulating fakes ------------------------------------------
    class Repo:
        def __init__(self, record):
            self.record = dict(record)
            self.chunks: list[dict] = []
            self.updates = 0

        def get_document(self, document_id):
            calls["db"] += 1
            time.sleep(args.db_latency)
            return dict(self.record)

        def update(self, document_id, organization_id, fields):
            calls["db"] += 1
            time.sleep(args.db_latency)
            self.updates += 1
            self.record.update(fields)
            return dict(self.record)

        def delete_chunks(self, document_id, organization_id):
            calls["db"] += 1
            time.sleep(args.db_latency)

        def create_chunk(self, row):
            calls["db"] += 1
            time.sleep(args.db_latency)
            self.chunks.append(row)
            return row

        def create_chunks(self, rows):
            calls["db_bulk"] += 1
            # One request, plus a little serialisation cost per row.
            time.sleep(args.db_latency + 0.005 * (len(rows) / 200))
            self.chunks.extend(rows)
            return [{"id": row["id"]} for row in rows]

    class FakeQdrant:
        """Fake low-level client, so the REAL batching code path runs.

        Patching ``vector_store.upsert_chunk_vectors`` would hide the batching
        under test, so the client itself is faked instead: the app's own
        batching, concurrency and (no-op) collection bootstrap execute for
        real and show up in the request counts.
        """

        def __init__(self):
            self.points: list[dict] = []

        # -- collection bookkeeping (mirrors a healthy, compatible cluster)
        def get_collections(self):
            calls["qdrant"] += 1
            time.sleep(args.db_latency)

            class _Col:
                name = settings.qdrant_collection

            class _Resp:
                collections = [_Col()] if created["done"] else []

            return _Resp()

        def create_collection(self, **kwargs):
            calls["qdrant"] += 1
            time.sleep(args.qdrant_latency)
            created["done"] = True

        def create_payload_index(self, **kwargs):
            calls["qdrant"] += 1
            time.sleep(args.db_latency)

        def get_collection(self, name):
            calls["qdrant"] += 1
            time.sleep(args.db_latency)

            class _Info:
                payload_schema: ClassVar[dict] = {}

            class _Params:
                pass

            from qdrant_client.http import models as qmodels

            _Params.vectors = qmodels.VectorParams(
                size=settings.embedding_dimensions,
                distance=qmodels.Distance.COSINE,
            )
            _Info.config = type("_Config", (), {"params": _Params})
            return _Info()

        # -- data plane
        def upsert(self, collection_name, points):
            calls["qdrant_upsert"] += 1
            time.sleep(args.qdrant_latency)
            self.points.extend(points)

        def delete(self, collection_name, points_selector):
            calls["qdrant_delete"] += 1
            time.sleep(args.qdrant_latency)

    doc = {
        "id": "doc-bench",
        "organization_id": "org-bench",
        "filename": "benchmark.pdf",
        "file_type": "pdf",
        "status": "pending",
        "storage_path": "organizations/org-bench/documents/doc-bench/benchmark.pdf",
    }
    created = {"done": False}
    repo, store = Repo(doc), FakeQdrant()

    def download(organization_id, document_id, filename):
        calls["storage"] += 1
        time.sleep(args.storage_latency)
        return b"bytes"

    def embed(texts):
        calls["embed"] += 1
        time.sleep(args.embed_latency)
        return [[0.0] * settings.embedding_dimensions for _ in texts]

    document_worker.DocumentRepository = lambda: repo
    document_worker.document_storage.download_document = download
    document_worker.document_parser.parse_document = (
        lambda data, file_type=None, filename="": parsed
    )
    document_worker.embeddings.embed_texts = embed
    document_worker.vector_store._client = lambda: store
    document_worker.vector_store._payload_indexes_ready = False

    # ---- run ---------------------------------------------------------------
    started = time.perf_counter()
    result = document_worker.process_document("doc-bench")
    duration = time.perf_counter() - started

    chunks = len(repo.chunks)
    print(f"document        : {len(text):,} chars, {chunks} chunks")
    print(f"status          : {result['status']}")
    print(f"wall clock      : {duration:.2f}s")
    print(
        "config          : "
        f"embed_batch={getattr(settings, 'embedding_batch_size', 'n/a')} "
        f"embed_concurrency={getattr(settings, 'embedding_concurrency', 'n/a')} "
        f"chunk_insert_batch={getattr(settings, 'chunk_insert_batch_size', 'n/a')} "
        f"qdrant_batch={getattr(settings, 'qdrant_upsert_batch_size', 'n/a')} "
        f"qdrant_concurrency={getattr(settings, 'qdrant_upsert_concurrency', 'n/a')}"
    )
    print("remote requests :")
    for name, count in sorted(calls.items()):
        print(f"  {name:<14} {count}")
    print(
        "request pattern : "
        f"{calls['embed']} embedding, "
        f"{calls['db_bulk']} bulk insert, "
        f"{calls['qdrant_upsert']} vector upsert "
        f"({calls['db'] + calls['qdrant']} other metadata request(s))"
    )
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
