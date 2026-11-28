"""A theme per person (themes design 2026-11-28): None until they pick one, which means the default (Aurora)."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("people") as batch:
        batch.add_column(sa.Column("theme", sa.String(20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("people") as batch:
        batch.drop_column("theme")
