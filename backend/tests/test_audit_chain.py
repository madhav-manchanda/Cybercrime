"""Audit chain integrity: every event is SHA-256 hash-linked to its parent."""

from __future__ import annotations

from app.core.enums import AuditAction
from app.services.audit_service import audit_service
from app.utils.hashing import audit_chain_hash


async def test_chain_is_hash_linked(db_session: object) -> None:
    session = db_session
    e1 = await audit_service.record(session, action=AuditAction.USER_CREATE, actor_email="a@x.com")
    e2 = await audit_service.record(session, action=AuditAction.LOGIN, actor_email="a@x.com")
    e3 = await audit_service.record(session, action=AuditAction.CASE_CREATE, actor_email="a@x.com")
    assert e1.prev_hash is None
    assert e2.prev_hash == e1.hash, "second event must chain to the first"
    assert e3.prev_hash == e2.hash, "third event must chain to the second"
    assert e3.hash != e2.hash


async def test_verify_chain_reports_ok(db_session: object) -> None:
    session = db_session
    await audit_service.record(session, action=AuditAction.USER_CREATE, actor_email="a@x.com")
    await audit_service.record(session, action=AuditAction.LOGIN, actor_email="a@x.com")
    ok, message = await audit_service.verify_chain(session)
    assert ok is True, message


async def test_tamper_is_detected(db_session: object) -> None:
    session = db_session
    first = await audit_service.record(session, action=AuditAction.USER_CREATE, actor_email="a@x.com")
    await audit_service.record(session, action=AuditAction.LOGIN, actor_email="a@x.com")
    # Tamper with the middle link: change the parent's stored hash.
    first.hash = audit_chain_hash({"action": "forged"}, prev_hash=None)
    ok, message = await audit_service.verify_chain(session)
    assert ok is False
    assert message