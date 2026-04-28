"""T4.1: 新增 external_evidence 表（外校命中证据）

Revision ID: c2d3e4f5a6b8
Revises: b9f2c3a4d5e7
Create Date: 2026-04-28 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c2d3e4f5a6b8"
down_revision = "b9f2c3a4d5e7"
branch_labels = None
depends_on = None


def _guid_type():
    return sa.CHAR(36)


def upgrade() -> None:
    op.create_table(
        "external_evidence",
        sa.Column("id", _guid_type(), primary_key=True),
        sa.Column("document_id", _guid_type(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("authors_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("citation_count", sa.Integer(), nullable=True),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "fetched_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "document_id",
            "source",
            "external_id",
            name="uq_external_evidence_doc_source_extid",
        ),
    )
    op.create_index(
        "idx_ext_evidence_document", "external_evidence", ["document_id"]
    )
    op.create_index(
        "idx_ext_evidence_source", "external_evidence", ["source"]
    )


def downgrade() -> None:
    op.drop_index("idx_ext_evidence_source", table_name="external_evidence")
    op.drop_index("idx_ext_evidence_document", table_name="external_evidence")
    op.drop_table("external_evidence")
