"""Operator commands for inspecting permanent Roots and assigning admin.

Read-only unless ``grant --apply`` is passed. The command never selects a
Root by name, email, or Telegram id, and it never clears another admin role.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from database.models import Partner


class GrantRefused(RuntimeError):
    """The requested admin assignment does not meet the operator rules."""


def database_label(database_url: str) -> str:
    """Describe the connected database without credentials or the full URL."""
    url = make_url(database_url)
    backend = url.get_backend_name()
    if backend == "sqlite":
        path = url.database or ":memory:"
        return f"dialect=sqlite path={path}"
    return (
        f"dialect={backend} host={url.host or '-'} "
        f"database={url.database or '-'}"
    )


def permanent_roots(session: Session) -> list[Partner]:
    return (
        session.query(Partner)
        .filter(
            Partner.upline_id.is_(None),
            Partner.root_id == Partner.id,
        )
        .order_by(Partner.id)
        .all()
    )


def _status_text(partner: Partner) -> str:
    status = partner.status
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def format_root(partner: Partner) -> str:
    return (
        f"id={partner.id} "
        f"first_name={partner.first_name or ''} "
        f"last_name={partner.last_name or ''} "
        f"email={partner.email or ''} "
        f"phone={partner.phone or ''} "
        f"role={partner.role or ''} "
        f"status={_status_text(partner)}"
    )


def show_roots(session: Session, database_url: str) -> str:
    lines = [database_label(database_url)]
    roots = permanent_roots(session)
    lines.append(f"permanent_roots={len(roots)}")
    lines.extend(format_root(root) for root in roots)
    session.rollback()
    return "\n".join(lines)


def _other_admins(session: Session, partner_id: int) -> list[Partner]:
    return (
        session.query(Partner)
        .filter(
            Partner.role == "admin",
            Partner.id != partner_id,
        )
        .order_by(Partner.id)
        .all()
    )


def validate_grant(session: Session, partner_id: int) -> Partner:
    roots = permanent_roots(session)
    if len(roots) != 2:
        raise GrantRefused(
            f"Expected exactly 2 permanent Roots, found {len(roots)}"
        )
    partner = session.get(Partner, partner_id)
    if partner is None:
        raise GrantRefused(f"Partner {partner_id} was not found")
    if not partner.is_permanent_root:
        raise GrantRefused(
            f"Partner {partner_id} is not a permanent Root"
        )
    others = _other_admins(session, partner.id)
    if others:
        ids = ", ".join(str(item.id) for item in others)
        raise GrantRefused(
            f"Another partner already has role admin: {ids}"
        )
    return partner


def grant_admin(
    session: Session,
    partner_id: int,
    *,
    apply: bool,
) -> str:
    try:
        partner = validate_grant(session, partner_id)
        if partner.role == "admin":
            session.rollback()
            return f"Partner {partner.id} is already admin; no change"
        plan = (
            f"Partner {partner.id}: role {partner.role!r} -> 'admin'"
        )
        if not apply:
            session.rollback()
            return "dry-run: " + plan
        partner = validate_grant(session, partner_id)
        if partner.role == "admin":
            session.rollback()
            return f"Partner {partner.id} is already admin; no change"
        previous = partner.role
        partner.role = "admin"
        session.commit()
        return f"Updated partner {partner.id}: role {previous!r} -> 'admin'"
    except Exception:
        session.rollback()
        raise


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect permanent Root partners and assign admin to one "
            "existing Root. Grant is a dry-run unless --apply is set."
        )
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser(
        "show",
        help="List permanent Roots without changing the database",
    )

    grant = subcommands.add_parser(
        "grant",
        help="Plan or apply role=admin for one permanent Root",
    )
    grant.add_argument(
        "--partner-id",
        type=int,
        required=True,
        help="Existing permanent Root partner id",
    )
    grant.add_argument(
        "--apply",
        action="store_true",
        help="Write the role change. Without this flag the command is a dry-run",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    session_factory=None,
    database_url: str | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    if session_factory is None or database_url is None:
        from config import DATABASE_URL
        from database.db import SessionLocal

        session_factory = session_factory or SessionLocal
        database_url = database_url or DATABASE_URL

    session = session_factory()
    try:
        if args.command == "show":
            print(show_roots(session, database_url))
            return 0
        print(
            grant_admin(
                session,
                args.partner_id,
                apply=args.apply,
            )
        )
        return 0
    except GrantRefused as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"ROOT ADMIN FAILED: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
