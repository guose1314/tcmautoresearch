"""Shared dependencies for the Architecture 3.0 REST API."""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Mapping, TypeVar

from fastapi import HTTPException, Request, WebSocket

from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.preprocessor import DocumentPreprocessor
from src.collector.normalizer import Normalizer
from src.core.architecture import ModuleInfo, ModuleType, SystemArchitecture
from src.core.module_interface import ModuleStatus
from src.extraction.relation_extractor import RelationExtractor
from src.infrastructure.config_loader import AppSettings, load_settings
from src.infrastructure.monitoring import MonitoringService
from web_console.job_manager import ResearchJobManager

if TYPE_CHECKING:
    from web_console.console_auth import ConsoleAuthService

ServiceT = TypeVar("ServiceT")
MANAGEMENT_API_KEY_HEADER = "X-API-Key"


def _get_management_api_key(settings: AppSettings) -> str:
    candidates = (
        settings.get_secret(
            "security.management_api_key",
            "security.access_control.management_api_key",
            "api.management_api_key",
            default="",
        ),
        settings.get("security.management_api_key", ""),
        settings.get("security.access_control.management_api_key", ""),
        settings.get("api.management_api_key", ""),
    )
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _extract_presented_api_key(carrier: Mapping[str, str], query_params: Mapping[str, str] | None = None) -> str:
    direct_key = str(carrier.get(MANAGEMENT_API_KEY_HEADER, "") or carrier.get(MANAGEMENT_API_KEY_HEADER.lower(), "")).strip()
    if direct_key:
        return direct_key

    authorization = str(carrier.get("Authorization", "") or carrier.get("authorization", "")).strip()
    if authorization.lower().startswith("bearer "):
        bearer_token = authorization[7:].strip()
        if bearer_token:
            return bearer_token

    if query_params is not None:
        query_key = str(query_params.get("api_key", "")).strip()
        if query_key:
            return query_key

    return ""


def extract_presented_auth_credential(carrier: Mapping[str, str], query_params: Mapping[str, str] | None = None) -> str:
    return _extract_presented_api_key(carrier, query_params)


def is_management_auth_enabled(settings: AppSettings) -> bool:
    return bool(_get_management_api_key(settings))


