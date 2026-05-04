"""p19: add production quality monitoring tables

Revision ID: c4d5e6f7a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-05-04 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a9b0"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _types() -> tuple[sa.types.TypeEngine, sa.types.TypeEngine]:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    if is_postgres:
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy.dialects.postgresql import UUID as PGUUID

        return PGUUID(as_uuid=True), JSONB()
    return sa.CHAR(36), sa.JSON()


def upgrade() -> None:
    uuid_type, json_type = _types()
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.create_table(
        "production_monitoring_outbox",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="production_monitoring",
        ),
        sa.Column("aggregate_id", sa.String(length=255), nullable=True),
        sa.Column("payload", json_type, nullable=False),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=is_postgres), nullable=True),
        sa.UniqueConstraint("event_key", name="uq_prod_mon_outbox_event_key"),
    )
    op.create_index(
        "idx_prod_mon_outbox_status_created",
        "production_monitoring_outbox",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_prod_mon_outbox_event_type",
        "production_monitoring_outbox",
        ["event_type"],
    )
    op.create_index(
        "idx_prod_mon_outbox_aggregate",
        "production_monitoring_outbox",
        ["aggregate_id"],
    )

    op.create_table(
        "production_monitoring_dlq",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("original_event_id", uuid_type, nullable=True),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="production_monitoring",
        ),
        sa.Column("aggregate_id", sa.String(length=255), nullable=True),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "replay_status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_replayed_at", sa.DateTime(timezone=is_postgres), nullable=True),
        sa.UniqueConstraint("event_key", name="uq_prod_mon_dlq_event_key"),
    )
    op.create_index(
        "idx_prod_mon_dlq_original",
        "production_monitoring_dlq",
        ["original_event_id"],
    )
    op.create_index(
        "idx_prod_mon_dlq_category_seen",
        "production_monitoring_dlq",
        ["category", "last_seen_at"],
    )
    op.create_index(
        "idx_prod_mon_dlq_replay_status",
        "production_monitoring_dlq",
        ["replay_status", "last_seen_at"],
    )
    op.create_index(
        "idx_prod_mon_dlq_event_type",
        "production_monitoring_dlq",
        ["event_type"],
    )

    op.create_table(
        "production_quality_snapshots",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "source",
            sa.String(length=64),
            nullable=False,
            server_default="batch_distill",
        ),
        sa.Column(
            "window_label",
            sa.String(length=128),
            nullable=False,
            server_default="recent",
        ),
        sa.Column("metrics_json", json_type, nullable=False),
        sa.Column("event_counts_json", json_type, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_prod_quality_snapshot_created",
        "production_quality_snapshots",
        ["created_at"],
    )
    op.create_index(
        "idx_prod_quality_snapshot_source",
        "production_quality_snapshots",
        ["source", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_prod_quality_snapshot_source", table_name="production_quality_snapshots"
    )
    op.drop_index(
        "idx_prod_quality_snapshot_created", table_name="production_quality_snapshots"
    )
    op.drop_table("production_quality_snapshots")
    op.drop_index("idx_prod_mon_dlq_event_type", table_name="production_monitoring_dlq")
    op.drop_index(
        "idx_prod_mon_dlq_replay_status", table_name="production_monitoring_dlq"
    )
    op.drop_index(
        "idx_prod_mon_dlq_category_seen", table_name="production_monitoring_dlq"
    )
    op.drop_index("idx_prod_mon_dlq_original", table_name="production_monitoring_dlq")
    op.drop_table("production_monitoring_dlq")
    op.drop_index(
        "idx_prod_mon_outbox_aggregate", table_name="production_monitoring_outbox"
    )
    op.drop_index(
        "idx_prod_mon_outbox_event_type", table_name="production_monitoring_outbox"
    )
    op.drop_index(
        "idx_prod_mon_outbox_status_created", table_name="production_monitoring_outbox"
    )
    op.drop_table("production_monitoring_outbox")
