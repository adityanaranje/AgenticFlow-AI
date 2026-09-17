"""Tests for per-user LLM usage guardrails + input/output guardrails.

Redis is faked in-process; the token math, concurrency slots, admission
rejection, config sanitization, per-run budget and the report-length cap
are all covered without any network.
"""

import pytest

from app.agents import research_graph as graph_mod
from app.core.exceptions import AdmissionError, BudgetExhaustedError
from app.services import llm_guardrails as guard
from app.services import research_service


# --- fake redis ----------------------------------------------------------------

class FakeRedis:
    def __init__(self):
        self.kv: dict[str, str] = {}
        self.sets: dict[str, set] = {}

    def mget(self, *keys):
        return [self.kv.get(k) for k in keys]

    def incrby(self, key, amount):
        self.kv[key] = str(int(self.kv.get(key, 0)) + amount)
        return int(self.kv[key])

    def expire(self, key, ttl):
        return True

    def set(self, key, value, ex=None):
        self.kv[key] = value
        return True

    def delete(self, *keys):
        for key in keys:
            self.kv.pop(key, None)
        return True

    def exists(self, key):
        return int(key in self.kv)

    def sadd(self, key, *members):
        self.sets.setdefault(key, set()).update(members)
        return len(self.sets[key])

    def srem(self, key, *members):
        self.sets.get(key, set()).difference_update(members)

    def scard(self, key):
        return len(self.sets.get(key, set()))

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def pipeline(self):
        r = self

        class _Pipe:
            def __init__(self):
                self.ops = []

            def incrby(self, key, amount):
                self.ops.append(("i", key, amount))
                return self

            def expire(self, key, ttl):
                self.ops.append(("e", key, ttl))
                return self

            def execute(self):
                for op in self.ops:
                    if op[0] == "i":
                        r.incrby(op[1], op[2])
                    else:
                        r.expire(op[1], op[2])

        return _Pipe()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(guard, "get_redis_client", lambda: fake)
    return fake


# --- token quotas ---------------------------------------------------------------

