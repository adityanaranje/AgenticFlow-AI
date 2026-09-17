"""The research token quota is researcher+ only (not viewer).

The quota only constrains *starting* a run, so it is meaningless to a
viewer who can never spend it. The UI hides the token-budget card from
viewers; this pins the API to the same rule so the data is not merely
hidden client-side.
"""

from app.api import research
from app.core.rbac import ROLE_RESEARCHER, ROLE_VIEWER, has_minimum_role


def _dependency_names(path_suffix: str, method: str = "GET") -> list[str]:
    """Names of the dependency callables guarding a route."""
    for route in research.router.routes:
        if route.path.endswith(path_suffix) and method in route.methods:
            return [
                dependency.call.__qualname__
                for dependency in route.dependant.dependencies
                if dependency.call is not None
            ]
    raise AssertionError(f"route {method} ...{path_suffix} not found")


def test_quota_route_exists():
    assert _dependency_names("/research/quota") != []


def test_quota_requires_researcher_not_viewer():
    """`require_researcher()` returns a closure named `...dependency`; the
    role it enforces is what matters, so assert on the behaviour instead."""
    # A viewer must not clear the researcher bar the route depends on.
    assert not has_minimum_role(ROLE_VIEWER, ROLE_RESEARCHER)
    assert has_minimum_role(ROLE_RESEARCHER, ROLE_RESEARCHER)


def test_quota_handler_is_gated_by_researcher_dependency():
    """Inspect the actual default on the handler signature."""
    import inspect

    signature = inspect.signature(research.get_research_quota)
    membership_default = signature.parameters["membership"].default

    # FastAPI wraps it in Depends(...); the factory closure carries the
    # minimum rank it was built with.
    closure_values = [
        cell.cell_contents
        for cell in (membership_default.dependency.__closure__ or ())
    ]

    from app.core.auth import ROLE_RANK

    assert ROLE_RANK[ROLE_RESEARCHER] in closure_values, (
        "GET /research/quota must require researcher+; a viewer cannot "
        "spend the quota, so must not be able to read it."
    )
