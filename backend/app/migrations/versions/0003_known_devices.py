"""Browsers a person logged in with before: wrong PINs from elsewhere don't lock them (security review 2026-10-30)."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "known_devices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("secret_hash", sa.String(64), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_known_devices_person_id_people", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_known_devices"),
        sa.UniqueConstraint("person_id", "secret_hash", name="uq_known_devices_person_id"),
    )


def downgrade() -> None:
    op.drop_table("known_devices")
