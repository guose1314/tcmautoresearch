"""add_review_assignments_table

Revision ID: b5d8a91e3c47
Revises: a1b2c3d4e5f6
Create Date: 2026-04-21 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

import src.infrastructure.persistence
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5d8a91e3c47"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create review_assignments table."""
    op.create_table(
        "review_assignments",
        sa.Column("id", src.infrastructure.persistence.GUID(), nullable=False),
        sa.Column(
            "session_id",
            src.infrastructure.persistence.GUID(),
            nullable=False,
        ),
        sa.Column("cycle_id", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=64), nullable=False),
        sa.Column("asset_key", sa.String(length=255), nullable=False),
        sa.Column("assignee", sa.String(length=255), nullable=True),
        sa.Column(
            "queue_status",
            sa.String(length=32),
            nullable=False,
            server_default="unassigned",
        ),
        sa.Column(
            "priority_bucket",
            sa.String(length=16),
            nullable=False,
            server_default="medium",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("released_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("due_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "cycle_id",
            "asset_type",
            "asset_key",
            name="uq_review_assignment_target",
        ),
    )
    op.create_index(
        "idx_rva_session_status",
        "review_assignments",
        ["session_id", "queue_status"],
    )
    op.create_index(
        "idx_rva_assignee_status",
        "review_assignments",
        ["assignee", "queue_status"],
    )
    op.create_index(
        "idx_rva_cycle_status",
        "review_assignments",
        ["cycle_id", "queue_status"],
    )
    op.create_index("idx_rva_due_at", "review_assignments", ["due_at"])


def downgrade() -> None:
    """Drop review_assignments table."""
    op.drop_index("idx_rva_due_at", table_name="review_assignments")
    op.drop_index("idx_rva_cycle_status", table_name="review_assignments")
    op.drop_index("idx_rva_assignee_status", table_name="review_assignments")
    op.drop_index("idx_rva_session_status", table_name="review_assignments")
    op.drop_table("review_assignments")
