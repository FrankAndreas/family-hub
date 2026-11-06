"""When each person first and last used an app: only a parent who used it is protected against another parent."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing access starts unused: an app asks for its key with the person's login on their next page
    with op.batch_alter_table("tile_access") as batch:
        batch.add_column(sa.Column("first_used_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("last_used_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tile_access") as batch:
        batch.drop_column("last_used_at")
        batch.drop_column("first_used_at")
