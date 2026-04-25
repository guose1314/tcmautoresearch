"""Configuration center and environment isolation tests."""

from __future__ import annotations

import gc
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import yaml
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.cycle.cycle_runtime_config import build_cycle_orchestrator_config
from src.infrastructure.config_loader import (
    load_secret_section,
    load_settings,
    load_settings_section,
)
from src.infrastructure.runtime_config_assembler import (
    _ENTRYPOINT_RUNTIME_PROFILES,
    build_runtime_assembly,
)
from src.web.app import create_app as create_legacy_web_app
from web_console.app import create_app as create_web_console_app
from web_console.job_manager import ResearchJobManager


class TestConfigLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "secrets").mkdir(parents=True, exist_ok=True)

        base_config = {
            "system": {
                "name": "测试研究系统",
                "version": "9.9.9",
                "description": "测试用配置中心",
                "standards": ["T/C IATCM 098-2023"],
                "principles": ["可测试性"],
            },
            "config_center": {
                "default_environment": "development",
                "environments_dir": "./config",
                "env_prefix": "TCM",
            },
            "api": {
                "title": "Test API",
                "version": "9.9.9",
                "cors_origins": ["http://localhost:3000"],
            },
            "modules": {
                "document_preprocessing": {
                    "timeout": 30,
                    "max_input_chars": 200,
                },
                "entity_extraction": {
                    "threshold": 0.7,
                },
            },
            "database": {
                "path": "./data/base.db",
            },
            "output": {
                "directory": "./output/base",
            },
            "logging": {
                "file": "./logs/base.log",
            },
            "web_console": {
                "job_storage_dir": "./output/base/web_console_jobs",
            },
        }
        test_config = {
            "environment": {"name": "test"},
            "output": {"directory": "./output/test"},
            "database": {"path": "./data/test.db"},
            "logging": {"file": "./logs/test.log"},
            "modules": {
                "document_preprocessing": {
                    "timeout": 5,
                },
            },
            "web_console": {
                "job_storage_dir": "./output/test/web_console_jobs",
            },
        }
        (self.root / "config.yml").write_text(yaml.safe_dump(base_config, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (self.root / "config" / "test.yml").write_text(
            yaml.safe_dump(test_config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        (self.root / "secrets.yml").write_text(
            yaml.safe_dump(
                {
                    "monitoring": {
                        "alerting": {
                            "email": {
                                "sender": "alerts@example.com",
                            }
                        }
                    }
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        (self.root / "secrets" / "test.yml").write_text(
            yaml.safe_dump(
                {
                    "models": {
                        "llm": {
                            "api_key": "test-llm-api-key",
                        }
                    },
                    "clinical_gap_analysis": {
                        "api_key": "test-gap-api-key",
                    },
                    "literature_retrieval": {
                        "pubmed_email": "pubmed@example.com",
                        "pubmed_api_key": "pubmed-secret-key",
                        "source_credentials": {
                            "scopus": {
                                "api_key": "scopus-secret-key",
                            },
                            "web_of_science": {
                                "api_key": "wos-secret-key",
                            },
                            "embase": {
                                "api_key": "embase-secret-key",
                            },
                            "clinicalkey": {
                                "api_key": "clinicalkey-secret-key",
                            },
                        },
                    },
                    "monitoring": {
                        "alerting": {
                            "email": {
                                "password": "test-secret-password",
                            },
                            "webhook_url": "https://example.invalid/secret-webhook",
                        }
                    }
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        # Force GC to release SQLite connections held by app state (Windows lock issue)
        gc.collect()
        try:
            self.tempdir.cleanup()
        except (PermissionError, OSError):
            # On Windows, SQLite files may stay locked briefly; ignore cleanup failure
            pass

    def test_loader_merges_environment_and_env_var_overrides(self) -> None:
        original_env = os.environ.get("TCM__WEB_CONSOLE__JOB_STORAGE_DIR")
        os.environ["TCM__WEB_CONSOLE__JOB_STORAGE_DIR"] = "./output/env-override/jobs"
        try:
            settings = load_settings(root_path=self.root, environment="test")
        finally:
            if original_env is None:
                os.environ.pop("TCM__WEB_CONSOLE__JOB_STORAGE_DIR", None)
            else:
                os.environ["TCM__WEB_CONSOLE__JOB_STORAGE_DIR"] = original_env

        self.assertEqual(settings.environment, "test")
        self.assertTrue(settings.loaded_files[-1].endswith("config\\test.yml") or settings.loaded_files[-1].endswith("config/test.yml"))
        self.assertEqual(settings.module_config("document_preprocessor")["timeout"], 5)
        self.assertEqual(
            settings.job_storage_dir,
            str((self.root / "output" / "env-override" / "jobs").resolve()),
        )
        self.assertEqual(settings.get("database.path"), str((self.root / "data" / "test.db").resolve()))

    def test_load_settings_section_merges_multiple_candidates(self) -> None:
        config_path = self.root / "config.yml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        payload["quality_assessment"] = {"min_overall_score": 80}
        payload["governance"] = {
            "quality_assessment": {
                "min_dimension_score": 65,
                "export_contract_version": "d49.v1",
            }
        }
        config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

        section = load_settings_section(
            "quality_assessment",
            "governance.quality_assessment",
            config_path=config_path,
            root_path=self.root,
            default={},
        )

        self.assertEqual(section["min_overall_score"], 80)
        self.assertEqual(section["min_dimension_score"], 65)
        self.assertEqual(section["export_contract_version"], "d49.v1")

    def test_loader_reads_secrets_from_files_and_secret_env_overrides(self) -> None:
        original_secret = os.environ.get("TCM_SECRET__MONITORING__ALERTING__EMAIL__PASSWORD")
        os.environ["TCM_SECRET__MONITORING__ALERTING__EMAIL__PASSWORD"] = "env-secret-password"
        try:
            settings = load_settings(root_path=self.root, environment="test")
        finally:
            if original_secret is None:
                os.environ.pop("TCM_SECRET__MONITORING__ALERTING__EMAIL__PASSWORD", None)
            else:
                os.environ["TCM_SECRET__MONITORING__ALERTING__EMAIL__PASSWORD"] = original_secret

        self.assertEqual(settings.get_secret("monitoring.alerting.email.sender"), "alerts@example.com")
        self.assertEqual(settings.get_secret("monitoring.alerting.email.password"), "env-secret-password")
        self.assertEqual(settings.get_secret("monitoring.alerting.webhook_url"), "https://example.invalid/secret-webhook")
        self.assertTrue(any(path.endswith("secrets.yml") for path in settings.loaded_secret_files))
        self.assertTrue(any(path.endswith("secrets\\test.yml") or path.endswith("secrets/test.yml") for path in settings.loaded_secret_files))

    def test_load_secret_section_merges_secret_candidates(self) -> None:
        section = load_secret_section(
            "monitoring.alerting",
            root_path=self.root,
            environment="test",
            default={},
        )

        self.assertEqual(section["email"]["sender"], "alerts@example.com")
        self.assertEqual(section["email"]["password"], "test-secret-password")
        self.assertEqual(section["webhook_url"], "https://example.invalid/secret-webhook")

    def test_materialize_runtime_config_injects_runtime_secrets(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")

        runtime_config = settings.materialize_runtime_config()

        self.assertEqual(runtime_config["models"]["llm"]["api_key"], "test-llm-api-key")
        self.assertEqual(runtime_config["clinical_gap_analysis"]["api_key"], "test-gap-api-key")
        self.assertEqual(runtime_config["literature_retrieval"]["pubmed_email"], "pubmed@example.com")
        self.assertEqual(runtime_config["literature_retrieval"]["pubmed_api_key"], "pubmed-secret-key")
        self.assertEqual(
            runtime_config["literature_retrieval"]["source_credentials"]["scopus"]["api_key"],
            "scopus-secret-key",
        )
        self.assertEqual(
            runtime_config["literature_retrieval"]["source_credentials"]["web_of_science"]["api_key"],
            "wos-secret-key",
        )

    def test_build_runtime_assembly_reuses_settings_and_clones_pipeline_config(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")

        assembly = build_runtime_assembly(settings=settings)

        self.assertIs(assembly.settings, settings)
        self.assertEqual(assembly.entrypoint, "")
        self.assertIsNone(assembly.runtime_profile)
        self.assertEqual(assembly.runtime_config["models"]["llm"]["api_key"], "test-llm-api-key")
        self.assertEqual(
            assembly.orchestrator_config["pipeline_config"]["literature_retrieval"]["pubmed_api_key"],
            "pubmed-secret-key",
        )
        self.assertNotIn("runtime_profile", assembly.orchestrator_config)

        assembly.runtime_config["models"]["llm"]["api_key"] = "mutated-runtime-key"
        self.assertEqual(
            assembly.orchestrator_config["pipeline_config"]["models"]["llm"]["api_key"],
            "test-llm-api-key",
        )

    def test_build_runtime_assembly_applies_web_entrypoint_runtime_profile(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")

        assembly = build_runtime_assembly(settings=settings, entrypoint="web")

        self.assertEqual(assembly.entrypoint, "web")
        self.assertEqual(assembly.runtime_profile, "web_research")
        self.assertEqual(assembly.orchestrator_config["runtime_profile"], "web_research")

    def test_runtime_entrypoint_profile_catalog_is_explicit_and_limited(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")

        self.assertEqual(
            _ENTRYPOINT_RUNTIME_PROFILES,
            {
                "web": "web_research",
                "demo": "demo_research",
            },
        )

        for entrypoint, expected_profile in _ENTRYPOINT_RUNTIME_PROFILES.items():
            assembly = build_runtime_assembly(settings=settings, entrypoint=entrypoint)
            self.assertEqual(assembly.entrypoint, entrypoint)
            self.assertEqual(assembly.runtime_profile, expected_profile)
            self.assertEqual(assembly.orchestrator_config["runtime_profile"], expected_profile)

        unknown_entry_assembly = build_runtime_assembly(settings=settings, entrypoint="batch")
        self.assertEqual(unknown_entry_assembly.entrypoint, "batch")
        self.assertIsNone(unknown_entry_assembly.runtime_profile)
        self.assertNotIn("runtime_profile", unknown_entry_assembly.orchestrator_config)

    def test_build_cycle_orchestrator_config_applies_demo_entrypoint_runtime_profile(self) -> None:
        orchestrator_config = build_cycle_orchestrator_config(
            config_path=self.root / "config.yml",
            environment="test",
        )

        self.assertEqual(orchestrator_config["runtime_profile"], "demo_research")
        self.assertEqual(
            orchestrator_config["pipeline_config"]["models"]["llm"]["api_key"],
            "test-llm-api-key",
        )

    def test_job_manager_uses_runtime_assembly_when_settings_provided(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")
        manager = ResearchJobManager(settings=settings)
        try:
            self.assertEqual(manager._default_orchestrator_config["runtime_profile"], "web_research")
            self.assertEqual(
                manager._default_orchestrator_config["pipeline_config"]["models"]["llm"]["api_key"],
                "test-llm-api-key",
            )
            self.assertEqual(
                manager.get_storage_summary()["storage_dir"],
                str((self.root / "output" / "test" / "web_console_jobs").resolve()),
            )
        finally:
            manager.close()

    def test_database_url_prefers_explicit_password_over_password_env(self) -> None:
        config_path = self.root / "config.yml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        payload["database"] = {
            "type": "postgresql",
            "host": "db.example.local",
            "port": 5432,
            "name": "explicit_db",
            "user": "explicit_user",
            "password": "explicit-db-password",
            "password_env": "TCM_DB_PASSWORD",
        }
        config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

        original_env = os.environ.get("TCM_DB_PASSWORD")
        os.environ["TCM_DB_PASSWORD"] = "stale-env-password"
        try:
            settings = load_settings(root_path=self.root, environment="test")
        finally:
            if original_env is None:
                os.environ.pop("TCM_DB_PASSWORD", None)
            else:
                os.environ["TCM_DB_PASSWORD"] = original_env

        self.assertEqual(
            settings.database_url,
            "postgresql://explicit_user:explicit-db-password@db.example.local:5432/explicit_db",
        )

    def test_neo4j_auth_prefers_explicit_password_over_password_env(self) -> None:
        config_path = self.root / "config.yml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        payload["neo4j"] = {
            "enabled": True,
            "uri": "bolt://neo4j.example.local:7687",
            "user": "neo4j-user",
            "password": "explicit-neo4j-password",
            "password_env": "TCM_NEO4J_PASSWORD",
            "database": "neo4j",
        }
        config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")

        original_env = os.environ.get("TCM_NEO4J_PASSWORD")
        os.environ["TCM_NEO4J_PASSWORD"] = "stale-env-password"
        try:
            settings = load_settings(root_path=self.root, environment="test")
        finally:
            if original_env is None:
                os.environ.pop("TCM_NEO4J_PASSWORD", None)
            else:
                os.environ["TCM_NEO4J_PASSWORD"] = original_env

        self.assertEqual(settings.neo4j_auth, ("neo4j-user", "explicit-neo4j-password"))

    def test_create_app_uses_environment_isolated_runtime_paths(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")

        with TestClient(create_app(settings=settings)) as client:
            health = client.get("/api/v1/system/health")
            self.assertEqual(health.status_code, 200)
            health_payload = health.json()
            self.assertEqual(health_payload["environment"], "test")
            self.assertIn(str((self.root / "config.yml").resolve()), health_payload["config_sources"])
            self.assertIn("summary", health_payload)

            status = client.get("/api/v1/system/status")
            self.assertEqual(status.status_code, 200)
            status_payload = status.json()
            self.assertEqual(status_payload["system_info"]["environment"], "test")
            self.assertEqual(status_payload["metadata"]["config_env"], "test")
            self.assertIn("health_report", status_payload)

            persistence = client.get("/api/v1/system/persistence/summary")
            self.assertEqual(persistence.status_code, 200)
            self.assertEqual(
                persistence.json()["storage_dir"],
                str((self.root / "output" / "test" / "web_console_jobs").resolve()),
            )

            self.assertEqual(
                client.app.state.job_manager._default_orchestrator_config["pipeline_config"]["models"]["llm"]["api_key"],
                "test-llm-api-key",
            )
            self.assertEqual(client.app.state.runtime_assembly.runtime_profile, "web_research")
            self.assertEqual(client.app.state.job_manager._default_orchestrator_config["runtime_profile"], "web_research")
            self.assertEqual(
                client.app.state.job_manager._default_orchestrator_config["pipeline_config"]["literature_retrieval"]["pubmed_api_key"],
                "pubmed-secret-key",
            )

    def test_web_console_app_uses_runtime_assembly_for_default_job_manager(self) -> None:
        settings = load_settings(root_path=self.root, environment="test")

        with TestClient(create_web_console_app(settings=settings)) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.app.state.runtime_assembly.runtime_profile, "web_research")
            self.assertEqual(client.app.state.job_manager._default_orchestrator_config["runtime_profile"], "web_research")
            self.assertEqual(
                client.app.state.job_manager._default_orchestrator_config["pipeline_config"]["models"]["llm"]["api_key"],
                "test-llm-api-key",
            )
            self.assertEqual(
                client.app.state.job_manager.get_storage_summary()["storage_dir"],
                str((self.root / "output" / "test" / "web_console_jobs").resolve()),
            )

    def test_app_entrypoints_accept_config_path_and_environment(self) -> None:
        with TestClient(create_app(config_path=self.root / "config.yml", environment="test")) as api_client:
            self.assertEqual(api_client.get("/health").json()["environment"], "test")
            self.assertEqual(api_client.app.state.runtime_assembly.runtime_profile, "web_research")
            self.assertEqual(
                api_client.app.state.job_manager._default_orchestrator_config["pipeline_config"]["models"]["llm"]["api_key"],
                "test-llm-api-key",
            )

        with TestClient(create_web_console_app(config_path=self.root / "config.yml", environment="test")) as web_client:
            self.assertEqual(web_client.get("/health").json()["environment"], "test")
            self.assertEqual(web_client.app.state.runtime_assembly.runtime_profile, "web_research")
            self.assertEqual(
                web_client.app.state.job_manager._default_orchestrator_config["pipeline_config"]["literature_retrieval"]["pubmed_api_key"],
                "pubmed-secret-key",
            )

        with TestClient(create_legacy_web_app(config_path=self.root / "config.yml", environment="test")) as legacy_client:
            self.assertEqual(legacy_client.get("/health").json()["environment"], "test")
            self.assertEqual(legacy_client.app.state.settings.environment, "test")
            self.assertEqual(legacy_client.app.state.runtime_assembly.runtime_profile, "web_research")
            self.assertEqual(
                legacy_client.app.state.config["models"]["llm"]["api_key"],
                "test-llm-api-key",
            )

    def test_legacy_web_app_uses_settings_database_url_for_postgresql_init(self) -> None:
        config_path = self.root / "config.yml"
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        payload["database"] = {
            "type": "postgresql",
            "host": "db.example.local",
            "port": 5432,
            "name": "structured_research",
            "user": "structured_user",
            "password": "structured-password",
        }
        config_path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        settings = load_settings(root_path=self.root, environment="test")
        observed: dict[str, object] = {}

        class _FakeDatabaseManager:
            def __init__(self, connection_string, echo=False):
                observed["connection_string"] = connection_string
                observed["echo"] = echo

            def init_db(self):
                observed["init_db"] = True

            @contextmanager
            def session_scope(self):
                yield object()

            @staticmethod
            def create_default_relationships(_session):
                return None

            def close(self):
                observed["close_called"] = True

        with patch("src.infrastructure.persistence.DatabaseManager", _FakeDatabaseManager):
            app = create_legacy_web_app(settings=settings)

        self.assertIn("db.example.local:5432/structured_research", observed["connection_string"])
        self.assertIn("structured_user", observed["connection_string"])
        self.assertTrue(observed["init_db"])
        self.assertIsInstance(app.state.db_manager, _FakeDatabaseManager)


class TestWebStartupEntryPoints(unittest.TestCase):
    def setUp(self) -> None:
        self._original_config_path = os.environ.get("TCM_CONFIG_PATH")
        self._original_environment = os.environ.get("TCM_ENV")
        os.environ.pop("TCM_CONFIG_PATH", None)
        os.environ.pop("TCM_ENV", None)

    def tearDown(self) -> None:
        if self._original_config_path is None:
            os.environ.pop("TCM_CONFIG_PATH", None)
        else:
            os.environ["TCM_CONFIG_PATH"] = self._original_config_path

        if self._original_environment is None:
            os.environ.pop("TCM_ENV", None)
        else:
            os.environ["TCM_ENV"] = self._original_environment

    def test_legacy_web_main_forwards_runtime_args_to_uvicorn(self) -> None:
        from src.web import main as legacy_main

        with patch.object(legacy_main.uvicorn, "run") as mock_run:
            legacy_main.main(
                [
                    "--config",
                    "./config/test.yml",
                    "--environment",
                    "test",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8011",
                    "--reload",
                    "--log-level",
                    "warning",
                ]
            )

        self.assertEqual(os.environ["TCM_CONFIG_PATH"], "./config/test.yml")
        self.assertEqual(os.environ["TCM_ENV"], "test")
        mock_run.assert_called_once_with(
            "src.web.main:create_uvicorn_app",
            factory=True,
            host="127.0.0.1",
            port=8011,
            reload=True,
            log_level="warning",
        )

    def test_web_console_main_forwards_runtime_args_to_uvicorn(self) -> None:
        from web_console import main as web_console_main

        mock_uvicorn = unittest.mock.Mock()
        with patch.object(web_console_main, "import_module", return_value=mock_uvicorn):
            web_console_main.main(
                [
                    "--config",
                    "./config/test.yml",
                    "--environment",
                    "test",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8009",
                    "--reload",
                ]
            )

        self.assertEqual(os.environ["TCM_CONFIG_PATH"], "./config/test.yml")
        self.assertEqual(os.environ["TCM_ENV"], "test")
        mock_uvicorn.run.assert_called_once_with(
            "web_console.main:create_uvicorn_app",
            factory=True,
            host="127.0.0.1",
            port=8009,
            reload=True,
            log_level="info",
        )

    def test_api_main_forwards_runtime_args_to_uvicorn(self) -> None:
        from src.api import main as api_main

        mock_uvicorn = unittest.mock.Mock()
        with patch.object(api_main, "import_module", return_value=mock_uvicorn):
            api_main.main(
                [
                    "--config",
                    "./config/test.yml",
                    "--environment",
                    "test",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8010",
                    "--reload",
                    "--log-level",
                    "warning",
                ]
            )

        self.assertEqual(os.environ["TCM_CONFIG_PATH"], "./config/test.yml")
        self.assertEqual(os.environ["TCM_ENV"], "test")
        mock_uvicorn.run.assert_called_once_with(
            "src.api.main:create_uvicorn_app",
            factory=True,
            host="127.0.0.1",
            port=8010,
            reload=True,
            log_level="warning",
        )

    def test_legacy_web_factory_reads_runtime_override_env(self) -> None:
        from src.web import main as legacy_main

        os.environ["TCM_CONFIG_PATH"] = "./config/test.yml"
        os.environ["TCM_ENV"] = "test"
        sentinel = object()
        with patch.object(legacy_main, "create_app", return_value=sentinel) as mock_create_app:
            result = legacy_main.create_uvicorn_app()

        self.assertIs(result, sentinel)
        mock_create_app.assert_called_once_with(config_path="./config/test.yml", environment="test")

    def test_web_console_factory_reads_runtime_override_env(self) -> None:
        from web_console import main as web_console_main

        os.environ["TCM_CONFIG_PATH"] = "./config/test.yml"
        os.environ["TCM_ENV"] = "test"
        sentinel = object()
        with patch.object(web_console_main, "create_app", return_value=sentinel) as mock_create_app:
            result = web_console_main.create_uvicorn_app()

        self.assertIs(result, sentinel)
        mock_create_app.assert_called_once_with(config_path="./config/test.yml", environment="test")

    def test_api_factory_reads_runtime_override_env(self) -> None:
        from src.api import main as api_main

        os.environ["TCM_CONFIG_PATH"] = "./config/test.yml"
        os.environ["TCM_ENV"] = "test"
        sentinel = object()
        mock_create_app = unittest.mock.Mock(return_value=sentinel)
        with patch.object(api_main, "_load_create_app_factory", return_value=mock_create_app):
            result = api_main.create_uvicorn_app()

        self.assertIs(result, sentinel)
        mock_create_app.assert_called_once_with(config_path="./config/test.yml", environment="test")