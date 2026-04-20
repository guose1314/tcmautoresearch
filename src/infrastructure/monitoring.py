"""Architecture 3.0 监控服务：指标采集、健康检查与 Prometheus 导出。"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import socket
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from prometheus_client import CollectorRegistry, Gauge, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST

logger = logging.getLogger(__name__)

try:
    import httpx
except Exception:  # pragma: no cover - 依赖缺失时降级
    httpx = None

try:
    import psutil
except Exception:  # pragma: no cover - 依赖缺失时降级
    psutil = None

from src.core.architecture import SystemArchitecture
from src.infrastructure.config_loader import AppSettings
from src.infrastructure.persistence import DatabaseManager
from web_console.job_manager import ResearchJobManager


def _utc_now() -> str:
    return datetime.now().isoformat()


class MonitoringService:
    """统一采集系统指标并执行健康检查。"""

    def __init__(
        self,
        settings: AppSettings,
        architecture: SystemArchitecture,
        job_manager: ResearchJobManager,
        db_manager: Optional[DatabaseManager] = None,
    ):
        self.settings = settings
        self.architecture = architecture
        self.job_manager = job_manager
        self._db_manager = db_manager
        self.monitoring_config = settings.get_section("monitoring", "system_management.monitoring", default={})
        self.health_check_config = settings.get_section("health_check", "system_management.health_check", default={})
        self._lock = threading.Lock()
        self._alert_lock = threading.Lock()
        self._alert_history: Dict[str, float] = {}
        self._registry = CollectorRegistry(auto_describe=True)
        self._gauges = self._create_gauges()
        self._storage_governance_enabled = bool(self.monitoring_config.get("storage_governance", False))
        if self._storage_governance_enabled:
            self._gauges.update(self._create_storage_governance_gauges())
        self._bound_storage_factory: Optional[Any] = None
        self._structured_storage_summary = self._build_structured_storage_summary()

    def bind_db_manager(self, db_manager: DatabaseManager) -> None:
        self._db_manager = db_manager
        self._structured_storage_summary = self._build_structured_storage_summary()

    def bind_storage_factory(self, factory: Any) -> None:
        """绑定活跃的 StorageBackendFactory 实例以采集运行时指标。

        绑定后 Prometheus gauge 将读取该实例的实时计数器，
        而非每次采集时创建临时 factory（临时 factory 计数器始终为零）。
        """
        self._bound_storage_factory = factory

    def unbind_storage_factory(self) -> None:
        """解除绑定的 StorageBackendFactory。"""
        self._bound_storage_factory = None

    @property
    def bound_storage_factory(self) -> Optional[Any]:
        """当前绑定的 StorageBackendFactory 实例（可为 None）。"""
        return self._bound_storage_factory

    @property
    def prometheus_content_type(self) -> str:
        return CONTENT_TYPE_LATEST

    def collect_metrics(self) -> Dict[str, Any]:
        host_metrics = self._collect_host_metrics()
        job_metrics = self._collect_job_metrics()
        persistence_summary = self._build_persistence_summary()
        health_report = self._build_health_report(host_metrics, job_metrics, persistence_summary)
        alerts = self._build_alerts(host_metrics, job_metrics, health_report)
        self._dispatch_alerts(alerts)
        system_status = self._refresh_architecture_status(host_metrics, job_metrics, health_report)
        architecture_summary = self.architecture.get_architecture_summary()

        payload = {
            "collected_at": _utc_now(),
            "system": {
                "status": system_status,
                "architecture": architecture_summary,
            },
            "host": host_metrics,
            "jobs": job_metrics,
            "persistence": persistence_summary,
            "health": health_report,
            "alerts": alerts,
        }
        self._update_prometheus_gauges(payload)
        return payload

    def get_health_report(self) -> Dict[str, Any]:
        host_metrics = self._collect_host_metrics()
        job_metrics = self._collect_job_metrics()
        persistence_summary = self._build_persistence_summary()
        health_report = self._build_health_report(host_metrics, job_metrics, persistence_summary)
        self._refresh_architecture_status(host_metrics, job_metrics, health_report)
        return health_report

    def get_system_status_snapshot(self) -> Dict[str, Any]:
        host_metrics = self._collect_host_metrics()
        job_metrics = self._collect_job_metrics()
        persistence_summary = self._build_persistence_summary()
        health_report = self._build_health_report(host_metrics, job_metrics, persistence_summary)
        status = self._refresh_architecture_status(host_metrics, job_metrics, health_report)
        system_info = status.get("system_info") if isinstance(status.get("system_info"), dict) else {}
        system_info["environment"] = self.settings.environment
        status["system_info"] = system_info
        metadata = status.get("metadata") if isinstance(status.get("metadata"), dict) else {}
        metadata["config_sources"] = list(self.settings.loaded_files)
        metadata["config_env"] = self.settings.environment
        metadata["monitoring"] = {
            "enabled": bool(self.monitoring_config.get("enabled", True)),
            "collected_at": _utc_now(),
            "overall_status": health_report.get("summary", {}).get("health_status", health_report.get("status", "unknown")),
            "failed_checks": health_report.get("summary", {}).get("failed", 0),
        }
        status["metadata"] = metadata
        status["health_report"] = health_report
        return status

    def get_liveness_report(self) -> Dict[str, Any]:
        checks = [
            self._check_config_loaded(),
            self._check_job_manager(),
        ]
        return self._build_probe_report("liveness", checks)

    def get_readiness_report(self) -> Dict[str, Any]:
        host_metrics = self._collect_host_metrics()
        persistence_summary = self._build_persistence_summary()
        checks = [
            self._resolve_named_check(name, host_metrics, persistence_summary)
            for name in self._get_enabled_readiness_checks()
        ]
        checks = [item for item in checks if item is not None]
        return self._build_probe_report("readiness", checks)

    def export_prometheus_metrics(self) -> str:
        self.collect_metrics()
        return generate_latest(self._registry).decode("utf-8")

    def _create_gauges(self) -> Dict[str, Gauge]:
        return {
            "system_health_score": Gauge(
                "tcm_system_health_score",
                "Overall system health score derived from monitoring checks.",
                registry=self._registry,
            ),
            "total_modules": Gauge(
                "tcm_registered_modules_total",
                "Total registered modules in system architecture.",
                registry=self._registry,
            ),
            "active_modules": Gauge(
                "tcm_active_modules_total",
                "Active modules in system architecture.",
                registry=self._registry,
            ),
            "host_cpu_usage_percent": Gauge(
                "tcm_host_cpu_usage_percent",
                "Host CPU usage percent.",
                registry=self._registry,
            ),
            "host_memory_usage_percent": Gauge(
                "tcm_host_memory_usage_percent",
                "Host memory usage percent.",
                registry=self._registry,
            ),
            "host_disk_usage_percent": Gauge(
                "tcm_host_disk_usage_percent",
                "Host disk usage percent.",
                registry=self._registry,
            ),
            "process_memory_bytes": Gauge(
                "tcm_process_resident_memory_bytes",
                "Current API/Web process resident memory usage.",
                registry=self._registry,
            ),
            "jobs_total": Gauge(
                "tcm_jobs_total",
                "Total known research jobs.",
                registry=self._registry,
            ),
            "jobs_running": Gauge(
                "tcm_jobs_running_total",
                "Currently running research jobs.",
                registry=self._registry,
            ),
            "jobs_failed": Gauge(
                "tcm_jobs_failed_total",
                "Failed research jobs.",
                registry=self._registry,
            ),
            "jobs_completed": Gauge(
                "tcm_jobs_completed_total",
                "Completed research jobs.",
                registry=self._registry,
            ),
            "jobs_partial": Gauge(
                "tcm_jobs_partial_total",
                "Partially completed research jobs.",
                registry=self._registry,
            ),
            "job_error_rate": Gauge(
                "tcm_job_error_rate",
                "Failure rate among terminal jobs.",
                registry=self._registry,
            ),
            "stored_job_count": Gauge(
                "tcm_persistence_stored_jobs_total",
                "Persisted job records in storage.",
                registry=self._registry,
            ),
            "health_failed_checks": Gauge(
                "tcm_health_failed_checks_total",
                "Number of failed health checks in the latest snapshot.",
                registry=self._registry,
            ),
            "health_degraded_checks": Gauge(
                "tcm_health_degraded_checks_total",
                "Number of degraded health checks in the latest snapshot.",
                registry=self._registry,
            ),
        }

    def _create_storage_governance_gauges(self) -> Dict[str, Gauge]:
        """F-2: StorageObservability / DegradationGovernor Prometheus gauges.

        仅在 monitoring.storage_governance 为 true 时调用。
        """
        return {
            # F-2-1 — StorageObservability
            "storage_health_score": Gauge(
                "tcm_storage_health_score",
                "Rolling-window storage health score from StorageObservability.",
                registry=self._registry,
            ),
            "storage_success_rate": Gauge(
                "tcm_storage_success_rate",
                "Rolling-window storage transaction success rate.",
                registry=self._registry,
            ),
            "storage_latency_p50_ms": Gauge(
                "tcm_storage_latency_p50_ms",
                "Rolling-window storage latency p50 in milliseconds.",
                registry=self._registry,
            ),
            "storage_latency_p95_ms": Gauge(
                "tcm_storage_latency_p95_ms",
                "Rolling-window storage latency p95 in milliseconds.",
                registry=self._registry,
            ),
            "storage_latency_p99_ms": Gauge(
                "tcm_storage_latency_p99_ms",
                "Rolling-window storage latency p99 in milliseconds.",
                registry=self._registry,
            ),
            "storage_lifetime_transactions": Gauge(
                "tcm_storage_lifetime_transactions",
                "Total lifetime storage transactions.",
                registry=self._registry,
            ),
            # F-2-1b — BackfillLedger
            "storage_backfill_pending": Gauge(
                "tcm_storage_backfill_pending",
                "Backfill ledger entries in pending state.",
                registry=self._registry,
            ),
            "storage_backfill_completed": Gauge(
                "tcm_storage_backfill_completed",
                "Backfill ledger entries completed.",
                registry=self._registry,
            ),
            "storage_backfill_failed": Gauge(
                "tcm_storage_backfill_failed",
                "Backfill ledger entries failed.",
                registry=self._registry,
            ),
            # F-2-2 — DegradationGovernor
            "storage_mode": Gauge(
                "tcm_storage_mode_info",
                "Current storage mode encoded as label (1=active).",
                ["mode"],
                registry=self._registry,
            ),
            "storage_is_degraded": Gauge(
                "tcm_storage_is_degraded",
                "1 if storage is in degraded mode, 0 otherwise.",
                registry=self._registry,
            ),
            "storage_failure_rate": Gauge(
                "tcm_storage_failure_rate",
                "Lifetime storage transaction failure rate.",
                registry=self._registry,
            ),
            "storage_compensations_total": Gauge(
                "tcm_storage_compensations_total",
                "Lifetime compensation transactions applied.",
                registry=self._registry,
            ),
        }

    def _collect_host_metrics(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "psutil_available": psutil is not None,
            "process_id": os.getpid(),
        }
        if psutil is None:
            return payload

        cpu_usage_percent = float(psutil.cpu_percent(interval=None))
        virtual_memory = psutil.virtual_memory()
        disk_usage = psutil.disk_usage(str(self.settings.root_path))
        network_io = psutil.net_io_counters()
        network_interfaces = psutil.net_if_stats()
        process = psutil.Process(os.getpid())

        payload.update(
            {
                "cpu_usage_percent": cpu_usage_percent,
                "memory_usage_percent": float(virtual_memory.percent),
                "memory_available_bytes": int(virtual_memory.available),
                "memory_total_bytes": int(virtual_memory.total),
                "disk_usage_percent": float(disk_usage.percent),
                "disk_free_bytes": int(disk_usage.free),
                "disk_total_bytes": int(disk_usage.total),
                "network_bytes_sent": int(network_io.bytes_sent),
                "network_bytes_recv": int(network_io.bytes_recv),
                "network_active_interfaces": sum(1 for item in network_interfaces.values() if getattr(item, "isup", False)),
                "process_resident_memory_bytes": int(process.memory_info().rss),
                "process_thread_count": int(process.num_threads()),
                "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            }
        )
        return payload

    def _collect_job_metrics(self) -> Dict[str, Any]:
        metrics = dict(self.job_manager.get_runtime_metrics())
        terminal_jobs = int(metrics.get("terminal_jobs", 0) or 0)
        failed_jobs = int(metrics.get("failed_jobs", 0) or 0)
        total_jobs = int(metrics.get("total_jobs", 0) or 0)
        uptime_seconds = self._get_uptime_seconds()
        metrics["error_rate"] = failed_jobs / terminal_jobs if terminal_jobs > 0 else 0.0
        metrics["events_per_job"] = (float(metrics.get("total_events", 0) or 0.0) / total_jobs) if total_jobs else 0.0
        metrics["throughput_jobs_per_hour"] = (terminal_jobs / (uptime_seconds / 3600.0)) if uptime_seconds > 0 else 0.0
        return metrics

    def _build_persistence_summary(self) -> Dict[str, Any]:
        summary = dict(self.job_manager.get_storage_summary())
        structured = dict(self._structured_storage_summary)
        # 嵌入统一的 StorageConsistencyState — 单一事实源
        consistency_dict = self._get_consistency_state_dict()
        if consistency_dict:
            structured["consistency_state"] = consistency_dict
        summary["structured_storage"] = structured
        return summary

    def _get_consistency_state_dict(self) -> Optional[Dict[str, Any]]:
        """从 StorageBackendFactory 获取一致性状态快照（懒加载，容错）。

        失败时返回带 ``error`` 键的降级字典，而非 None，
        使消费方可区分"未初始化"与"获取失败"。
        """
        try:
            from src.storage import StorageBackendFactory
            factory = StorageBackendFactory(self.settings.materialize_runtime_config())
            try:
                factory.initialize()
                return factory.get_consistency_state().to_dict()
            finally:
                factory.close()
        except Exception as exc:
            logger.warning("获取 StorageConsistencyState 失败: %s", exc)
            return {
                "mode": "fetch_error",
                "error": str(exc),
            }

    def _build_structured_storage_summary(self) -> Dict[str, Any]:
        db_type = self.settings.database_type
        summary: Dict[str, Any] = {
            "configured": bool(self.settings.database_config),
            "db_type": db_type,
            "db_healthy": None,
            "neo4j_enabled": self.settings.neo4j_enabled,
            "schema_drift": {
                "status": "skip",
                "checked_at": _utc_now(),
                "database_type": db_type,
                "legacy_enum_count": 0,
                "incompatible_drift_count": 0,
                "compatibility_variant_count": 0,
                "issues": [],
                "compatibility_variants": [],
                "normalization_report": {},
                "message": "未配置结构化 PostgreSQL 存储或当前环境无需 drift 检查",
            },
        }
        if not summary["configured"]:
            return summary

        if db_type != "postgresql":
            database_path = self.settings.get("database.path")
            if database_path:
                database_file = self._resolve_path(database_path)
                summary["db_path"] = str(database_file)
                summary["db_healthy"] = database_file.parent.exists()
            summary["schema_drift"]["message"] = "当前非 PostgreSQL 环境，schema drift 检查已跳过"
            return summary

        manager = self._db_manager or DatabaseManager(
            self.settings.database_url,
            echo=bool(self.settings.database_config.get("echo", False)),
            connection_timeout=self.settings.database_config.get("connection_timeout"),
            pool_size=self.settings.database_config.get("connection_pool_size"),
            max_overflow=self.settings.database_config.get("max_overflow"),
        )
        owns_manager = self._db_manager is None
        try:
            summary["db_healthy"] = manager.health_check()
            summary["schema_drift"] = manager.inspect_schema_drift()
            summary["schema_normalization"] = manager.get_schema_normalization_report()
        finally:
            if owns_manager:
                manager.close()
        return summary

    def _refresh_architecture_status(
        self,
        host_metrics: Dict[str, Any],
        job_metrics: Dict[str, Any],
        health_report: Dict[str, Any],
    ) -> Dict[str, Any]:
        module_health = self.architecture.module_registry.get_system_health()
        uptime_seconds = self._get_uptime_seconds()
        self.architecture.performance_metrics.update(
            {
                "environment": self.settings.environment,
                "config_sources": list(self.settings.loaded_files),
                "uptime_seconds": uptime_seconds,
                "total_modules": int(module_health.get("total_modules", 0) or 0),
                "active_modules": int(module_health.get("active_modules", 0) or 0),
                "system_health_score": float(health_report.get("overall_health", module_health.get("health_score", 0.0)) or 0.0),
                "quality_assurance_score": self._normalize_ratio(self.architecture.performance_metrics.get("quality_assurance_score", 0.0)),
                "host_cpu_usage_percent": float(host_metrics.get("cpu_usage_percent", 0.0) or 0.0),
                "host_memory_usage_percent": float(host_metrics.get("memory_usage_percent", 0.0) or 0.0),
                "host_disk_usage_percent": float(host_metrics.get("disk_usage_percent", 0.0) or 0.0),
                "job_error_rate": float(job_metrics.get("error_rate", 0.0) or 0.0),
                "job_throughput_per_hour": float(job_metrics.get("throughput_jobs_per_hour", 0.0) or 0.0),
                "stored_job_count": int(self.job_manager.get_storage_summary().get("stored_job_count", 0) or 0),
            }
        )
        return self.architecture.get_system_status()

    def _build_health_report(
        self,
        host_metrics: Dict[str, Any],
        job_metrics: Dict[str, Any],
        persistence_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        checks = self._build_core_checks(persistence_summary)

        for metric_name in self._get_enabled_health_metrics():
            check = self._build_metric_health_check(metric_name, host_metrics)
            if check is not None:
                checks.append(check)

        summary = self._summarize_checks(checks)
        health_status = "ok"
        if summary["critical_failed"] > 0:
            health_status = "error"
        elif summary["failed"] > 0 or summary["degraded"] > 0:
            health_status = "degraded"

        applicable_count = summary["passed"] + summary["degraded"] + summary["failed"]
        overall_health = summary["passed"] / applicable_count if applicable_count else 1.0
        summary["health_status"] = health_status

        return {
            "status": "error" if summary["critical_failed"] > 0 else "ok",
            "system_status": self.architecture.system_status,
            "version": self.architecture.config.version,
            "environment": self.settings.environment,
            "config_sources": list(self.settings.loaded_files),
            "overall_health": round(overall_health, 4),
            "summary": summary,
            "checks": checks,
        }

    def _build_probe_report(self, probe_type: str, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
        summary = self._summarize_checks(checks)
        status = "ok"
        if summary["critical_failed"] > 0 or summary["failed"] > 0:
            status = "error"
        elif summary["degraded"] > 0:
            status = "degraded"

        applicable_count = summary["passed"] + summary["degraded"] + summary["failed"]
        overall_health = summary["passed"] / applicable_count if applicable_count else 1.0
        summary["health_status"] = status
        return {
            "status": status,
            "probe_type": probe_type,
            "environment": self.settings.environment,
            "checked_at": _utc_now(),
            "overall_health": round(overall_health, 4),
            "summary": summary,
            "checks": checks,
        }

    def _build_alerts(
        self,
        host_metrics: Dict[str, Any],
        job_metrics: Dict[str, Any],
        health_report: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        alert_config = self.monitoring_config.get("alerting") if isinstance(self.monitoring_config.get("alerting"), dict) else {}
        thresholds = alert_config.get("thresholds") if isinstance(alert_config.get("thresholds"), dict) else {}
        alerts: List[Dict[str, Any]] = []

        self._append_threshold_alert(alerts, "cpu_usage", host_metrics.get("cpu_usage_percent"), thresholds.get("cpu_usage"))
        self._append_threshold_alert(alerts, "memory_usage", host_metrics.get("memory_usage_percent"), thresholds.get("memory_usage"))
        self._append_threshold_alert(alerts, "error_rate", job_metrics.get("error_rate"), thresholds.get("error_rate"))
        health_status = health_report.get("summary", {}).get("health_status", health_report.get("status", "ok"))
        if health_status in {"degraded", "error"}:
            alerts.append(
                {
                    "metric": "health_status",
                    "severity": "critical" if health_status == "error" else "warning",
                    "message": f"系统健康状态为 {health_status}",
                }
            )
        for alert in alerts:
            alert.setdefault("created_at", _utc_now())
            alert.setdefault("notifications", [])
        return alerts

    def _dispatch_alerts(self, alerts: List[Dict[str, Any]]) -> None:
        if not alerts:
            return

        alert_config = self.monitoring_config.get("alerting") if isinstance(self.monitoring_config.get("alerting"), dict) else {}
        if not bool(alert_config.get("enabled", True)):
            return

        due_alerts: List[Dict[str, Any]] = []
        suppressed_alerts: List[Dict[str, Any]] = []
        for alert in alerts:
            if self._should_dispatch_alert(alert):
                due_alerts.append(alert)
            else:
                suppressed_alerts.append(alert)

        for alert in suppressed_alerts:
            alert["notifications"].append(
                {
                    "channel": "dispatcher",
                    "status": "suppressed",
                    "message": "告警处于冷却窗口，已跳过重复发送",
                }
            )

        if not due_alerts:
            return

        for channel in self._get_notification_channels(alert_config):
            if channel == "email":
                result = self._send_email_notifications(due_alerts, alert_config)
            elif channel in {"webhook", "slack"}:
                result = self._send_webhook_notifications(due_alerts, alert_config, channel)
            else:
                result = {
                    "channel": channel,
                    "status": "skipped",
                    "message": "未实现的通知通道",
                }

            for alert in due_alerts:
                alert["notifications"].append(dict(result))

        self._mark_alerts_dispatched(due_alerts)

    def _append_threshold_alert(
        self,
        alerts: List[Dict[str, Any]],
        metric_name: str,
        value: Any,
        threshold: Any,
        *,
        reverse: bool = False,
    ) -> None:
        if threshold is None or value is None:
            return
        try:
            numeric_value = float(value)
            numeric_threshold = float(threshold)
        except (TypeError, ValueError):
            return

        exceeded = numeric_value < numeric_threshold if reverse else numeric_value > numeric_threshold
        if not exceeded:
            return

        alerts.append(
            {
                "metric": metric_name,
                "severity": "warning",
                "value": numeric_value,
                "threshold": numeric_threshold,
                "message": f"{metric_name} 超过阈值",
            }
        )

    def _check_config_loaded(self) -> Dict[str, Any]:
        loaded = bool(self.settings.loaded_files)
        return {
            "name": "config_loaded",
            "status": "pass" if loaded else "fail",
            "critical": True,
            "observed_value": len(self.settings.loaded_files),
            "message": "配置源已加载" if loaded else "未加载配置源",
        }

    def _check_job_manager(self) -> Dict[str, Any]:
        available = self.job_manager is not None
        return {
            "name": "job_manager",
            "status": "pass" if available else "fail",
            "critical": True,
            "message": "任务管理器可用" if available else "任务管理器不可用",
        }

    def _check_storage_writable(self, persistence_summary: Dict[str, Any]) -> Dict[str, Any]:
        storage_dir = Path(str(persistence_summary.get("storage_dir") or self.settings.job_storage_dir)).expanduser()
        try:
            storage_dir.mkdir(parents=True, exist_ok=True)
            writable = os.access(storage_dir, os.W_OK)
        except OSError:
            writable = False
        return {
            "name": "job_storage",
            "status": "pass" if writable else "fail",
            "critical": True,
            "path": str(storage_dir),
            "message": "任务持久化目录可写" if writable else "任务持久化目录不可写",
        }

    def _build_core_checks(self, persistence_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            self._check_config_loaded(),
            self._check_job_manager(),
            self._check_storage_writable(persistence_summary),
            self._build_database_schema_check(persistence_summary),
        ]

    def _resolve_named_check(
        self,
        check_name: str,
        host_metrics: Dict[str, Any],
        persistence_summary: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        builders = {
            "config_loaded": self._check_config_loaded,
            "job_manager": self._check_job_manager,
            "job_storage": lambda: self._check_storage_writable(persistence_summary),
            "database_connection": lambda: self._build_database_check(persistence_summary),
            "database_schema_drift": lambda: self._build_database_schema_check(persistence_summary),
            "schema_drift": lambda: self._build_database_schema_check(persistence_summary),
            "model_loading": self._build_model_check,
            "cpu_usage": lambda: self._build_metric_health_check("cpu_usage", host_metrics),
            "memory_usage": lambda: self._build_metric_health_check("memory_usage", host_metrics),
            "disk_space": lambda: self._build_metric_health_check("disk_space", host_metrics),
            "network_connectivity": lambda: self._build_metric_health_check("network_connectivity", host_metrics),
        }
        builder = builders.get(check_name)
        if builder is None:
            return None
        return builder()

    def _build_metric_health_check(self, metric_name: str, host_metrics: Dict[str, Any]) -> Dict[str, Any] | None:
        builders = {
            "cpu_usage": lambda: self._build_threshold_check(
                "cpu_usage",
                host_metrics.get("cpu_usage_percent"),
                self._resolve_health_threshold("cpu_usage", 85),
                "CPU 使用率正常",
                "CPU 使用率过高",
            ),
            "memory_usage": lambda: self._build_threshold_check(
                "memory_usage",
                host_metrics.get("memory_usage_percent"),
                self._resolve_health_threshold("memory_usage", 85),
                "内存使用率正常",
                "内存使用率过高",
            ),
            "disk_space": lambda: self._build_threshold_check(
                "disk_space",
                host_metrics.get("disk_usage_percent"),
                self._resolve_health_threshold("disk_space", 90),
                "磁盘使用率正常",
                "磁盘使用率过高",
            ),
            "disk_usage": lambda: self._build_threshold_check(
                "disk_usage",
                host_metrics.get("disk_usage_percent"),
                self._resolve_health_threshold("disk_space", 90),
                "磁盘使用率正常",
                "磁盘使用率过高",
            ),
            "network_connectivity": lambda: self._build_network_check(host_metrics),
            "database_connection": lambda: self._build_database_check(self._build_persistence_summary()),
            "model_loading": self._build_model_check,
        }
        builder = builders.get(metric_name)
        if builder is None:
            return None
        return builder()

    def _build_threshold_check(
        self,
        name: str,
        value: Any,
        threshold: float,
        pass_message: str,
        fail_message: str,
    ) -> Dict[str, Any]:
        if value is None:
            return {
                "name": name,
                "status": "skip",
                "critical": False,
                "threshold": threshold,
                "message": f"{name} 指标不可用",
            }

        numeric_value = float(value)
        status = "pass" if numeric_value <= threshold else "fail"
        return {
            "name": name,
            "status": status,
            "critical": False,
            "observed_value": round(numeric_value, 4),
            "threshold": threshold,
            "message": pass_message if status == "pass" else fail_message,
        }

    def _build_network_check(self, host_metrics: Dict[str, Any]) -> Dict[str, Any]:
        active_interfaces = int(host_metrics.get("network_active_interfaces", 0) or 0)
        localhost_resolved = False
        try:
            localhost_resolved = bool(socket.gethostbyname("localhost"))
        except OSError:
            localhost_resolved = False

        healthy = active_interfaces > 0 and localhost_resolved
        return {
            "name": "network_connectivity",
            "status": "pass" if healthy else "fail",
            "critical": False,
            "observed_value": active_interfaces,
            "message": "网络接口可用" if healthy else "未检测到可用网络接口",
        }

    def _build_database_check(self, persistence_summary: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        structured_storage = (
            dict((persistence_summary or {}).get("structured_storage") or {})
            if isinstance((persistence_summary or {}).get("structured_storage"), dict)
            else dict(self._structured_storage_summary)
        )
        if structured_storage.get("db_type") == "postgresql":
            healthy = bool(structured_storage.get("db_healthy"))
            return {
                "name": "database_connection",
                "status": "pass" if healthy else "fail",
                "critical": False,
                "database_type": "postgresql",
                "message": "PostgreSQL 连接可用" if healthy else "PostgreSQL 连接不可用",
            }

        database_path = self.settings.get("database.path")
        if not database_path:
            return {
                "name": "database_connection",
                "status": "skip",
                "critical": False,
                "message": "未配置数据库路径",
            }

        database_file = self._resolve_path(database_path)
        try:
            database_file.parent.mkdir(parents=True, exist_ok=True)
            healthy = os.access(database_file.parent, os.W_OK)
        except OSError:
            healthy = False
        return {
            "name": "database_connection",
            "status": "pass" if healthy else "fail",
            "critical": False,
            "path": str(database_file),
            "message": "数据库路径可访问" if healthy else "数据库路径不可访问",
        }

    def _build_database_schema_check(self, persistence_summary: Dict[str, Any]) -> Dict[str, Any]:
        structured_storage = (
            dict(persistence_summary.get("structured_storage") or {})
            if isinstance(persistence_summary.get("structured_storage"), dict)
            else {}
        )
        schema_drift = (
            dict(structured_storage.get("schema_drift") or {})
            if isinstance(structured_storage.get("schema_drift"), dict)
            else {}
        )
        if not schema_drift:
            return {
                "name": "database_schema_drift",
                "status": "skip",
                "critical": False,
                "message": "未提供 schema drift 诊断信息",
            }

        drift_status = str(schema_drift.get("status") or "skip")
        if drift_status == "skip":
            return {
                "name": "database_schema_drift",
                "status": "skip",
                "critical": False,
                "details": schema_drift,
                "message": str(schema_drift.get("message") or "schema drift 检查已跳过"),
            }

        incompatible_count = int(schema_drift.get("incompatible_drift_count") or 0)
        legacy_enum_count = int(schema_drift.get("legacy_enum_count") or 0)
        compatibility_variant_count = int(schema_drift.get("compatibility_variant_count") or 0)
        normalization_report = (
            dict(schema_drift.get("normalization_report") or {})
            if isinstance(schema_drift.get("normalization_report"), dict)
            else {}
        )
        normalized_enum_count = int(normalization_report.get("normalized_enum_count") or 0)

        if incompatible_count > 0 or drift_status == "error":
            status = "fail"
        elif legacy_enum_count > 0:
            status = "degraded"
        else:
            status = "pass"

        if status == "fail":
            message = f"检测到 {incompatible_count} 个不兼容 schema drift"
        elif status == "degraded":
            message = f"检测到 {legacy_enum_count} 个 legacy enum drift；启动期已自动规范 {normalized_enum_count} 组标签"
        elif compatibility_variant_count > 0:
            message = f"未检测到不兼容 drift；发现 {compatibility_variant_count} 个兼容存储差异"
        else:
            message = "未检测到 schema drift"

        return {
            "name": "database_schema_drift",
            "status": status,
            "critical": False,
            "observed_value": {
                "legacy_enum_count": legacy_enum_count,
                "incompatible_drift_count": incompatible_count,
                "compatibility_variant_count": compatibility_variant_count,
                "normalized_enum_count": normalized_enum_count,
            },
            "details": schema_drift,
            "message": message,
        }

    def _build_model_check(self) -> Dict[str, Any]:
        model_path = self.settings.get("models.llm.path")
        if not model_path:
            return {
                "name": "model_loading",
                "status": "skip",
                "critical": False,
                "message": "未配置 LLM 模型路径",
            }

        model_file = self._resolve_path(model_path)
        exists = model_file.exists()
        status = "pass" if exists else "degraded"
        return {
            "name": "model_loading",
            "status": status,
            "critical": False,
            "path": str(model_file),
            "message": "模型文件可用" if exists else "模型文件不存在，运行时可能降级或失败",
        }

    def _summarize_checks(self, checks: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        summary = {
            "total": 0,
            "passed": 0,
            "degraded": 0,
            "failed": 0,
            "skipped": 0,
            "critical_failed": 0,
        }
        for item in checks:
            summary["total"] += 1
            status = str(item.get("status") or "skip")
            if status == "pass":
                summary["passed"] += 1
            elif status == "degraded":
                summary["degraded"] += 1
            elif status == "fail":
                summary["failed"] += 1
                if item.get("critical"):
                    summary["critical_failed"] += 1
            else:
                summary["skipped"] += 1
        return summary

    def _resolve_health_threshold(self, metric_name: str, default: float) -> float:
        thresholds = self.health_check_config.get("alert_thresholds") if isinstance(self.health_check_config.get("alert_thresholds"), dict) else {}
        value = thresholds.get(metric_name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def _get_enabled_health_metrics(self) -> List[str]:
        configured = self.health_check_config.get("health_metrics")
        if isinstance(configured, list) and configured:
            return [str(item).strip() for item in configured if str(item).strip()]
        return ["cpu_usage", "memory_usage", "disk_space", "database_connection"]

    def _get_enabled_readiness_checks(self) -> List[str]:
        configured = self.health_check_config.get("readiness_checks")
        if isinstance(configured, list) and configured:
            return [str(item).strip() for item in configured if str(item).strip()]
        return ["config_loaded", "job_manager", "job_storage", "database_connection", "model_loading"]

    def _get_notification_channels(self, alert_config: Dict[str, Any]) -> List[str]:
        configured = alert_config.get("notification_channels")
        if isinstance(configured, list) and configured:
            return [str(item).strip().lower() for item in configured if str(item).strip()]
        return []

    def _should_dispatch_alert(self, alert: Dict[str, Any]) -> bool:
        resend_interval_seconds = self._resolve_int(
            self.monitoring_config.get("alerting", {}).get("resend_interval_seconds")
            if isinstance(self.monitoring_config.get("alerting"), dict)
            else None,
            300,
        )
        signature = self._alert_signature(alert)
        with self._alert_lock:
            last_sent_at = self._alert_history.get(signature)
            if last_sent_at is None:
                return True
            return (time.time() - last_sent_at) >= resend_interval_seconds

    def _mark_alerts_dispatched(self, alerts: List[Dict[str, Any]]) -> None:
        now = time.time()
        with self._alert_lock:
            for alert in alerts:
                self._alert_history[self._alert_signature(alert)] = now

    def _alert_signature(self, alert: Dict[str, Any]) -> str:
        payload = {
            "metric": alert.get("metric"),
            "severity": alert.get("severity"),
            "message": alert.get("message"),
            "threshold": alert.get("threshold"),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def _send_email_notifications(self, alerts: List[Dict[str, Any]], alert_config: Dict[str, Any]) -> Dict[str, Any]:
        email_config = alert_config.get("email") if isinstance(alert_config.get("email"), dict) else {}
        recipients = email_config.get("recipients")
        if not isinstance(recipients, list) or not recipients:
            recipients = alert_config.get("email_recipients") if isinstance(alert_config.get("email_recipients"), list) else []
        recipients = [str(item).strip() for item in recipients if str(item).strip()]
        if not recipients:
            return {
                "channel": "email",
                "status": "skipped",
                "message": "未配置邮件接收人",
            }

        smtp_host = self._first_non_empty(
            self.settings.get_secret("monitoring.alerting.email.smtp_host"),
            email_config.get("smtp_host"),
            os.getenv("MONITORING_ALERT_SMTP_HOST"),
            os.getenv("SMTP_HOST"),
        )
        sender = self._first_non_empty(
            self.settings.get_secret("monitoring.alerting.email.sender"),
            email_config.get("sender"),
            os.getenv("MONITORING_ALERT_EMAIL_SENDER"),
            os.getenv("SMTP_SENDER"),
            recipients[0],
        )
        if not smtp_host:
            return {
                "channel": "email",
                "status": "skipped",
                "message": "未配置 SMTP 主机",
            }

        smtp_port = self._resolve_int(
            self._first_non_empty(
                self.settings.get_secret("monitoring.alerting.email.smtp_port"),
                email_config.get("smtp_port"),
                os.getenv("MONITORING_ALERT_SMTP_PORT"),
                os.getenv("SMTP_PORT"),
            ),
            25,
        )
        username = self._first_non_empty(
            self.settings.get_secret("monitoring.alerting.email.username"),
            email_config.get("username"),
            os.getenv("MONITORING_ALERT_SMTP_USERNAME"),
            os.getenv("SMTP_USERNAME"),
        )
        password = self._first_non_empty(
            self.settings.get_secret("monitoring.alerting.email.password"),
            email_config.get("password"),
            os.getenv("MONITORING_ALERT_SMTP_PASSWORD"),
            os.getenv("SMTP_PASSWORD"),
        )
        use_tls = self._resolve_bool(
            self._first_non_empty(
                self.settings.get_secret("monitoring.alerting.email.use_tls"),
                email_config.get("use_tls"),
                os.getenv("MONITORING_ALERT_SMTP_TLS"),
            ),
            False,
        )
        use_ssl = self._resolve_bool(
            self._first_non_empty(
                self.settings.get_secret("monitoring.alerting.email.use_ssl"),
                email_config.get("use_ssl"),
                os.getenv("MONITORING_ALERT_SMTP_SSL"),
            ),
            False,
        )
        timeout_seconds = self._resolve_int(email_config.get("timeout_seconds"), 10)

        message = EmailMessage()
        message["Subject"] = self._build_email_subject(alerts)
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message.set_content(self._build_email_body(alerts))

        try:
            smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
            with smtp_cls(smtp_host, smtp_port, timeout=timeout_seconds) as client:
                if use_tls and not use_ssl:
                    client.starttls()
                if username:
                    client.login(username, password or "")
                client.send_message(message)
        except Exception as exc:
            return {
                "channel": "email",
                "status": "failed",
                "message": str(exc),
                "recipient_count": len(recipients),
            }

        return {
            "channel": "email",
            "status": "sent",
            "message": "邮件告警已发送",
            "recipient_count": len(recipients),
        }

    def _send_webhook_notifications(
        self,
        alerts: List[Dict[str, Any]],
        alert_config: Dict[str, Any],
        channel: str,
    ) -> Dict[str, Any]:
        webhook_url = self._first_non_empty(
            self.settings.get_secret("monitoring.alerting.webhook_url", f"monitoring.alerting.{channel}.webhook_url"),
            alert_config.get("webhook_url"),
            os.getenv("MONITORING_ALERT_WEBHOOK_URL"),
            os.getenv("ALERT_WEBHOOK_URL"),
        )
        if not webhook_url:
            return {
                "channel": channel,
                "status": "skipped",
                "message": "未配置 webhook URL",
            }
        if httpx is None:
            return {
                "channel": channel,
                "status": "failed",
                "message": "httpx 不可用，无法发送 webhook",
            }

        payload = {
            "channel": channel,
            "environment": self.settings.environment,
            "sent_at": _utc_now(),
            "alert_count": len(alerts),
            "alerts": [
                {
                    "metric": alert.get("metric"),
                    "severity": alert.get("severity"),
                    "value": alert.get("value"),
                    "threshold": alert.get("threshold"),
                    "message": alert.get("message"),
                    "created_at": alert.get("created_at"),
                }
                for alert in alerts
            ],
        }
        timeout_seconds = self._resolve_int(alert_config.get("timeout_seconds"), 10)

        try:
            response = httpx.post(webhook_url, json=payload, timeout=timeout_seconds)
            response.raise_for_status()
        except Exception as exc:
            return {
                "channel": channel,
                "status": "failed",
                "message": str(exc),
            }

        return {
            "channel": channel,
            "status": "sent",
            "message": "Webhook 告警已发送",
            "status_code": response.status_code,
        }

    def _build_email_subject(self, alerts: List[Dict[str, Any]]) -> str:
        highest_severity = "warning"
        if any(str(alert.get("severity")) == "critical" for alert in alerts):
            highest_severity = "critical"
        return f"[{self.settings.environment}] TCM Auto Research {highest_severity} alerts ({len(alerts)})"

    def _build_email_body(self, alerts: List[Dict[str, Any]]) -> str:
        lines = [
            f"环境: {self.settings.environment}",
            f"时间: {_utc_now()}",
            f"告警数量: {len(alerts)}",
            "",
        ]
        for index, alert in enumerate(alerts, start=1):
            lines.extend(
                [
                    f"{index}. metric={alert.get('metric')}",
                    f"   severity={alert.get('severity')}",
                    f"   value={alert.get('value')}",
                    f"   threshold={alert.get('threshold')}",
                    f"   message={alert.get('message')}",
                ]
            )
        return "\n".join(lines)

    def _first_non_empty(self, *values: Any) -> str | None:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _resolve_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _resolve_bool(self, value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    def _get_uptime_seconds(self) -> float:
        if not self.architecture.start_time:
            return 0.0
        return max((datetime.now() - self.architecture.start_time).total_seconds(), 0.0)

    def _resolve_path(self, value: Any) -> Path:
        candidate = Path(str(value)).expanduser()
        if candidate.is_absolute():
            return candidate
        return (self.settings.root_path / candidate).resolve()

    def _normalize_ratio(self, value: Any) -> float:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(numeric, 1.0))

    def _update_prometheus_gauges(self, payload: Dict[str, Any]) -> None:
        with self._lock:
            host = payload.get("host") if isinstance(payload.get("host"), dict) else {}
            jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
            persistence = payload.get("persistence") if isinstance(payload.get("persistence"), dict) else {}
            health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
            system = payload.get("system") if isinstance(payload.get("system"), dict) else {}
            system_status = system.get("status") if isinstance(system.get("status"), dict) else {}
            performance_metrics = system_status.get("performance_metrics") if isinstance(system_status.get("performance_metrics"), dict) else {}

            self._gauges["system_health_score"].set(float(health.get("overall_health", 0.0) or 0.0))
            self._gauges["total_modules"].set(float(performance_metrics.get("total_modules", 0) or 0))
            self._gauges["active_modules"].set(float(performance_metrics.get("active_modules", 0) or 0))
            self._gauges["host_cpu_usage_percent"].set(float(host.get("cpu_usage_percent", 0.0) or 0.0))
            self._gauges["host_memory_usage_percent"].set(float(host.get("memory_usage_percent", 0.0) or 0.0))
            self._gauges["host_disk_usage_percent"].set(float(host.get("disk_usage_percent", 0.0) or 0.0))
            self._gauges["process_memory_bytes"].set(float(host.get("process_resident_memory_bytes", 0.0) or 0.0))
            self._gauges["jobs_total"].set(float(jobs.get("total_jobs", 0) or 0))
            self._gauges["jobs_running"].set(float(jobs.get("running_jobs", 0) or 0))
            self._gauges["jobs_failed"].set(float(jobs.get("failed_jobs", 0) or 0))
            self._gauges["jobs_completed"].set(float(jobs.get("completed_jobs", 0) or 0))
            self._gauges["jobs_partial"].set(float(jobs.get("partial_jobs", 0) or 0))
            self._gauges["job_error_rate"].set(float(jobs.get("error_rate", 0.0) or 0.0))
            self._gauges["stored_job_count"].set(float(persistence.get("stored_job_count", 0) or 0))
            summary = health.get("summary") if isinstance(health.get("summary"), dict) else {}
            self._gauges["health_failed_checks"].set(float(summary.get("failed", 0) or 0))
            self._gauges["health_degraded_checks"].set(float(summary.get("degraded", 0) or 0))

            # F-2: 存储治理指标
            if self._storage_governance_enabled:
                self._update_storage_governance_gauges()

    def _resolve_storage_factory(self) -> Optional[Any]:
        """返回可用的 StorageBackendFactory 实例。

        优先使用 ``bind_storage_factory()`` 绑定的活跃实例（含真实运行时计数器），
        若无绑定则回退到创建临时实例（仅能获取配置/模式信息，计数器为零）。
        """
        if self._bound_storage_factory is not None:
            return self._bound_storage_factory
        try:
            from src.storage import StorageBackendFactory
            factory = StorageBackendFactory(self.settings.materialize_runtime_config())
            factory.initialize()
            return factory
        except Exception as exc:
            logger.debug("存储治理指标采集失败（临时 factory 创建失败）: %s", exc)
            return None

    def _update_storage_governance_gauges(self) -> None:
        """从 StorageBackendFactory 拉取 observability + governor + backfill 指标并更新 Prometheus gauges。"""
        factory = self._resolve_storage_factory()
        if factory is None:
            return
        is_transient = factory is not self._bound_storage_factory
        try:
            obs_report = factory.observability.get_health_report()
            gov_report = factory.degradation_governor.to_governance_report()
            backfill_summary = factory.backfill_ledger.get_summary()
        except Exception as exc:
            logger.debug("存储治理指标采集失败: %s", exc)
            return
        finally:
            if is_transient:
                try:
                    factory.close()
                except Exception:
                    pass

        # F-2-1 — StorageObservability
        self._gauges["storage_health_score"].set(float(obs_report.get("health_score", 0.0) or 0.0))
        window_metrics = obs_report.get("window_metrics") if isinstance(obs_report.get("window_metrics"), dict) else {}
        self._gauges["storage_success_rate"].set(float(window_metrics.get("success_rate", 0.0) or 0.0))
        latency = obs_report.get("latency_ms") if isinstance(obs_report.get("latency_ms"), dict) else {}
        self._gauges["storage_latency_p50_ms"].set(float(latency.get("p50", 0.0) or 0.0))
        self._gauges["storage_latency_p95_ms"].set(float(latency.get("p95", 0.0) or 0.0))
        self._gauges["storage_latency_p99_ms"].set(float(latency.get("p99", 0.0) or 0.0))
        self._gauges["storage_lifetime_transactions"].set(float(obs_report.get("lifetime_transactions", 0) or 0))

        # F-2-1b — BackfillLedger
        self._gauges["storage_backfill_pending"].set(float(backfill_summary.get("pending", 0) or 0))
        self._gauges["storage_backfill_completed"].set(float(backfill_summary.get("completed", 0) or 0))
        self._gauges["storage_backfill_failed"].set(float(backfill_summary.get("failed", 0) or 0))

        # F-2-2 — DegradationGovernor
        current_mode = str(gov_report.get("current_mode", "unknown"))
        for mode_label in ("dual_write", "pg_only", "sqlite_fallback", "uninitialized"):
            self._gauges["storage_mode"].labels(mode=mode_label).set(1.0 if mode_label == current_mode else 0.0)
        self._gauges["storage_is_degraded"].set(1.0 if gov_report.get("is_degraded") else 0.0)
        gov_metrics = gov_report.get("metrics") if isinstance(gov_report.get("metrics"), dict) else {}
        total_tx = int(gov_metrics.get("total_transactions", 0) or 0)
        failed_tx = int(gov_metrics.get("failed_transactions", 0) or 0)
        self._gauges["storage_failure_rate"].set(failed_tx / total_tx if total_tx > 0 else 0.0)
        self._gauges["storage_compensations_total"].set(float(gov_metrics.get("compensations_applied", 0) or 0))