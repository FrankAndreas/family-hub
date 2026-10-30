"""People and the start page's tiles."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("name_key", sa.String(50), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("pin_hash", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("PARENT", "CHILD", name="role"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("language", sa.String(2)),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("lockouts", sa.Integer(), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("name_key", name="uq_people_name_key"),
        sa.UniqueConstraint("email", name="uq_people_email"),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "tiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("icon", sa.String(16), nullable=False),
        sa.Column("local_url", sa.String(300), nullable=False),
        sa.Column("remote_url", sa.String(300)),
        sa.Column("position", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("tiles")
    op.drop_table("people")
