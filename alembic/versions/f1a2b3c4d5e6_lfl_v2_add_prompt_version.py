"""lfl_v2: add prompt_version + schema_version to research_learning_feedback

Revision ID: f1a2b3c4d5e6
Revises: c7e9a32d8b54
Create Date: 2026-04-28 00:00:00.000000

T2.2 — research-feedback-library 升级到 v2，反馈条目可定位到具体 prompt 版本。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "c7e9a32d8b54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add prompt_version & schema_version columns (nullable, no backfill)."""
    op.add_column(
        "research_learning_feedback",
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "research_learning_feedback",
        sa.Column("schema_version", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    """Drop prompt_version & schema_version columns."""
    op.drop_column("research_learning_feedback", "schema_version")
    op.drop_column("research_learning_feedback", "prompt_version")
