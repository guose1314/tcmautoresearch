"""Configuration center and environment isolation tests."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.infrastructure.config_loader import (
    load_secret_section,
    load_settings,
    load_settings_section,
)


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
        self.tempdir.cleanup()

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
            self.assertEqual(
                client.app.state.job_manager._default_orchestrator_config["pipeline_config"]["literature_retrieval"]["pubmed_api_key"],
                "pubmed-secret-key",
            )