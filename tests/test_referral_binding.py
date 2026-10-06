import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from core.security_tokens import (
    TELEGRAM_BINDING_TOKEN_TTL_SECONDS,
    create_telegram_binding_token,
    is_telegram_binding_token_valid,
)
from database.models import Partner
from services.partner_service import PartnerService
from tg_handlers import start
from web import app as web_app


def seed_roots(session_factory):
    session = session_factory()
    roots = [
        Partner(first_name="Root 1", lineage=[]),
        Partner(first_name="Root 2", lineage=[]),
    ]
    session.add_all(roots)
    session.commit()
    root_ids = [root.id for root in roots]
    session.close()
    return root_ids


def make_update(telegram_id, text, first_name="Telegram User"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=telegram_id,
            username=f"user_{telegram_id}",
            first_name=first_name,
        ),
        message=SimpleNamespace(
            text=text,
            reply_text=AsyncMock(),
        ),
    )


def test_registration_referral_is_partner_id_and_binding_token_is_distinct(
    isolated_database,
):
    root_ids = seed_roots(isolated_database)

    response = asyncio.run(
        web_app.register_user(
            request=Mock(),
            first_name="Referral",
            last_name="Partner",
            email="referral@example.test",
            phone="+10000000001",
            ref=str(root_ids[0]),
            consent="on",
        )
    )
    token_match = re.search(r"start=([A-Za-z0-9_.-]+)", response.body.decode())
    assert token_match
    binding_token = token_match.group(1)
    assert binding_token != str(root_ids[0])
    assert is_telegram_binding_token_valid(binding_token)

    session = isolated_database()
    try:
        partner = session.query(Partner).filter_by(
            email="referral@example.test"
        ).one()
        assert partner.upline_id == root_ids[0]
        assert partner.lineage == [root_ids[0]]
        assert partner.telegram_link_code == binding_token
        assert partner.consent_given is True
        assert partner.consent_version == "v.1.0 21.04.2026"
        assert partner.consent_date is not None
    finally:
        session.close()


def test_registration_rejects_unknown_referral(isolated_database):
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            web_app.register_user(
                request=Mock(),
                first_name="Bad",
                last_name="Referral",
                email="bad-referral@example.test",
                phone="+10000000002",
                ref="999999",
                consent="on",
            )
        )

    assert exc_info.value.status_code == 400


def test_registration_requires_consent_on_server(isolated_database):
    root_ids = seed_roots(isolated_database)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            web_app.register_user(
                request=Mock(),
                first_name="No",
                last_name="Consent",
                email="no-consent@example.test",
                phone="+10000000004",
                ref=str(root_ids[0]),
                consent=None,
            )
        )

    assert exc_info.value.status_code == 400
    session = isolated_database()
    try:
        assert session.query(Partner).filter_by(
            email="no-consent@example.test"
        ).count() == 0
    finally:
        session.close()


def test_partner_service_rejects_unknown_upline(isolated_database):
    seed_roots(isolated_database)

    with pytest.raises(ValueError, match="Реферальный партнёр не найден"):
        PartnerService().create_partner(
            telegram_id=None,
            upline_id=999999,
        )


def test_telegram_binding_token_is_one_time_and_cleared(isolated_database):
    root_ids = seed_roots(isolated_database)
    asyncio.run(
        web_app.register_user(
            request=Mock(),
            first_name="Binding",
            last_name="Partner",
            email="binding@example.test",
            phone="+10000000003",
            ref=str(root_ids[0]),
            consent="on",
        )
    )

    session = isolated_database()
    partner = session.query(Partner).filter_by(
        email="binding@example.test"
    ).one()
    token = partner.telegram_link_code
    partner_id = partner.id
    session.close()

    first_update = make_update(101, f"/start {token}")
    asyncio.run(start.start_handler(first_update, Mock()))

    session = isolated_database()
    try:
        partner = session.get(Partner, partner_id)
        assert partner.telegram_id == "101"
        assert partner.telegram_link_code is None
    finally:
        session.close()

    replay_update = make_update(202, f"/start {token}")
    asyncio.run(start.start_handler(replay_update, Mock()))

    session = isolated_database()
    try:
        assert session.get(Partner, partner_id).telegram_id == "101"
    finally:
        session.close()
    assert "уже использован" in replay_update.message.reply_text.await_args.args[0]


def test_expired_binding_token_is_rejected_and_cleared(isolated_database):
    issued_at = 1_000_000
    token = create_telegram_binding_token(now=issued_at)
    assert not is_telegram_binding_token_valid(
        token,
        now=issued_at + TELEGRAM_BINDING_TOKEN_TTL_SECONDS + 1,
    )

    session = isolated_database()
    partner = Partner(
        first_name="Expired",
        telegram_link_code=token,
    )
    session.add(partner)
    session.commit()
    partner_id = partner.id
    session.close()

    update = make_update(303, f"/start {token}")
    asyncio.run(start.start_handler(update, Mock()))

    session = isolated_database()
    try:
        assert session.get(Partner, partner_id).telegram_link_code is None
    finally:
        session.close()
    assert "истёк" in update.message.reply_text.await_args.args[0]


def test_binding_token_rejects_second_partner_for_same_telegram(isolated_database):
    session = isolated_database()
    first = Partner(first_name="First", telegram_id="404")
    second = Partner(
        first_name="Second",
        telegram_link_code=create_telegram_binding_token(),
    )
    session.add_all([first, second])
    session.commit()
    second_id = second.id
    token = second.telegram_link_code
    session.close()

    update = make_update(404, f"/start {token}")
    asyncio.run(start.start_handler(update, Mock()))

    session = isolated_database()
    try:
        second = session.get(Partner, second_id)
        assert second.telegram_id is None
        assert second.telegram_link_code == token
    finally:
        session.close()
    assert "уже привязан" in update.message.reply_text.await_args.args[0]
