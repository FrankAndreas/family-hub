"""The AUD tag of an app's Cloudflare Access application: its Cloudflare logins count only for it (hub#12)."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tiles") as batch:
        batch.add_column(sa.Column("cf_audience", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tiles") as batch:
        batch.drop_column("cf_audience")
