"""T6.1: add outbox_events + outbox_dlq for transactional outbox

Revision ID: d8e1f2a3b4c5
Revises: c2d3e4f5a6b8
Create Date: 2026-04-28 00:00:00.000000

T6.1 — Transactional Outbox：与业务表同事务写入 ``outbox_events``，由后台 worker
异步消费并投影到 Neo4j；失败 ≥ 5 次的事件归档至 ``outbox_dlq``。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d8e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
        json_type = JSONB
        uuid_type = PGUUID(as_uuid=True)
    else:
        json_type = sa.JSON  # type: ignore[assignment]
        uuid_type = sa.CHAR(36)  # type: ignore[assignment]

    op.create_table(
        "outbox_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=is_postgres), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_outbox_status_created",
        "outbox_events",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_outbox_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id"],
    )

    op.create_table(
        "outbox_dlq",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("original_event_id", uuid_type, nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "moved_at",
            sa.DateTime(timezone=is_postgres),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "idx_outbox_dlq_original",
        "outbox_dlq",
        ["original_event_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_dlq_original", table_name="outbox_dlq")
    op.drop_table("outbox_dlq")
    op.drop_index("idx_outbox_aggregate", table_name="outbox_events")
    op.drop_index("idx_outbox_status_created", table_name="outbox_events")
    op.drop_table("outbox_events")
