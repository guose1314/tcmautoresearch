"""add_learning_insights_table

Revision ID: e7f9a1b2c3d4
Revises: d8e1f2a3b4c5
Create Date: 2026-05-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f9a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        from sqlalchemy.dialects.postgresql import JSONB

        json_type = JSONB
    else:
        json_type = sa.JSON  # type: ignore[assignment]

    op.create_table(
        "learning_insights",
        sa.Column("insight_id", sa.String(length=128), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("target_phase", sa.String(length=64), nullable=False),
        sa.Column("insight_type", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("evidence_refs_json", json_type, nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=is_postgres), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_learning_insights_confidence",
        ),
        sa.PrimaryKeyConstraint("insight_id"),
    )
    op.create_index("idx_learning_insights_source", "learning_insights", ["source"])
    op.create_index(
        "idx_learning_insights_phase_status",
        "learning_insights",
        ["target_phase", "status"],
    )
    op.create_index("idx_learning_insights_type", "learning_insights", ["insight_type"])
    op.create_index(
        "idx_learning_insights_expires", "learning_insights", ["expires_at"]
    )
    op.create_index(
        "idx_learning_insights_created", "learning_insights", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_learning_insights_created", table_name="learning_insights")
    op.drop_index("idx_learning_insights_expires", table_name="learning_insights")
    op.drop_index("idx_learning_insights_type", table_name="learning_insights")
    op.drop_index("idx_learning_insights_phase_status", table_name="learning_insights")
    op.drop_index("idx_learning_insights_source", table_name="learning_insights")
    op.drop_table("learning_insights")
