"""Architecture 3.0 monitoring service tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from src.api.dependencies import create_default_architecture
from src.infrastructure.config_loader import load_settings
from src.infrastructure.monitoring import MonitoringService
from web_console.job_manager import ResearchJobManager


class TestMonitoringService(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "secrets").mkdir(parents=True, exist_ok=True)
        (self.root / "models").mkdir(parents=True, exist_ok=True)
        (self.root / "logs").mkdir(parents=True, exist_ok=True)
        (self.root / "data").mkdir(parents=True, exist_ok=True)
        (self.root / "output").mkdir(parents=True, exist_ok=True)
        (self.root / "models" / "test-model.gguf").write_text("placeholder", encoding="utf-8")

        config = {
            "system": {
                "name": "监控测试系统",
                "version": "3.0.0-test",
                "description": "监控服务测试",
            },
            "monitoring": {
                "enabled": True,
                "interval_seconds": 30,
                "alerting": {
                    "enabled": True,
                    "resend_interval_seconds": 0,
                    "thresholds": {
                        "cpu_usage": -1,
                        "memory_usage": -1,
                        "error_rate": -1,
                    },
                    "notification_channels": ["email", "webhook"],
                    "email_recipients": ["ops@example.com"],
                    "email": {
                        "sender": "alerts@example.com",
                        "smtp_host": "smtp.example.com",
                        "smtp_port": 25,
                        "username": "alerts-user",
                        "timeout_seconds": 3,
                    },
                },
            },
            "health_check": {
                "enabled": True,
                "readiness_checks": [
                    "config_loaded",
                    "job_manager",
                    "job_storage",
                    "database_connection",
                    "model_loading",
                ],
                "health_metrics": [
                    "cpu_usage",
                    "memory_usage",
                    "disk_space",
                    "database_connection",
                    "model_loading",
                ],
                "alert_thresholds": {
                    "cpu_usage": 100,
                    "memory_usage": 100,
                    "disk_space": 100,
                },
            },
            "models": {
                "llm": {
                    "path": "./models/test-model.gguf",
                }
            },
            "database": {
                "path": "./data/test.db",
            },
            "output": {
                "directory": "./output",
            },
            "web_console": {
                "job_storage_dir": "./output/jobs",
            },
            "logging": {
                "file": "./logs/test.log",
            },
        }
        (self.root / "config.yml").write_text(
            yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        (self.root / "secrets.yml").write_text(
            yaml.safe_dump(
                {
                    "monitoring": {
                        "alerting": {
                            "email": {
                                "password": "super-secret-password",
                            },
                            "webhook_url": "https://example.invalid/alerts",
                        }
                    }
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

        self.settings = load_settings(root_path=self.root)
        self.architecture = create_default_architecture(self.settings)
        self.manager = ResearchJobManager(storage_dir=self.root / "output" / "jobs")
        self.service = MonitoringService(self.settings, self.architecture, self.manager)

    def tearDown(self) -> None:
        self.manager.close()
        self.tempdir.cleanup()

    def test_collect_metrics_returns_health_host_and_alert_sections(self) -> None:
        metrics = self.service.collect_metrics()

        self.assertIn("collected_at", metrics)
        self.assertIn("system", metrics)
        self.assertIn("host", metrics)
        self.assertIn("jobs", metrics)
        self.assertIn("persistence", metrics)
        self.assertIn("health", metrics)
        self.assertIn("alerts", metrics)
        self.assertEqual(metrics["health"]["status"], "ok")
        self.assertEqual(metrics["health"]["summary"]["failed"], 0)
        self.assertEqual(metrics["health"]["summary"]["health_status"], "ok")
        self.assertIn("cpu_usage_percent", metrics["host"])
        self.assertEqual(metrics["jobs"]["total_jobs"], 0)
        self.assertTrue(str(metrics["persistence"]["storage_dir"]).endswith("output\\jobs") or str(metrics["persistence"]["storage_dir"]).endswith("output/jobs"))

    def test_prometheus_export_contains_core_metrics(self) -> None:
        payload = self.service.export_prometheus_metrics()

        self.assertIn("tcm_system_health_score", payload)
        self.assertIn("tcm_jobs_total", payload)
        self.assertIn("tcm_host_cpu_usage_percent", payload)

    @patch("src.infrastructure.monitoring.httpx.post")
    @patch("src.infrastructure.monitoring.smtplib.SMTP")
    def test_collect_metrics_dispatches_email_and_webhook_alerts(self, smtp_mock: MagicMock, httpx_post_mock: MagicMock) -> None:
        smtp_client = MagicMock()
        smtp_mock.return_value.__enter__.return_value = smtp_client
        webhook_response = MagicMock()
        webhook_response.status_code = 200
        webhook_response.raise_for_status.return_value = None
        httpx_post_mock.return_value = webhook_response

        metrics = self.service.collect_metrics()

        self.assertTrue(smtp_client.send_message.called)
        smtp_client.login.assert_called_once_with("alerts-user", "super-secret-password")
        httpx_post_mock.assert_called_once()
        self.assertEqual(httpx_post_mock.call_args.kwargs["json"]["alerts"][0]["message"], metrics["alerts"][0]["message"])
        self.assertTrue(metrics["alerts"])
        for alert in metrics["alerts"]:
            channels = {item["channel"] for item in alert["notifications"]}
            self.assertIn("email", channels)
            self.assertIn("webhook", channels)

    def test_liveness_and_readiness_reports_are_split(self) -> None:
        liveness = self.service.get_liveness_report()
        readiness = self.service.get_readiness_report()

        self.assertEqual(liveness["probe_type"], "liveness")
        self.assertEqual(readiness["probe_type"], "readiness")
        self.assertEqual(liveness["status"], "ok")
        self.assertEqual(readiness["status"], "ok")
        self.assertLess(len(liveness["checks"]), len(readiness["checks"]))
