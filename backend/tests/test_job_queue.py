"""Tests for the Redis-backed job queue (Phase 4, §6)."""

import json

from redis.exceptions import TimeoutError as RedisTimeoutError

from app.services import job_queue


class FakeRedis:
    def __init__(self, mode):
        self.mode = mode
        self.pushed = []

    def blpop(self, keys, timeout=0):
        if self.mode == "timeout":
            # What redis-py raises when the socket read times out waiting —
            # the worker's steady-state "no job yet" condition.
            raise RedisTimeoutError("Timeout reading from socket")
        return (keys[0], json.dumps({"document_id": "doc-1"}))

    def rpush(self, queue, payload):
        self.pushed.append((queue, payload))
        return 1


def test_pop_returns_none_on_socket_timeout(monkeypatch):
    """An idle blocking wait must be quiet — not a logged exception."""
    monkeypatch.setattr(job_queue, "get_redis_client", lambda: FakeRedis("timeout"))
    assert job_queue._pop("q", timeout=5) is None
    assert job_queue.pop_next_document(timeout=5) is None


def test_pop_parses_enqueued_job(monkeypatch):
    monkeypatch.setattr(job_queue, "get_redis_client", lambda: FakeRedis("ok"))
    assert job_queue._pop("q", timeout=5) == {"document_id": "doc-1"}
    assert job_queue.pop_next_document(timeout=5) == "doc-1"


def test_enqueue_document_pushes_payload(monkeypatch):
    client = FakeRedis("ok")
    monkeypatch.setattr(job_queue, "get_redis_client", lambda: client)
    assert job_queue.enqueue_document("doc-9") is True
    assert client.pushed == [
        (job_queue.QUEUE_NAME, json.dumps({"document_id": "doc-9"}))
    ]
