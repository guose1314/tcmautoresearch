"""add canonical document identity fields

Revision ID: f6a7b8c9d0e1
Revises: e7f9a1b2c3d4
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e7f9a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(
            sa.Column("canonical_document_key", sa.String(length=128), nullable=True)
        )
        batch.add_column(
            sa.Column("canonical_title", sa.String(length=500), nullable=True)
        )
        batch.add_column(
            sa.Column("normalized_title", sa.String(length=500), nullable=True)
        )
        batch.add_column(
            sa.Column("source_file_hash", sa.CHAR(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("edition_hint", sa.String(length=255), nullable=True)
        )
        batch.add_column(
            sa.Column("document_key_version", sa.String(length=32), nullable=True)
        )
        batch.create_index("idx_documents_canonical_key", ["canonical_document_key"])
        batch.create_index("idx_documents_normalized_title", ["normalized_title"])
        batch.create_index("idx_documents_source_file_hash", ["source_file_hash"])
        batch.create_unique_constraint(
            "uq_documents_canonical_document_key", ["canonical_document_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("uq_documents_canonical_document_key", type_="unique")
        batch.drop_index("idx_documents_source_file_hash")
        batch.drop_index("idx_documents_normalized_title")
        batch.drop_index("idx_documents_canonical_key")
        batch.drop_column("document_key_version")
        batch.drop_column("edition_hint")
        batch.drop_column("source_file_hash")
        batch.drop_column("normalized_title")
        batch.drop_column("canonical_title")
        batch.drop_column("canonical_document_key")
