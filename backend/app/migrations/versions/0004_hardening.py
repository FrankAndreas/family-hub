"""Logins that ended with "Log out", PIN reset links, and everyone logged out once: older tokens have no id
(spec 2026-10-30 hub hardening)."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ended_logins",
        sa.Column("jti", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("jti", name="pk_ended_logins"),
    )
    op.create_table(
        "pin_resets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_pin_resets_person_id_people", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pin_resets"),
        sa.UniqueConstraint("token_hash", name="uq_pin_resets_token_hash"),
    )
    # Tokens from before carry no id, so "Log out" couldn't end them: every login ends once
    op.execute("UPDATE people SET token_version = token_version + 1")


def downgrade() -> None:
    op.drop_table("pin_resets")
    op.drop_table("ended_logins")
