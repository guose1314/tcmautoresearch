"""add edition lineage and variant readings

Revision ID: b3c4d5e6f7a8
Revises: a2b4c6d8e9f0
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

import src.infrastructure.persistence
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b4c6d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "edition_lineages",
        sa.Column("id", src.infrastructure.persistence.GUID(), nullable=False),
        sa.Column("document_id", src.infrastructure.persistence.GUID(), nullable=True),
        sa.Column("canonical_document_key", sa.String(length=128), nullable=False),
        sa.Column("version_lineage_key", sa.String(length=500), nullable=True),
        sa.Column("witness_key", sa.String(length=500), nullable=False),
        sa.Column("work_title", sa.String(length=500), nullable=True),
        sa.Column("fragment_title", sa.String(length=500), nullable=True),
        sa.Column("edition", sa.String(length=255), nullable=True),
        sa.Column("dynasty", sa.String(length=255), nullable=True),
        sa.Column("author", sa.String(length=255), nullable=True),
        sa.Column("source_ref", sa.String(length=1000), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),
        sa.Column("base_witness_key", sa.String(length=500), nullable=True),
        sa.Column("lineage_relation", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_document_key",
            "witness_key",
            name="uq_edition_lineage_canonical_witness",
        ),
    )
    op.create_index(
        "idx_edition_lineages_document", "edition_lineages", ["document_id"]
    )
    op.create_index(
        "idx_edition_lineages_canonical", "edition_lineages", ["canonical_document_key"]
    )
    op.create_index(
        "idx_edition_lineages_lineage", "edition_lineages", ["version_lineage_key"]
    )
    op.create_index("idx_edition_lineages_witness", "edition_lineages", ["witness_key"])
    op.alter_column("edition_lineages", "metadata_json", server_default=None)

    op.create_table(
        "variant_readings",
        sa.Column("id", src.infrastructure.persistence.GUID(), nullable=False),
        sa.Column("document_id", src.infrastructure.persistence.GUID(), nullable=True),
        sa.Column(
            "edition_lineage_id", src.infrastructure.persistence.GUID(), nullable=True
        ),
        sa.Column("variant_key", sa.String(length=64), nullable=False),
        sa.Column("canonical_document_key", sa.String(length=128), nullable=False),
        sa.Column("version_lineage_key", sa.String(length=500), nullable=True),
        sa.Column("witness_key", sa.String(length=500), nullable=True),
        sa.Column("base_witness_key", sa.String(length=500), nullable=True),
        sa.Column("segment_id", sa.String(length=128), nullable=True),
        sa.Column("position_label", sa.String(length=255), nullable=True),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("base_text", sa.Text(), nullable=True),
        sa.Column("variant_text", sa.Text(), nullable=False),
        sa.Column("normalized_meaning", sa.Text(), nullable=True),
        sa.Column("annotation", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(length=1000), nullable=True),
        sa.Column("evidence_ref", sa.String(length=1000), nullable=True),
        sa.Column(
            "evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["edition_lineage_id"], ["edition_lineages.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "canonical_document_key",
            "witness_key",
            "variant_key",
            name="uq_variant_reading_canonical_witness_key",
        ),
    )
    op.create_index(
        "idx_variant_readings_document", "variant_readings", ["document_id"]
    )
    op.create_index(
        "idx_variant_readings_edition", "variant_readings", ["edition_lineage_id"]
    )
    op.create_index(
        "idx_variant_readings_canonical", "variant_readings", ["canonical_document_key"]
    )
    op.create_index("idx_variant_readings_witness", "variant_readings", ["witness_key"])
    op.create_index("idx_variant_readings_segment", "variant_readings", ["segment_id"])
    op.alter_column("variant_readings", "evidence_json", server_default=None)
    op.alter_column("variant_readings", "review_status", server_default=None)


def downgrade() -> None:
    op.drop_index("idx_variant_readings_segment", table_name="variant_readings")
    op.drop_index("idx_variant_readings_witness", table_name="variant_readings")
    op.drop_index("idx_variant_readings_canonical", table_name="variant_readings")
    op.drop_index("idx_variant_readings_edition", table_name="variant_readings")
    op.drop_index("idx_variant_readings_document", table_name="variant_readings")
    op.drop_table("variant_readings")

    op.drop_index("idx_edition_lineages_witness", table_name="edition_lineages")
    op.drop_index("idx_edition_lineages_lineage", table_name="edition_lineages")
    op.drop_index("idx_edition_lineages_canonical", table_name="edition_lineages")
    op.drop_index("idx_edition_lineages_document", table_name="edition_lineages")
    op.drop_table("edition_lineages")
