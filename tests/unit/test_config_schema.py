"""Phase L-4 — 配置 schema fail-fast 单元测试。"""

from __future__ import annotations

import unittest

from src.infrastructure.config_schema import (
    APP_CONFIG_SCHEMA_CONTRACT_VERSION,
    CONTRACT_VERSION,
    AppConfigSchema,
    ConfigValidationError,
    ConfigValidationReport,
    DatabaseConfig,
    LoggingConfig,
    Neo4jConfig,
    WebConsoleConfig,
    validate_app_config,
)


def _good_config() -> dict:
    return {
        "environment": "development",
        "api": {"title": "TCM", "version": "0.1.0", "cors_origins": ["*"]},
        "database": {"type": "postgresql", "host": "localhost", "port": 5432},
        "neo4j": {"enabled": True, "uri": "neo4j://localhost:7687"},
        "models": {"llm": {"path": "./models/x.gguf"}},
        "output": {"base_dir": "./output"},
        "logging": {"level": "INFO"},
        "web_console": {"title": "Console", "port": 8080},
    }


class TestContractVersion(unittest.TestCase):
    def test_version(self) -> None:
        self.assertEqual(CONTRACT_VERSION, "app-config-schema-v1")
        self.assertEqual(APP_CONFIG_SCHEMA_CONTRACT_VERSION, CONTRACT_VERSION)


class TestSubsectionValidators(unittest.TestCase):
    def test_database_type_normalized(self) -> None:
        cfg = DatabaseConfig(type="POSTGRES")
        self.assertEqual(cfg.type, "postgresql")

    def test_database_type_invalid(self) -> None:
        with self.assertRaises(Exception):
            DatabaseConfig(type="mongodb")

    def test_database_port_range(self) -> None:
        with self.assertRaises(Exception):
            DatabaseConfig(type="sqlite", port=99999)

    def test_neo4j_uri_must_be_neo4j_or_bolt(self) -> None:
        with self.assertRaises(Exception):
            Neo4jConfig(enabled=True, uri="http://example.com")

    def test_neo4j_uri_accepts_bolt(self) -> None:
        cfg = Neo4jConfig(enabled=True, uri="bolt://localhost:7687")
        self.assertTrue(cfg.uri.startswith("bolt://"))  # type: ignore[union-attr]

    def test_logging_level_normalized(self) -> None:
        cfg = LoggingConfig(level="info")
        self.assertEqual(cfg.level, "INFO")

    def test_logging_level_invalid(self) -> None:
        with self.assertRaises(Exception):
            LoggingConfig(level="LOUD")

    def test_web_console_port(self) -> None:
        with self.assertRaises(Exception):
            WebConsoleConfig(port=0)


class TestAppConfigSchema(unittest.TestCase):
    def test_full_good_config_passes(self) -> None:
        # Should not raise
        AppConfigSchema.model_validate(_good_config())

    def test_unknown_top_level_keys_allowed(self) -> None:
        cfg = _good_config()
        cfg["custom_section"] = {"foo": "bar"}
        AppConfigSchema.model_validate(cfg)


class TestValidateAppConfig(unittest.TestCase):
    def test_good_returns_ok_report(self) -> None:
        report = validate_app_config(_good_config())
        self.assertIsInstance(report, ConfigValidationReport)
        self.assertTrue(report.ok)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.contract_version, CONTRACT_VERSION)

    def test_bad_returns_errors_in_non_strict(self) -> None:
        cfg = _good_config()
        cfg["database"]["type"] = "mongodb"
        report = validate_app_config(cfg)
        self.assertFalse(report.ok)
        self.assertGreaterEqual(len(report.errors), 1)
        self.assertTrue(any("database" in (e.get("loc") or "") for e in report.errors))

    def test_strict_raises_on_error(self) -> None:
        cfg = _good_config()
        cfg["neo4j"]["uri"] = "http://nope"
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_app_config(cfg, strict=True)
        self.assertGreaterEqual(len(ctx.exception.errors), 1)

    def test_non_mapping_input_handled(self) -> None:
        report = validate_app_config([])  # type: ignore[arg-type]
        self.assertFalse(report.ok)

    def test_non_mapping_strict_raises(self) -> None:
        with self.assertRaises(ConfigValidationError):
            validate_app_config("not a dict", strict=True)  # type: ignore[arg-type]

    def test_partial_config_passes(self) -> None:
        # Empty dict should be acceptable (all fields optional)
        report = validate_app_config({})
        self.assertTrue(report.ok)

    def test_to_dict_serialization(self) -> None:
        report = validate_app_config(_good_config())
        data = report.to_dict()
        self.assertEqual(data["ok"], True)
        self.assertEqual(data["contract_version"], CONTRACT_VERSION)


if __name__ == "__main__":
    unittest.main()
