"""Who may use which app: an app key per tile and the people per tile (spec 2026-10-30, part A)."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tiles") as batch:
        batch.add_column(sa.Column("app_key", sa.String(20)))
        batch.create_unique_constraint("uq_tiles_app_key", ["app_key"])
    op.create_table(
        "tile_access",
        sa.Column("tile_id", sa.Integer(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tile_id"], ["tiles.id"], name="fk_tile_access_tile_id_tiles", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_tile_access_person_id_people", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("tile_id", "person_id", name="pk_tile_access"),
    )


def downgrade() -> None:
    op.drop_table("tile_access")
    with op.batch_alter_table("tiles") as batch:
        batch.drop_constraint("uq_tiles_app_key", type_="unique")
        batch.drop_column("app_key")
