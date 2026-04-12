"""migrate_postgres_string_list_columns_to_varchar_array_contract

Revision ID: d6c8f52a1b2e
Revises: 7fbe6f4d7a2c
Create Date: 2026-04-12 20:55:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd6c8f52a1b2e'
down_revision: Union[str, Sequence[str], None] = '7fbe6f4d7a2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STRING_LIST_COLUMN_MIGRATIONS = (
    {
        "table_name": "entities",
        "column_name": "alternative_names",
    },
    {
        "table_name": "processing_statistics",
        "column_name": "source_modules",
    },
)

_JSON_TO_VARCHAR_ARRAY_FUNCTION = "_tcmautoresearch_jsonb_to_varchar_array"


def _quote_identifier(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _fetch_column_metadata(connection: sa.Connection, table_name: str, column_name: str):
    return connection.execute(
        sa.text(
            """
            SELECT data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).fetchone()


def _create_json_to_varchar_array_function() -> None:
    quoted_function = _quote_identifier(_JSON_TO_VARCHAR_ARRAY_FUNCTION)
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {quoted_function}(payload jsonb)
            RETURNS varchar[]
            LANGUAGE SQL
            IMMUTABLE
            AS $$
                SELECT CASE
                    WHEN payload IS NULL THEN NULL
                    WHEN jsonb_typeof(payload) = 'null' THEN ARRAY[]::varchar[]
                    WHEN jsonb_typeof(payload) = 'array' THEN COALESCE(
                        ARRAY(SELECT jsonb_array_elements_text(payload)),
                        ARRAY[]::varchar[]
                    )
                    WHEN jsonb_typeof(payload) = 'string' THEN ARRAY[payload #>> '{{}}']
                    ELSE ARRAY[payload::text]
                END
            $$
            """
        )
    )


def _drop_json_to_varchar_array_function() -> None:
    quoted_function = _quote_identifier(_JSON_TO_VARCHAR_ARRAY_FUNCTION)
    op.execute(sa.text(f"DROP FUNCTION IF EXISTS {quoted_function}(jsonb)"))


def _upgrade_column_to_varchar_array(
    connection: sa.Connection,
    *,
    table_name: str,
    column_name: str,
) -> None:
    metadata = _fetch_column_metadata(connection, table_name, column_name)
    if metadata is None:
        raise RuntimeError(f"Column public.{table_name}.{column_name} does not exist")

    data_type = str(metadata[0] or "").upper()
    udt_name = str(metadata[1] or "").strip()
    if data_type == "ARRAY" and udt_name == "_varchar":
        return

    if data_type not in {"JSON", "JSONB"}:
        raise RuntimeError(
            f"Unsupported column type for public.{table_name}.{column_name}: {metadata[0]}:{metadata[1]}"
        )

    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    quoted_function = _quote_identifier(_JSON_TO_VARCHAR_ARRAY_FUNCTION)
    op.execute(
        sa.text(
            f"ALTER TABLE {quoted_table} "
            f"ALTER COLUMN {quoted_column} "
            f"TYPE VARCHAR[] "
            f"USING {quoted_function}({quoted_column}::jsonb)"
        )
    )


def _downgrade_column_to_json(
    connection: sa.Connection,
    *,
    table_name: str,
    column_name: str,
) -> None:
    metadata = _fetch_column_metadata(connection, table_name, column_name)
    if metadata is None:
        raise RuntimeError(f"Column public.{table_name}.{column_name} does not exist")

    data_type = str(metadata[0] or "").upper()
    udt_name = str(metadata[1] or "").strip()
    if data_type in {"JSON", "JSONB"}:
        return

    if data_type != "ARRAY" or udt_name != "_varchar":
        raise RuntimeError(
            f"Unsupported column type for public.{table_name}.{column_name}: {metadata[0]}:{metadata[1]}"
        )

    quoted_table = _quote_identifier(table_name)
    quoted_column = _quote_identifier(column_name)
    op.execute(
        sa.text(
            f"ALTER TABLE {quoted_table} "
            f"ALTER COLUMN {quoted_column} "
            f"TYPE JSON "
            f"USING to_json({quoted_column})"
        )
    )


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    _create_json_to_varchar_array_function()
    try:
        for migration in STRING_LIST_COLUMN_MIGRATIONS:
            _upgrade_column_to_varchar_array(connection, **migration)
    finally:
        _drop_json_to_varchar_array_function()


def downgrade() -> None:
    """Downgrade schema."""
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    for migration in STRING_LIST_COLUMN_MIGRATIONS:
        _downgrade_column_to_json(connection, **migration)