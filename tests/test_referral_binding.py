import asyncio
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from core.security_tokens import (
    TELEGRAM_BINDING_TOKEN_TTL_SECONDS,
    create_telegram_binding_token,
    is_telegram_binding_token_valid,
)
from database.models import Partner
from services.partner_service import PartnerService
from tg_handlers import start
from tg_handlers import handlers
from web import app as web_app
from web import order_handler


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


def get_referral_code(session_factory, partner_id):
    session = session_factory()
    try:
        return session.get(Partner, partner_id).referral_code
    finally:
        session.close()


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


def test_registration_referral_uses_referral_code_and_binding_token_is_distinct(
    isolated_database,
):
    root_ids = seed_roots(isolated_database)
    root_referral_code = get_referral_code(
        isolated_database,
        root_ids[0],
    )

    response = asyncio.run(
        web_app.register_user(
            request=Mock(),
            first_name="Referral",
            last_name="Partner",
            email=" Referral@Example.Test ",
            phone="+10000000001",
            ref=root_referral_code,
            consent="on",
        )
    )
    token_match = re.search(r"start=([A-Za-z0-9_.-]+)", response.body.decode())
    assert token_match
    binding_token = token_match.group(1)
    assert binding_token != root_referral_code
    assert is_telegram_binding_token_valid(binding_token)

    session = isolated_database()
    try:
        partner = session.query(Partner).filter_by(
            email="referral@example.test"
        ).one()
        assert partner.upline_id == root_ids[0]
        assert partner.lineage == [root_ids[0]]
        assert partner.telegram_link_code == binding_token
        assert partner.referral_code
        assert partner.referral_code != str(partner.id)
        assert partner.referral_code != partner.telegram_link_code
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
                ref="unknown-referral-code",
                consent="on",
            )
        )

    assert exc_info.value.status_code == 400


def test_registration_requires_consent_on_server(isolated_database):
    root_ids = seed_roots(isolated_database)
    root_referral_code = get_referral_code(
        isolated_database,
        root_ids[0],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            web_app.register_user(
                request=Mock(),
                first_name="No",
                last_name="Consent",
                email="no-consent@example.test",
                phone="+10000000004",
                ref=root_referral_code,
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

    with pytest.raises(ValueError, match="Referral partner not found"):
        PartnerService().create_partner(
            telegram_id=None,
            upline_id=999999,
        )


def test_referral_codes_are_unique_and_generated_for_roots_and_partners(
    isolated_database,
):
    root_ids = seed_roots(isolated_database)
    first_code, second_code = (
        get_referral_code(isolated_database, partner_id)
        for partner_id in root_ids
    )
    assert first_code
    assert second_code
    assert first_code != second_code

    partner = PartnerService().create_partner(
        telegram_id=None,
        upline_id=root_ids[0],
        first_name="Automatically coded partner",
    )
    assert partner.referral_code
    assert partner.referral_code not in {first_code, second_code}

    session = isolated_database()
    duplicate = Partner(
        first_name="Duplicate referral code",
        referral_code=partner.referral_code,
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
    session.close()


def test_referral_code_can_be_reused_for_multiple_registrations(
    isolated_database,
):
    root_ids = seed_roots(isolated_database)
    root_code = get_referral_code(isolated_database, root_ids[0])

    for name, email in (
        ("First referred", "first-referred@example.test"),
        ("Second referred", "second-referred@example.test"),
    ):
        asyncio.run(
            web_app.register_user(
                request=Mock(),
                first_name=name,
                last_name="Partner",
                email=email,
                phone="",
                ref=root_code,
                consent="on",
            )
        )

    session = isolated_database()
    try:
        referred = session.query(Partner).filter(
            Partner.email.in_(
                ["first-referred@example.test", "second-referred@example.test"]
            )
        ).all()
        assert len(referred) == 2
        assert {partner.upline_id for partner in referred} == {root_ids[0]}
        assert all(partner.referral_code != root_code for partner in referred)
    finally:
        session.close()


def test_numeric_partner_id_is_not_a_referral_code(isolated_database):
    root_ids = seed_roots(isolated_database)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            web_app.register_user(
                request=Mock(),
                first_name="Legacy numeric referral",
                last_name="Rejected",
                email="legacy-numeric@example.test",
                phone="",
                ref=str(root_ids[0]),
                consent="on",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Referral code not found"


def test_admin_referral_link_uses_referral_code(isolated_database):
    root_ids = seed_roots(isolated_database)
    session = isolated_database()
    try:
        result = order_handler.get_referral_link(root_ids[0], session)
        referral_code = session.get(Partner, root_ids[0]).referral_code
        assert result["referral_code"] == referral_code
        assert result["referral_link"] == (
            f"https://nanorvs.ru/register?ref={referral_code}"
        )
        assert result["referral_link"] != (
            f"https://nanorvs.ru/register?ref={root_ids[0]}"
        )
    finally:
        session.close()


def test_telegram_referral_button_uses_referral_code(
    isolated_database,
    monkeypatch,
):
    monkeypatch.setattr(handlers, "SessionLocal", isolated_database)
    telegram_id = 918273
    session = isolated_database()
    partner = Partner(
        first_name="Telegram referrer",
        telegram_id=str(telegram_id),
    )
    session.add(partner)
    session.commit()
    partner_id = partner.id
    referral_code = partner.referral_code
    session.close()
    update = make_update(telegram_id, "🔗 Реферальная ссылка")

    asyncio.run(handlers.button_handler(update, Mock()))

    message = update.message.reply_text.await_args.args[0]
    assert f"https://nanorvs.ru/register?ref={referral_code}" in message
    assert f"https://nanorvs.ru/register?ref={partner_id}" not in message


def test_telegram_binding_token_is_one_time_and_cleared(isolated_database):
    root_ids = seed_roots(isolated_database)
    root_referral_code = get_referral_code(
        isolated_database,
        root_ids[0],
    )
    asyncio.run(
        web_app.register_user(
            request=Mock(),
            first_name="Binding",
            last_name="Partner",
            email="binding@example.test",
            phone="+10000000003",
            ref=root_referral_code,
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
