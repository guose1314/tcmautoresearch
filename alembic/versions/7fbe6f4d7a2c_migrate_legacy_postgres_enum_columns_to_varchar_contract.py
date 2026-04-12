"""migrate_legacy_postgres_enum_columns_to_varchar_contract

Revision ID: 7fbe6f4d7a2c
Revises: 3e5089f32f9a
Create Date: 2026-04-12 20:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7fbe6f4d7a2c'
down_revision: Union[str, Sequence[str], None] = '3e5089f32f9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_ENUM_MIGRATIONS = (
    {
        "table_name": "documents",
        "column_name": "process_status",
        "varchar_length": 10,
        "legacy_enum_name": "processstatusenum",
        "legacy_labels": ("PENDING", "PROCESSING", "COMPLETED", "FAILED"),
        "nullable": False,
    },
    {
        "table_name": "entities",
        "column_name": "type",
        "varchar_length": 8,
        "legacy_enum_name": "entitytypeenum",
        "legacy_labels": (
            "FORMULA",
            "HERB",
            "SYNDROME",
            "EFFICACY",
            "PROPERTY",
            "TASTE",
            "MERIDIAN",
            "OTHER",
        ),
        "nullable": False,
    },
    {
        "table_name": "relationship_types",
        "column_name": "category",
        "varchar_length": 11,
        "legacy_enum_name": "relationshipcategoryenum",
        "legacy_labels": ("COMPOSITION", "THERAPEUTIC", "PROPERTY", "SIMILARITY", "OTHER"),
        "nullable": True,
    },
)


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _fetch_column_metadata(connection: sa.Connection, table_name: str, column_name: str):
    return connection.execute(
        sa.text(
            """
            SELECT data_type, udt_name, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).fetchone()


def _drop_enum_type_if_unused(connection: sa.Connection, enum_name: str) -> None:
    if not enum_name:
        return
    remaining_columns = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND data_type = 'USER-DEFINED'
              AND udt_name = :enum_name
            """
        ),
        {"enum_name": enum_name},
    ).scalar()
    if int(remaining_columns or 0) == 0:
        op.execute(sa.text(f"DROP TYPE IF EXISTS {_quote_identifier(enum_name)}"))


def _ensure_legacy_enum_type(connection: sa.Connection, enum_name: str, labels: tuple[str, ...]) -> None:
    exists = connection.execute(
        sa.text("SELECT 1 FROM pg_type WHERE typname = :enum_name"),
        {"enum_name": enum_name},
    ).scalar()
    if exists:
        return
    labels_sql = ", ".join("'" + str(label).replace("'", "''") + "'" for label in labels)
    op.execute(sa.text(f"CREATE TYPE {_quote_identifier(enum_name)} AS ENUM ({labels_sql})"))


def _upgrade_column_to_varchar(
    connection: sa.Connection,
    *,
    table_name: str,
    column_name: str,
    varchar_length: int,
    legacy_enum_name: str,
    **_: object,
) -> None:
    metadata = _fetch_column_metadata(connection, table_name, column_name)
    if metadata is None:
        raise RuntimeError(f"Column public.{table_name}.{column_name} does not exist")

    data_type = str(metadata[0] or "").upper()
    enum_name = str(metadata[1] or "").strip() or legacy_enum_name
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)

    if data_type == "USER-DEFINED":
        op.execute(
            sa.text(
                f"ALTER TABLE {quoted_table} "
                f"ALTER COLUMN {quoted_column} "
                f"TYPE VARCHAR({int(varchar_length)}) "
                f"USING LOWER({quoted_column}::text)"
            )
        )
        _drop_enum_type_if_unused(connection, enum_name)
        return

    if data_type in {"CHARACTER VARYING", "TEXT"}:
        _drop_enum_type_if_unused(connection, legacy_enum_name)
        return

    raise RuntimeError(
        f"Unsupported column type for public.{table_name}.{column_name}: {metadata[0]}:{metadata[1]}"
    )


def _downgrade_column_to_legacy_enum(
    connection: sa.Connection,
    *,
    table_name: str,
    column_name: str,
    legacy_enum_name: str,
    legacy_labels: tuple[str, ...],
    nullable: bool,
    **_: object,
) -> None:
    metadata = _fetch_column_metadata(connection, table_name, column_name)
    if metadata is None:
        raise RuntimeError(f"Column public.{table_name}.{column_name} does not exist")

    data_type = str(metadata[0] or "").upper()
    udt_name = str(metadata[1] or "").strip()
    if data_type == "USER-DEFINED" and udt_name == legacy_enum_name:
        return

    if data_type not in {"CHARACTER VARYING", "TEXT"}:
        raise RuntimeError(
            f"Unsupported column type for public.{table_name}.{column_name}: {metadata[0]}:{metadata[1]}"
        )

    _ensure_legacy_enum_type(connection, legacy_enum_name, legacy_labels)
    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    quoted_enum = _quote_identifier(legacy_enum_name)
    cast_expression = f"UPPER({quoted_column}::text)::{quoted_enum}"
    if nullable:
        cast_expression = (
            f"CASE WHEN {quoted_column} IS NULL THEN NULL ELSE {cast_expression} END"
        )
    op.execute(
        sa.text(
            f"ALTER TABLE {quoted_table} "
            f"ALTER COLUMN {quoted_column} "
            f"TYPE {quoted_enum} "
            f"USING {cast_expression}"
        )
    )


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    for migration in LEGACY_ENUM_MIGRATIONS:
        _upgrade_column_to_varchar(connection, **migration)


def downgrade() -> None:
    """Downgrade schema."""
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    for migration in LEGACY_ENUM_MIGRATIONS:
        _downgrade_column_to_legacy_enum(connection, **migration)