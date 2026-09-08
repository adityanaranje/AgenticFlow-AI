"""RBAC role-hierarchy tests (Phase 5, §24)."""

from app.core.rbac import (
    ROLE_ADMIN,
    ROLE_OWNER,
    ROLE_RESEARCHER,
    ROLE_VIEWER,
    ROLE_HIERARCHY,
    has_minimum_role,
)
from app.core.auth import ROLE_RANK


def test_hierarchy_order():
    assert ROLE_HIERARCHY == (ROLE_OWNER, ROLE_ADMIN, ROLE_RESEARCHER, ROLE_VIEWER)
    assert ROLE_RANK[ROLE_OWNER] > ROLE_RANK[ROLE_ADMIN] > ROLE_RANK[ROLE_RESEARCHER] > ROLE_RANK[ROLE_VIEWER]


def test_has_minimum_role():
    assert has_minimum_role(ROLE_OWNER, ROLE_VIEWER)
    assert has_minimum_role(ROLE_ADMIN, ROLE_RESEARCHER)
    assert has_minimum_role(ROLE_RESEARCHER, ROLE_RESEARCHER)
    assert not has_minimum_role(ROLE_VIEWER, ROLE_RESEARCHER)
    assert not has_minimum_role("", ROLE_VIEWER)
    assert not has_minimum_role(None, ROLE_VIEWER)
    assert not has_minimum_role("superuser", ROLE_VIEWER)  # unknown role denied
