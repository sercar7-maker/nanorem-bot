"""Explicit offline contact preparation; no startup hook or commit."""

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from database.models import Partner
from database.models_cabinet import CabinetOwner, CabinetPosition
from database.models_cabinet_contacts import CabinetContact
from services.auth_service import normalize_identifier


class CabinetContactMigrationError(ValueError):
    """Unsafe source data; messages do not expose raw contacts."""


def create_cabinet_contacts_schema(engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table in (
            "partners",
            "cabinet_owners",
            "cabinet_positions",
        ):
            if not inspector.has_table(table):
                raise RuntimeError(
                    f"Required table is missing: {table}"
                )

        CabinetContact.__table__.create(
            connection,
            checkfirst=True,
        )


def backfill_cabinet_contacts(session: Session) -> int:
    """Copy primary contacts as unverified; caller commits or rolls back.

    Ownership preparation must be complete. Validate all positions before
    inserting contacts. Run offline without concurrent writers, first on
    a reviewed database copy. Never overwrite existing contacts.
    """
    with session.begin_nested():
        owners = {
            owner.id: owner
            for owner in session.query(CabinetOwner).all()
        }
        positions = {
            position.partner_id: position.owner_id
            for position in session.query(CabinetPosition).all()
        }
        partners = {
            partner.id: partner
            for partner in session.query(Partner).all()
        }

        for owner_id, owner in owners.items():
            if (
                owner.primary_partner_id not in partners
                or positions.get(owner.primary_partner_id) != owner_id
            ):
                raise CabinetContactMigrationError(
                    f"Invalid primary position for owner {owner_id}"
                )

        claims = {}
        candidates = {}

        for partner_id, partner in sorted(partners.items()):
            owner_id = positions.get(partner_id)
            if owner_id not in owners:
                raise CabinetContactMigrationError(
                    f"Missing ownership for partner {partner_id}"
                )

            for channel in ("email", "phone"):
                raw_value = getattr(partner, channel)
                if raw_value is None or not raw_value.strip():
                    continue

                try:
                    value = normalize_identifier(raw_value, channel)
                except ValueError:
                    raise CabinetContactMigrationError(
                        f"Invalid {channel} on partner {partner_id}"
                    ) from None

                key = (channel, value)
                previous_owner = claims.setdefault(key, owner_id)
                if previous_owner != owner_id:
                    raise CabinetContactMigrationError(
                        f"Conflicting {channel} on partner {partner_id}"
                    )

                if owners[owner_id].primary_partner_id == partner_id:
                    candidates[key] = owner_id

        existing = {}
        for contact in session.query(CabinetContact).all():
            key = (contact.channel, contact.normalized_value)
            claimed_owner = claims.get(key)

            if (
                claimed_owner is not None
                and claimed_owner != contact.owner_id
            ):
                raise CabinetContactMigrationError(
                    f"Existing {contact.channel} conflicts "
                    "with partner ownership"
                )

            existing[key] = contact

        created = 0
        for (channel, value), owner_id in sorted(candidates.items()):
            if (channel, value) in existing:
                continue

            session.add(
                CabinetContact(
                    owner_id=owner_id,
                    channel=channel,
                    normalized_value=value,
                    verified_at=None,
                )
            )
            created += 1

        session.flush()

    return created