"""add_document_version_lineage_fields

Revision ID: e4c6d2b7a9f1
Revises: d6c8f52a1b2e
Create Date: 2026-04-14 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4c6d2b7a9f1"
down_revision: Union[str, Sequence[str], None] = "d6c8f52a1b2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("document_urn", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("document_title", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("source_type", sa.String(length=64), nullable=True))
    op.add_column("documents", sa.Column("catalog_id", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("work_title", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("fragment_title", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("work_fragment_key", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("version_lineage_key", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("witness_key", sa.String(length=500), nullable=True))
    op.add_column("documents", sa.Column("dynasty", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("author", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("edition", sa.String(length=255), nullable=True))
    op.add_column("documents", sa.Column("version_metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))

    op.create_index("idx_documents_urn", "documents", ["document_urn"], unique=False)
    op.create_index("idx_documents_catalog_id", "documents", ["catalog_id"], unique=False)
    op.create_index("idx_documents_lineage", "documents", ["version_lineage_key"], unique=False)
    op.create_index("idx_documents_work_fragment", "documents", ["work_fragment_key"], unique=False)
    op.create_index("idx_documents_witness", "documents", ["witness_key"], unique=False)

    op.alter_column("documents", "version_metadata_json", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_documents_witness", table_name="documents")
    op.drop_index("idx_documents_work_fragment", table_name="documents")
    op.drop_index("idx_documents_lineage", table_name="documents")
    op.drop_index("idx_documents_catalog_id", table_name="documents")
    op.drop_index("idx_documents_urn", table_name="documents")

    op.drop_column("documents", "version_metadata_json")
    op.drop_column("documents", "edition")
    op.drop_column("documents", "author")
    op.drop_column("documents", "dynasty")
    op.drop_column("documents", "witness_key")
    op.drop_column("documents", "version_lineage_key")
    op.drop_column("documents", "work_fragment_key")
    op.drop_column("documents", "fragment_title")
    op.drop_column("documents", "work_title")
    op.drop_column("documents", "catalog_id")
    op.drop_column("documents", "source_type")
    op.drop_column("documents", "document_title")
    op.drop_column("documents", "document_urn")