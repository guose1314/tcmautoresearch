"""migrate learning insight lifecycle statuses

Revision ID: a2b4c6d8e9f0
Revises: f6a7b8c9d0e1
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b4c6d8e9f0"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE learning_insights SET status = 'accepted' WHERE status = 'reviewed'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE learning_insights SET status = 'reviewed' WHERE status = 'accepted'"
        )
    )
