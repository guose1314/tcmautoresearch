"""add_review_disputes_table

Revision ID: c7e9a32d8b54
Revises: b5d8a91e3c47
Create Date: 2026-04-22 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

import src.infrastructure.persistence
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e9a32d8b54"
down_revision: Union[str, Sequence[str], None] = "b5d8a91e3c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create review_disputes table (Phase H-3 dispute archive)."""
    op.create_table(
        "review_disputes",
        sa.Column("id", src.infrastructure.persistence.GUID(), nullable=False),
        sa.Column(
            "session_id",
            src.infrastructure.persistence.GUID(),
            nullable=False,
        ),
        sa.Column("cycle_id", sa.String(length=128), nullable=False),
        sa.Column("case_id", sa.String(length=64), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("asset_key", sa.String(length=255), nullable=False),
        sa.Column(
            "dispute_status",
            sa.String(length=32),
            nullable=False,
            server_default="open",
        ),
        sa.Column("resolution", sa.String(length=32), nullable=True),
        sa.Column("opened_by", sa.String(length=255), nullable=False),
        sa.Column("arbitrator", sa.String(length=255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("events_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_id", "case_id", name="uq_review_dispute_case"
        ),
    )
    op.create_index(
        "idx_rvd_session_status",
        "review_disputes",
        ["session_id", "dispute_status"],
    )
    op.create_index(
        "idx_rvd_cycle_status",
        "review_disputes",
        ["cycle_id", "dispute_status"],
    )
    op.create_index(
        "idx_rvd_arbitrator",
        "review_disputes",
        ["arbitrator", "dispute_status"],
    )
    op.create_index(
        "idx_rvd_target",
        "review_disputes",
        ["cycle_id", "asset_type", "asset_key"],
    )


def downgrade() -> None:
    op.drop_index("idx_rvd_target", table_name="review_disputes")
    op.drop_index("idx_rvd_arbitrator", table_name="review_disputes")
    op.drop_index("idx_rvd_cycle_status", table_name="review_disputes")
    op.drop_index("idx_rvd_session_status", table_name="review_disputes")
    op.drop_table("review_disputes")
