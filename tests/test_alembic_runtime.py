from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from src.infrastructure.alembic_runtime import (
    DEFAULT_ALEMBIC_SQLALCHEMY_URL,
    resolve_alembic_database_target,
)


class TestAlembicRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "config.yml").write_text(
            yaml.safe_dump(
                {
                    "config_center": {
                        "default_environment": "development",
                        "environments_dir": "./config",
                    },
                    "database": {
                        "path": "./data/base.db",
                    },
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "config" / "production.yml").write_text(
            yaml.safe_dump(
                {
                    "environment": {"name": "production"},
                    "database": {
                        "type": "postgresql",
                        "host": "db.internal",
                        "port": 5432,
                        "name": "research",
                        "user": "tcm",
                        "password_env": "TCM_DB_PASSWORD",
                    },
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_prefers_explicit_url_over_runtime_settings(self) -> None:
        target = resolve_alembic_database_target(
            DEFAULT_ALEMBIC_SQLALCHEMY_URL,
            x_arguments={"url": "postgresql://user:pass@localhost:5432/custom"},
            default_root_path=self.root,
        )

        self.assertEqual(target.source, "explicit_url")
        self.assertEqual(target.sqlalchemy_url, "postgresql://user:pass@localhost:5432/custom")

    def test_uses_runtime_settings_when_ini_url_is_default(self) -> None:
        target = resolve_alembic_database_target(
            DEFAULT_ALEMBIC_SQLALCHEMY_URL,
            x_arguments={"environment": "production"},
            env={"TCM_DB_PASSWORD": "secret"},
            default_root_path=self.root,
        )

        self.assertEqual(target.source, "runtime_settings")
        self.assertEqual(target.environment, "production")
        self.assertEqual(target.sqlalchemy_url, "postgresql://tcm:secret@db.internal:5432/research")
        self.assertTrue(any(path.endswith("config.yml") for path in target.loaded_files))
        self.assertTrue(any(path.endswith("config\\production.yml") or path.endswith("config/production.yml") for path in target.loaded_files))

    def test_preserves_custom_ini_url_without_runtime_overrides(self) -> None:
        target = resolve_alembic_database_target(
            "sqlite:///C:/temp/custom.db",
            default_root_path=self.root,
        )

        self.assertEqual(target.source, "alembic_ini")
        self.assertEqual(target.sqlalchemy_url, "sqlite:///C:/temp/custom.db")