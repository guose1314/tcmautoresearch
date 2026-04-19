"""add_research_learning_feedback_table

Revision ID: a1b2c3d4e5f6
Revises: e4c6d2b7a9f1
Create Date: 2026-04-19 10:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

import src.infrastructure.persistence
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "e4c6d2b7a9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create research_learning_feedback table."""
    op.create_table(
        "research_learning_feedback",
        sa.Column("id", src.infrastructure.persistence.GUID(), nullable=False),
        sa.Column(
            "session_id",
            src.infrastructure.persistence.GUID(),
            nullable=False,
        ),
        sa.Column("cycle_id", sa.String(length=128), nullable=False),
        sa.Column(
            "phase_execution_id",
            src.infrastructure.persistence.GUID(),
            nullable=True,
        ),
        sa.Column("feedback_scope", sa.String(length=64), nullable=False),
        sa.Column(
            "source_phase",
            sa.String(length=64),
            nullable=False,
            server_default="reflect",
        ),
        sa.Column("target_phase", sa.String(length=64), nullable=True),
        sa.Column(
            "feedback_status",
            sa.String(length=64),
            nullable=False,
            server_default="tracked",
        ),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("grade_level", sa.String(length=64), nullable=True),
        sa.Column("cycle_trend", sa.String(length=64), nullable=True),
        sa.Column("issue_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weakness_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strength_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "strategy_changed", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("strategy_before_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("strategy_after_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("recorded_phase_names", sa.JSON(), nullable=False),
        sa.Column("weak_phase_names", sa.JSON(), nullable=False),
        sa.Column(
            "quality_dimensions_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "issues_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "improvement_priorities_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "replay_feedback_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["research_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["phase_execution_id"],
            ["phase_executions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rlf_cycle", "research_learning_feedback", ["cycle_id"])
    op.create_index(
        "idx_rlf_cycle_scope",
        "research_learning_feedback",
        ["cycle_id", "feedback_scope"],
    )
    op.create_index(
        "idx_rlf_target_phase", "research_learning_feedback", ["target_phase"]
    )
    op.create_index("idx_rlf_created", "research_learning_feedback", ["created_at"])


def downgrade() -> None:
    """Drop research_learning_feedback table."""
    op.drop_index("idx_rlf_created", table_name="research_learning_feedback")
    op.drop_index("idx_rlf_target_phase", table_name="research_learning_feedback")
    op.drop_index("idx_rlf_cycle_scope", table_name="research_learning_feedback")
    op.drop_index("idx_rlf_cycle", table_name="research_learning_feedback")
    op.drop_table("research_learning_feedback")
