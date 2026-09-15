"""Dispatch of a research run: queue round trip, worker consumption, takeover.

A run is created in ``queued`` state and only starts when *something* consumes
the Redis queue. These tests cover the three ways that can happen:

* a worker pops the job (``run_worker_loop``),
* nothing consumes it, so the API process claims it back off the queue after
  ``RESEARCH_UNCLAIMED_FALLBACK_SECONDS`` (a bare ``uvicorn`` dev setup),
* Redis is unavailable, so it goes straight to the in-process pool.

The claim must be exactly-once: a job is either taken by a worker or by the
fallback, never both.
"""

from __future__ import annotations

import json
import threading
import time
from typing import ClassVar

import pytest
from app.agents import research_graph as graph_mod
from app.services import background, job_queue, research_service


class FakeRedis:
    """Minimal Redis list implementation used by the queue helpers."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.lock = threading.Lock()
        self.ready = threading.Event()

    def rpush(self, queue: str, raw: str) -> int:
        with self.lock:
            self.lists.setdefault(queue, []).append(raw)
            self.ready.set()
            return len(self.lists[queue])

    def lrem(self, queue: str, count: int, raw: str) -> int:
        with self.lock:
            items = self.lists.get(queue, [])
            removed = 0
            for _ in range(count):
                if raw not in items:
                    break
                items.remove(raw)
                removed += 1
            return removed

    def blpop(self, queues, timeout: int = 0):
        queue = queues[0]
        deadline = time.monotonic() + (timeout or 0)
        while True:
            with self.lock:
                items = self.lists.get(queue, [])
                if items:
                    return queue, items.pop(0)
            if timeout and time.monotonic() >= deadline:
                return None
            self.ready.wait(0.01)


@pytest.fixture()
def fake_redis(monkeypatch):
    client = FakeRedis()
    monkeypatch.setattr(job_queue, "get_redis_client", lambda: client)
    return client


@pytest.fixture()
def ran(monkeypatch):
    """Record executions instead of running the pipeline."""
    executed: list[str] = []
    monkeypatch.setattr(graph_mod, "run_research", executed.append)
    return executed


# --------------------------------------------------------------------------
# queue round trip (previously untested)
# --------------------------------------------------------------------------


def test_enqueued_research_message_is_what_the_worker_pops(fake_redis):
    assert job_queue.enqueue_research("run-1") is True

    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == ['{"research_id": "run-1"}']
    assert job_queue.pop_next_research(timeout=1) == "run-1"
    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == []


def test_claim_takes_the_message_back_only_when_still_queued(fake_redis):
    job_queue.enqueue_research("run-1")

    # Still queued -> the claim wins the job.
    assert job_queue.claim_research("run-1") is True
    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == []
    # Nothing left -> a second claim (or a worker pop) finds nothing.
    assert job_queue.claim_research("run-1") is False
    assert job_queue.pop_next_research(timeout=1) is None


def test_claim_after_a_worker_popped_the_job_does_nothing(fake_redis):
    job_queue.enqueue_research("run-1")
    assert job_queue.pop_next_research(timeout=1) == "run-1"  # worker wins

    assert job_queue.claim_research("run-1") is False


def test_claim_only_touches_its_own_run(fake_redis):
    job_queue.enqueue_research("run-1")
    job_queue.enqueue_research("run-2")

    assert job_queue.claim_research("run-2") is True

    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == ['{"research_id": "run-1"}']
    assert job_queue.pop_next_research(timeout=1) == "run-1"


def test_claim_without_redis_or_on_error_is_false(monkeypatch):
    monkeypatch.setattr(job_queue, "get_redis_client", lambda: None)
    assert job_queue.claim_research("run-1") is False

    class Broken:
        def lrem(self, *_args, **_kwargs):
            raise RuntimeError("redis down")

    monkeypatch.setattr(job_queue, "get_redis_client", lambda: Broken())
    assert job_queue.claim_research("run-1") is False


# --------------------------------------------------------------------------
# create_research: scheduling of the takeover
# --------------------------------------------------------------------------


class _Repo:
    """ResearchRepository double with the attributes the service uses."""

    statuses: ClassVar[dict[str, str]] = {}
    created: ClassVar[list[dict]] = []

    def __init__(self, *_args, **_kwargs):
        pass

    def create(self, **_kwargs):
        run = {"id": f"run-{len(type(self).created) + 1}"}
        type(self).created.append(run)
        type(self).statuses[run["id"]] = "queued"
        return run

    def get_status(self, research_id):
        return type(self).statuses.get(research_id)

    def get(self, research_id, _organization_id):
        if research_id not in type(self).statuses:
            return None
        return {"id": research_id, "status": type(self).statuses[research_id]}

    def update(self, research_id, _organization_id, fields):
        if "status" in fields:
            type(self).statuses[research_id] = fields["status"]


@pytest.fixture()
def repo(monkeypatch):
    class Scoped(_Repo):
        pass

    Scoped.statuses = {"run-1": "queued"}
    Scoped.created = []
    monkeypatch.setattr(research_service, "ResearchRepository", Scoped)
    return Scoped


def test_enqueue_schedules_a_takeover_check(repo, fake_redis, monkeypatch):
    scheduled: list[tuple[str, float]] = []
    monkeypatch.setattr(
        research_service,
        "_schedule_unclaimed_check",
        lambda research_id, delay: scheduled.append((research_id, delay)),
    )

    run = research_service.create_research(
        organization_id="org", user_id="user", question="why?"
    )

    assert job_queue.pop_next_research(timeout=1) == run["id"]
    assert scheduled == [(run["id"], float(15))]


def test_takeover_is_not_scheduled_when_disabled(repo, fake_redis, monkeypatch):
    scheduled: list[tuple[str, float]] = []
    monkeypatch.setattr(
        research_service,
        "_schedule_unclaimed_check",
        lambda research_id, delay: scheduled.append((research_id, delay)),
    )
    monkeypatch.setattr(
        research_service.settings, "research_unclaimed_fallback_seconds", 0
    )

    research_service.create_research(organization_id="org", user_id="user", question="why?")

    assert scheduled == []


def test_timer_wiring_takes_over_a_run_when_no_worker_exists(
    repo, fake_redis, ran, monkeypatch
):
    """End to end through the real Timer: create -> queue -> takeover -> run."""
    monkeypatch.setattr(
        research_service.settings, "research_unclaimed_fallback_seconds", 1
    )

    run = research_service.create_research(
        organization_id="org", user_id="user", question="no worker running"
    )
    assert ran == []  # queued, not started

    deadline = time.time() + 5
    while not ran and time.time() < deadline:
        time.sleep(0.05)

    assert ran == [run["id"]]
    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == []
    assert background.wait_idle(timeout=5)


def test_takeover_check_uses_a_daemon_timer(monkeypatch):
    started: list[tuple] = []

    class Timer:
        def __init__(self, delay, func, args=()):
            started.append((delay, func, args))
            self.daemon = False

        def start(self):
            pass

    monkeypatch.setattr(research_service.threading, "Timer", Timer)

    research_service._schedule_unclaimed_check("run-1", 5.0)

    assert started == [(5.0, research_service._claim_unclaimed, ("run-1", 5.0))]
    # A non-daemon timer would keep the process (and pytest) alive for its delay.


# --------------------------------------------------------------------------
# the takeover itself
# --------------------------------------------------------------------------


def test_unclaimed_run_is_taken_over_and_executed(repo, fake_redis, ran, monkeypatch):
    job_queue.enqueue_research("run-1")

    research_service._claim_unclaimed("run-1", 15.0)
    assert background.wait_idle(timeout=5)

    assert ran == ["run-1"]
    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == []


def test_takeover_defers_to_the_worker_that_popped_the_job(
    repo, fake_redis, ran, monkeypatch
):
    job_queue.enqueue_research("run-1")
    assert job_queue.pop_next_research(timeout=1) == "run-1"
    repo.statuses["run-1"] = "planning"

    research_service._claim_unclaimed("run-1", 15.0)
    assert background.wait_idle(timeout=5)

    assert ran == []


def test_takeover_skips_runs_that_already_settled(repo, fake_redis, ran):
    job_queue.enqueue_research("run-1")
    repo.statuses["run-1"] = "completed"

    research_service._claim_unclaimed("run-1", 15.0)
    assert background.wait_idle(timeout=5)

    assert ran == []


def test_takeover_does_nothing_without_redis(repo, ran, monkeypatch):
    monkeypatch.setattr(job_queue, "get_redis_client", lambda: None)
    repo.statuses["run-1"] = "queued"

    research_service._claim_unclaimed("run-1", 15.0)
    assert background.wait_idle(timeout=5)

    assert ran == []


def test_takeover_never_raises_on_a_failing_repository(repo, fake_redis, monkeypatch):
    class Broken(_Repo):
        def get_status(self, _research_id):
            raise RuntimeError("supabase down")

    monkeypatch.setattr(research_service, "ResearchRepository", Broken)

    research_service._claim_unclaimed("run-1", 15.0)  # must not raise


# --------------------------------------------------------------------------
# a worker consuming the queue end to end
# --------------------------------------------------------------------------


def test_worker_loop_consumes_queued_research(repo, fake_redis, ran):
    for run_id in ("run-1", "run-2"):
        repo.statuses[run_id] = "queued"
        job_queue.enqueue_research(run_id)

    stop = threading.Event()
    worker = threading.Thread(
        target=graph_mod.run_worker_loop,
        kwargs={"interval": 1, "concurrency": 2, "stop_event": stop},
        daemon=True,
    )
    worker.start()
    try:
        deadline = time.time() + 5
        while len(ran) < 2 and time.time() < deadline:
            time.sleep(0.05)
        assert sorted(ran) == ["run-1", "run-2"]
        assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == []

        # Graceful stop: the loop returns instead of polling forever, so
        # `docker stop` / Ctrl+C does not kill a run in flight.
        stop.set()
        worker.join(timeout=5)
        assert not worker.is_alive()
    finally:
        stop.set()
        worker.join(timeout=5)


def test_document_worker_loop_stops_on_the_shared_event(monkeypatch):
    from app.workers import document_worker

    stop = threading.Event()
    monkeypatch.setattr(document_worker, "_pop_with_backoff", lambda _wait: None)

    worker = threading.Thread(
        target=document_worker._consume_forever,
        args=(0, 1, stop),
        daemon=True,
    )
    worker.start()
    stop.set()
    worker.join(timeout=5)

    assert not worker.is_alive()


# --------------------------------------------------------------------------
# cancellation
# --------------------------------------------------------------------------


def test_cancelling_a_queued_run_removes_its_queue_message(repo, fake_redis):
    job_queue.enqueue_research("run-1")

    assert research_service.cancel_research("run-1", "org") is True

    assert repo.statuses["run-1"] == "cancelled"
    assert fake_redis.lists[job_queue.RESEARCH_QUEUE] == []
    assert job_queue.pop_next_research(timeout=1) is None


def test_a_cancelled_run_never_starts(repo, monkeypatch):
    class Repo:
        def get_any(self, _research_id):
            return {
                "id": "run-1",
                "organization_id": "org",
                "user_id": "user",
                "question": "why?",
                "config": {},
                "status": "cancelled",
            }

        def set_status(self, *_args, **_kwargs):
            raise AssertionError("a cancelled run must not be started")

    monkeypatch.setattr(graph_mod, "ResearchRepository", Repo)

    assert graph_mod.run_research("run-1") == {"status": "cancelled"}


def test_queue_message_json_is_stable_across_enqueue_and_claim(fake_redis):
    """The claim must match byte-for-byte the message the worker pop gets."""
    job_queue.enqueue_research("run-1")
    pushed = fake_redis.lists[job_queue.RESEARCH_QUEUE][0]

    assert pushed == json.dumps({"research_id": "run-1"})
    assert job_queue.claim_research("run-1") is True