def test_quota_allows_under_limit(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_hourly", 100)
    guard.record_user_tokens("u1", 50)
    guard.check_user_quota("u1")  # no raise
    usage = guard.user_token_usage("u1")
    assert usage["hourly"]["used"] == 50


def test_quota_rejects_at_limit(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_hourly", 100)
    guard.record_user_tokens("u1", 100)
    with pytest.raises(AdmissionError, match="hourly"):
        guard.check_user_quota("u1")


def test_quota_daily_window_independent(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_hourly", 0)
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_daily", 10)
    guard.record_user_tokens("u1", 10)
    with pytest.raises(AdmissionError, match="daily"):
        guard.check_user_quota("u1")


def test_zero_limit_means_unlimited(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_hourly", 0)
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_daily", 0)
    guard.record_user_tokens("u1", 10**9)
    guard.check_user_quota("u1")  # never enforced


def test_no_redis_degrades_to_allowed(monkeypatch):
    monkeypatch.setattr(guard, "get_redis_client", lambda: None)
    guard.check_user_quota("u1")  # no raise without Redis
    guard.record_user_tokens("u1", 10)  # no-op
    assert guard.user_token_usage("u1")["hourly"]["used"] == 0


# --- concurrent-run slots ---------------------------------------------------------

def test_concurrent_slot_enforced(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_max_concurrent_runs", 2)
    guard.acquire_run_slot("u1", "r1")
    guard.acquire_run_slot("u1", "r2")
    with pytest.raises(AdmissionError, match="2 research run"):
        guard.acquire_run_slot("u1", "r3")

    guard.release_run_slot("u1", "r1")
    guard.acquire_run_slot("u1", "r3")  # fits again


def test_stale_slot_of_dead_run_is_reaped(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_max_concurrent_runs", 1)
    guard.acquire_run_slot("u1", "dead-run")
    # Simulate a process crash: the slot marker key vanished (TTL expiry),
    # but the set member lingers.
    dead_slot_key = guard._run_slot_key("u1", "dead-run")
    fake_redis.kv.pop(dead_slot_key, None)

    guard.acquire_run_slot("u1", "alive-run")  # must succeed
    assert guard._run_set_key("u1") in fake_redis.sets
    assert fake_redis.smembers(guard._run_set_key("u1")) == {"alive-run"}


def test_zero_concurrency_limit_means_unlimited(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_max_concurrent_runs", 0)
    for i in range(10):
        guard.acquire_run_slot("u1", f"r{i}")  # no raise, nothing tracked


# --- admission at dispatch --------------------------------------------------------

class _FakeRepo:
    def __init__(self, reject=False):
        self.rows = {}
        self.reject = reject

    def create(self, **kwargs):
        row = {"id": "run-1", "status": "queued", **kwargs}
        self.rows["run-1"] = row
        return row

    def update(self, research_id, organization_id, fields):
        self.rows[research_id].update(fields)
        return self.rows[research_id]


def test_dispatch_rejects_when_quota_exhausted(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_token_limit_hourly", 10)
    guard.record_user_tokens("user-1", 10)

    repo = _FakeRepo()
    monkeypatch.setattr(research_service, "ResearchRepository", lambda: repo)
    monkeypatch.setattr(research_service.job_queue, "enqueue_research", lambda rid: True)

    with pytest.raises(AdmissionError):
        research_service.create_research(
            organization_id="org", user_id="user-1", question="why?", config={}
        )
    # The orphaned row is marked failed instead of lingering "queued".
    assert repo.rows["run-1"]["status"] == "failed"
    assert "token limit" in repo.rows["run-1"]["error"]


def test_dispatch_admits_and_releases_slot(fake_redis, monkeypatch):
    monkeypatch.setattr(guard.settings, "llm_user_max_concurrent_runs", 1)
    repo = _FakeRepo()
    monkeypatch.setattr(research_service, "ResearchRepository", lambda: repo)
    monkeypatch.setattr(research_service.job_queue, "enqueue_research", lambda rid: True)

    run = research_service.create_research(
        organization_id="org", user_id="user-1", question="why?", config={}
    )
    assert run["status"] == "queued"
    assert fake_redis.smembers(guard._run_set_key("user-1")) == {"run-1"}

    # Worker finished → slot released (mirrors run_research's finally).
    guard.release_run_slot("user-1", "run-1")
    assert fake_redis.smembers(guard._run_set_key("user-1")) == set()


# --- input guardrail: config sanitization ----------------------------------------

def test_sanitize_config_clamps_and_whitelists():
    safe = research_service.sanitize_research_config(
        {
            "top_k": 999,          # clamped to 50
            "max_subquestions": -5,  # clamped to 1
            "max_iterations": 3,    # kept
            "max_chunks": 200,      # kept
            "model": "gpt-4",       # dropped: not an allowed key
            "budget": 10**9,        # dropped
            "top_k2": 1,            # dropped
            "max_iterations": "x",  # invalid → dropped (last write wins)
        }
    )
    assert safe == {"top_k": 50, "max_subquestions": 1, "max_chunks": 200}


# --- per-run token budget -----------------------------------------------------------

def test_run_budget_stops_further_calls(monkeypatch, fake_redis):
    calls = []

    def fake_chat(messages, **kwargs):
        calls.append(len(messages))
        usage = kwargs.get("usage_out")
        if usage is not None:
            usage.update({"input": 10, "output": 20, "total": 30})
        return "ok"

    monkeypatch.setattr(graph_mod.llm_mod, "chat", fake_chat)

    from app.agents.state import ResearchState

    state = ResearchState(
        research_id="r1", organization_id="org", user_id="u1",
        original_query="q", config={"run_token_budget": 60},
    )
    llm_with_budget = graph_mod._make_budgeted_llm(state)

    assert llm_with_budget([{"role": "user", "content": "a"}]) == "ok"   # 30 used
    assert llm_with_budget([{"role": "user", "content": "b"}]) == "ok"   # 60 used
    with pytest.raises(BudgetExhaustedError, match="budget of 60"):
        llm_with_budget([{"role": "user", "content": "c"}])
    assert len(calls) == 2  # the third call never reached the model

    # Real usage was accounted against the user's quota too.
    usage = guard.user_token_usage("u1")
    assert usage["hourly"]["used"] == 60


def test_run_budget_zero_is_unlimited(monkeypatch):
    def fake_chat(messages, **kwargs):
        usage = kwargs.get("usage_out")
        if usage is not None:
            usage.update({"total": 10**9})
        return "ok"

    monkeypatch.setattr(graph_mod.llm_mod, "chat", fake_chat)

    from app.agents.state import ResearchState

    state = ResearchState(
        research_id="r1", organization_id="org", user_id="u1",
        original_query="q", config={"run_token_budget": 0},
    )
    llm_with_budget = graph_mod._make_budgeted_llm(state)
    for _ in range(3):
        assert llm_with_budget([{"role": "user", "content": "a"}]) == "ok"


# --- output guardrail: report length cap -------------------------------------------

def test_report_length_capped(monkeypatch):
    from app.agents.context import ResearchServices
    from app.agents.nodes.finalizer import finalizer_node
    from app.agents.state import ResearchState

    monkeypatch.setattr(graph_mod.settings, "research_max_report_chars", 50)

    state = ResearchState(
        research_id="r1",
        organization_id="org",
        user_id="u1",
        original_query="q",
        config={},
        draft="#" + " A" * 100 + "\nsecond line is here",
    )
    services = ResearchServices(
        llm=lambda m: "", retrieve=lambda *a, **k: [], config={}
    )
    state = finalizer_node(state, services)

    # The report body is capped at the limit; a visible marker is appended.
    body = state.final_report.split("\n\n> _Note:")[0]
    assert len(body) <= 50
    assert "truncated" in state.final_report
    assert "second line" not in state.final_report
    assert state.status == "completed"