def verify_management_api_key(
    presented_key: str,
    settings: AppSettings,
) -> None:
    expected_key = _get_management_api_key(settings)
    if not expected_key:
        return
    if not presented_key or not secrets.compare_digest(presented_key, expected_key):
        raise HTTPException(
            status_code=401,
            detail="缺少或无效的管理 API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_console_auth_service_from_state(state: Any, settings: AppSettings) -> "ConsoleAuthService":
    from web_console.console_auth import ConsoleAuthService

    service = getattr(state, "console_auth_service", None)
    if service is None:
        service = ConsoleAuthService(settings)
        state.console_auth_service = service
    return service


def get_console_auth_service(request: Request) -> "ConsoleAuthService":
    settings = get_settings(request)
    return get_console_auth_service_from_state(request.app.state, settings)


def resolve_authenticated_console_principal(
    presented_key: str,
    settings: AppSettings,
    console_auth_service: "ConsoleAuthService",
) -> dict[str, Any]:
    normalized_key = str(presented_key or "").strip()
    expected_key = _get_management_api_key(settings)
    if expected_key and normalized_key and secrets.compare_digest(normalized_key, expected_key):
        return {
            "principal": "管理 API Key",
            "auth_source": "management_api_key",
        }

    session = console_auth_service.resolve_session(normalized_key)
    if session is not None:
        return session.to_public_dict()

    if not expected_key and not console_auth_service.auth_required:
        return {
            "principal": "访客",
            "auth_source": "open",
        }

    raise HTTPException(
        status_code=401,
        detail="缺少或无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_management_api_key(request: Request) -> None:
    settings = get_settings(request)
    console_auth_service = get_console_auth_service_from_state(request.app.state, settings)
    presented_key = _extract_presented_api_key(request.headers, request.query_params)
    request.state.auth_context = resolve_authenticated_console_principal(
        presented_key,
        settings,
        console_auth_service,
    )


def verify_management_api_key_for_websocket(websocket: WebSocket) -> None:
    settings = getattr(websocket.app.state, "settings", None)
    if settings is None:
        settings = load_settings()
        websocket.app.state.settings = settings
    console_auth_service = get_console_auth_service_from_state(websocket.app.state, settings)
    presented_key = _extract_presented_api_key(websocket.headers, websocket.query_params)
    resolve_authenticated_console_principal(
        presented_key,
        settings,
        console_auth_service,
    )


def create_default_architecture(settings: AppSettings | None = None) -> SystemArchitecture:
    resolved_settings = settings or load_settings()
    system_standards = resolved_settings.get("system.standards") or ["T/C IATCM 098-2023"]
    system_principles = resolved_settings.get("system.principles") or ["系统性原则", "科学性原则", "实用性原则"]
    architecture = SystemArchitecture(
        {
            "system_name": resolved_settings.system_name,
            "version": resolved_settings.api_version,
            "description": resolved_settings.system_description,
            "standards": list(system_standards),
            "principles": list(system_principles),
            "performance_target": dict(resolved_settings.get("performance", {})),
            "quality_requirements": dict(resolved_settings.get("academic.research_quality.quality_metrics", {})),
            "security_config": dict(resolved_settings.get("security", {})),
            "monitoring_config": dict(resolved_settings.get("monitoring", {})),
        }
    )
    architecture.system_status = "running"
    architecture.start_time = datetime.now()
    architecture.performance_metrics["environment"] = resolved_settings.environment
    architecture.performance_metrics["config_sources"] = list(resolved_settings.loaded_files)

    if architecture.get_module_list():
        return architecture

    created_at = datetime.now().isoformat()
    default_modules = [
        ModuleInfo(
            module_id="api.rest_service",
            module_name="FastAPI REST Service",
            module_type=ModuleType.MONITORING,
            version=architecture.config.version,
            status=ModuleStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            dependencies=["research.job_manager", "collector.normalizer", "analysis.document_preprocessor"],
            metadata={
                "bounded_context": "api",
                "contract": "v1",
                "environment": resolved_settings.environment,
            },
        ),
        ModuleInfo(
            module_id="research.job_manager",
            module_name="Research Job Manager",
            module_type=ModuleType.RESEARCH,
            version=architecture.config.version,
            status=ModuleStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            dependencies=[],
            metadata={
                "bounded_context": "research",
                "responsibility": "job orchestration",
                "storage_dir": resolved_settings.job_storage_dir,
            },
        ),
        ModuleInfo(
            module_id="infrastructure.monitoring_service",
            module_name="Monitoring Service",
            module_type=ModuleType.MONITORING,
            version=architecture.config.version,
            status=ModuleStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            dependencies=["research.job_manager"],
            metadata={
                "bounded_context": "infrastructure",
                "responsibility": "metrics collection and health checks",
                "environment": resolved_settings.environment,
            },
        ),
        ModuleInfo(
            module_id="collector.normalizer",
            module_name="Document Normalizer",
            module_type=ModuleType.PREPROCESSING,
            version=architecture.config.version,
            status=ModuleStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            dependencies=[],
            metadata={"bounded_context": "collector", "dto": "StandardDocument"},
        ),
        ModuleInfo(
            module_id="analysis.document_preprocessor",
            module_name="Document Preprocessor",
            module_type=ModuleType.ANALYSIS,
            version=architecture.config.version,
            status=ModuleStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            dependencies=["collector.normalizer"],
            metadata={"bounded_context": "analysis", "dto": "AnalysisResult"},
        ),
        ModuleInfo(
            module_id="analysis.entity_extractor",
            module_name="Advanced Entity Extractor",
            module_type=ModuleType.ANALYSIS,
            version=architecture.config.version,
            status=ModuleStatus.ACTIVE,
            created_at=created_at,
            updated_at=created_at,
            dependencies=["analysis.document_preprocessor"],
            metadata={"bounded_context": "analysis", "dto": "AnalysisResult"},
        ),
    ]
    for module in default_modules:
        architecture.register_module(module)

    architecture.performance_metrics["active_modules"] = len(architecture.get_module_list())
    architecture.performance_metrics["system_health_score"] = 1.0
    return architecture


def get_job_manager(request: Request) -> ResearchJobManager:
    manager = getattr(request.app.state, "job_manager", None)
    if manager is None:
        raise HTTPException(status_code=500, detail="job manager 未配置")
    return manager


def get_settings(request: Request) -> AppSettings:
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        settings = load_settings()
        request.app.state.settings = settings
    return settings


def get_architecture(request: Request) -> SystemArchitecture:
    architecture = getattr(request.app.state, "architecture", None)
    if architecture is None:
        architecture = create_default_architecture(get_settings(request))
        request.app.state.architecture = architecture
    return architecture


def create_default_monitoring_service(
    settings: AppSettings,
    architecture: SystemArchitecture,
    job_manager: ResearchJobManager,
) -> MonitoringService:
    return MonitoringService(settings=settings, architecture=architecture, job_manager=job_manager)


def get_monitoring_service(request: Request) -> MonitoringService:
    monitoring_service = getattr(request.app.state, "monitoring_service", None)
    if monitoring_service is None:
        monitoring_service = create_default_monitoring_service(
            get_settings(request),
            get_architecture(request),
            get_job_manager(request),
        )
        request.app.state.monitoring_service = monitoring_service
    return monitoring_service


def _get_or_create_initialized_service(
    request: Request,
    state_key: str,
    display_name: str,
    factory: Callable[[], ServiceT],
    initialize: Callable[[ServiceT], bool],
) -> ServiceT:
    service = getattr(request.app.state, state_key, None)
    if service is None:
        service = factory()
        if not initialize(service):
            raise HTTPException(status_code=500, detail=f"{display_name} 初始化失败")
        setattr(request.app.state, state_key, service)
    return service


def get_normalizer(request: Request) -> Normalizer:
    settings = get_settings(request)
    return _get_or_create_initialized_service(
        request,
        "normalizer",
        "Normalizer",
        lambda: Normalizer(),
        lambda instance: instance.initialize(settings.module_config("normalizer")),
    )


def get_preprocessor(request: Request) -> DocumentPreprocessor:
    settings = get_settings(request)
    return _get_or_create_initialized_service(
        request,
        "document_preprocessor",
        "DocumentPreprocessor",
        lambda: DocumentPreprocessor(),
        lambda instance: instance.initialize(settings.module_config("document_preprocessor")),
    )


def get_entity_extractor(request: Request) -> AdvancedEntityExtractor:
    settings = get_settings(request)
    return _get_or_create_initialized_service(
        request,
        "advanced_entity_extractor",
        "AdvancedEntityExtractor",
        lambda: AdvancedEntityExtractor(),
        lambda instance: instance.initialize(settings.module_config("advanced_entity_extractor")),
    )


def get_relation_extractor(request: Request) -> RelationExtractor:
    extractor = getattr(request.app.state, "relation_extractor", None)
    if extractor is None:
        extractor = RelationExtractor()
        request.app.state.relation_extractor = extractor
    return extractor