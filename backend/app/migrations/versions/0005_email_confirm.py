"""An e-mail address counts only once a link mailed to it was opened (security review 2026-10-30). Addresses from
before stay as they are."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("people") as batch:
        batch.add_column(sa.Column("email_pending", sa.String(254)))
    op.create_table(
        "email_confirms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime()),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_email_confirms_person_id_people", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_email_confirms"),
        sa.UniqueConstraint("token_hash", name="uq_email_confirms_token_hash"),
    )


def downgrade() -> None:
    op.drop_table("email_confirms")
    with op.batch_alter_table("people") as batch:
        batch.drop_column("email_pending")
