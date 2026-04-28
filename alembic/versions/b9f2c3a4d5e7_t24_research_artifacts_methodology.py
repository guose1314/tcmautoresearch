"""T2.4: research_artifacts 加 methodology_tag / evidence_grade 列

Revision ID: b9f2c3a4d5e7
Revises: a8c4e5d6f7b9
Create Date: 2026-04-26 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b9f2c3a4d5e7"
down_revision = "a8c4e5d6f7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "sqlite":
        with op.batch_alter_table("research_artifacts") as batch_op:
            batch_op.add_column(
                sa.Column("methodology_tag", sa.String(length=32), nullable=True)
            )
            batch_op.add_column(
                sa.Column("evidence_grade", sa.String(length=2), nullable=True)
            )
    else:
        op.add_column(
            "research_artifacts",
            sa.Column("methodology_tag", sa.String(length=32), nullable=True),
        )
        op.add_column(
            "research_artifacts",
            sa.Column("evidence_grade", sa.String(length=2), nullable=True),
        )
    op.create_index(
        "idx_ra_methodology_tag",
        "research_artifacts",
        ["methodology_tag"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_ra_methodology_tag", table_name="research_artifacts")
    bind = op.get_bind()
    dialect = bind.dialect.name if bind is not None else ""
    if dialect == "sqlite":
        with op.batch_alter_table("research_artifacts") as batch_op:
            batch_op.drop_column("evidence_grade")
            batch_op.drop_column("methodology_tag")
    else:
        op.drop_column("research_artifacts", "evidence_grade")
        op.drop_column("research_artifacts", "methodology_tag")
