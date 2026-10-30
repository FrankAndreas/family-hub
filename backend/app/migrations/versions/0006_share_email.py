"""Apps that may see their people's confirmed e-mail addresses (2026-10-30)."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tiles") as batch:
        batch.add_column(sa.Column("share_email", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("tiles") as batch:
        batch.drop_column("share_email")
