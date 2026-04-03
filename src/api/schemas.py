"""OpenAPI DTOs for the Architecture 3.0 REST API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ResearchRunRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="研究主题")
    orchestrator_config: Dict[str, Any] = Field(default_factory=dict, description="编排器配置")
    phase_contexts: Dict[str, Any] = Field(default_factory=dict, description="阶段上下文")
    cycle_name: Optional[str] = Field(default=None, description="研究周期名称")
    description: Optional[str] = Field(default=None, description="研究描述")
    scope: Optional[str] = Field(default=None, description="研究范围")


class ResearchPhaseOutcome(BaseModel):
    phase: str = Field(..., description="阶段标识")
    status: str = Field(..., description="阶段状态")
    duration_sec: float = Field(default=0.0, description="阶段耗时（秒）")
    error: str = Field(default="", description="阶段错误信息")
    summary: Dict[str, Any] = Field(default_factory=dict, description="阶段摘要")


class ResearchResult(BaseModel):
    topic: str = Field(..., description="研究主题")
    cycle_id: str = Field(..., description="周期 ID")
    status: str = Field(..., description="执行状态")
    started_at: Optional[str] = Field(default=None, description="开始时间")
    completed_at: Optional[str] = Field(default=None, description="完成时间")
    total_duration_sec: float = Field(default=0.0, description="总耗时（秒）")
    phases: List[ResearchPhaseOutcome] = Field(default_factory=list, description="阶段执行结果")
    pipeline_metadata: Dict[str, Any] = Field(default_factory=dict, description="流程元数据")
    analysis_results: Dict[str, Any] = Field(default_factory=dict, description="分析域输出 DTO")
    research_artifact: Dict[str, Any] = Field(default_factory=dict, description="研究产物 DTO")
    output_files: Dict[str, Any] = Field(default_factory=dict, description="输出文件集合")


class ResearchJobAccepted(BaseModel):
    job_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务当前状态")
    stream_url: str = Field(..., description="兼容层 SSE 地址")
    status_url: str = Field(..., description="兼容层状态查询地址")
    websocket_url: str = Field(..., description="兼容层 WebSocket 地址")
    versioned_stream_url: str = Field(..., description="版本化 SSE 地址")
    versioned_status_url: str = Field(..., description="版本化状态查询地址")
    versioned_websocket_url: str = Field(..., description="版本化 WebSocket 地址")


class ResearchJobSnapshot(BaseModel):
    job_id: str = Field(..., description="任务 ID")
    topic: str = Field(..., description="研究主题")
    status: str = Field(..., description="任务状态")
    progress: float = Field(default=0.0, description="进度百分比")
    current_phase: str = Field(default="", description="当前阶段")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    started_at: Optional[str] = Field(default=None, description="开始时间")
    completed_at: Optional[str] = Field(default=None, description="完成时间")
    error: str = Field(default="", description="错误信息")
    result: Optional[Dict[str, Any]] = Field(default=None, description="最终研究结果")
    event_count: int = Field(default=0, description="已记录事件数")


class ResearchJobListItem(BaseModel):
    job_id: str = Field(..., description="任务 ID")
    topic: str = Field(..., description="研究主题")
    status: str = Field(..., description="任务状态")
    progress: float = Field(default=0.0, description="进度百分比")
    current_phase: str = Field(default="", description="当前阶段")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    started_at: Optional[str] = Field(default=None, description="开始时间")
    completed_at: Optional[str] = Field(default=None, description="完成时间")
    error: str = Field(default="", description="错误信息")


class ResearchJobListResponse(BaseModel):
    jobs: List[ResearchJobListItem] = Field(default_factory=list, description="任务列表")
    count: int = Field(default=0, description="返回任务数")
    limit: int = Field(default=0, description="请求限制")


class ResearchJobDeletionResponse(BaseModel):
    job_id: str = Field(..., description="任务 ID")
    deleted: bool = Field(..., description="是否删除成功")
    job: ResearchJobListItem = Field(..., description="被删除任务摘要")


class ResearchEventEnvelope(BaseModel):
    sequence: int = Field(..., description="事件序号")
    event: str = Field(..., description="事件类型")
    job_id: str = Field(..., description="任务 ID")
    timestamp: str = Field(..., description="事件时间")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")


class StandardDocumentFormatInfo(BaseModel):
    source_type: str = Field(..., description="来源类型")
    language: str = Field(..., description="语言代码")
    encoding: Optional[str] = Field(default=None, description="编码信息")


class StandardDocument(BaseModel):
    id: str = Field(..., description="统一文档 ID")
    text: str = Field(..., description="标准化正文")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文档元数据")
    source: str = Field(..., description="来源引用")
    format_info: StandardDocumentFormatInfo = Field(..., description="格式信息")


class NormalizationResultDto(BaseModel):
    success: bool = Field(..., description="是否成功")
    normalized_text: str = Field(default="", description="归一化文本")
    term_mappings: Dict[str, str] = Field(default_factory=dict, description="术语映射")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="归一化后的元数据")
    errors: List[str] = Field(default_factory=list, description="错误列表")
    normalization_steps: List[str] = Field(default_factory=list, description="执行步骤")


class NormalizeDocumentRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待标准化原始文本")
    document_id: Optional[str] = Field(default=None, description="外部文档标识")
    title: Optional[str] = Field(default=None, description="文档标题")
    source: str = Field(default="api", description="来源标识")
    source_type: str = Field(default="text", description="来源类型")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class NormalizeDocumentResponse(BaseModel):
    standard_document: StandardDocument = Field(..., description="统一文档 DTO")
    document: Dict[str, Any] = Field(default_factory=dict, description="完整文档结构")
    normalization: NormalizationResultDto = Field(..., description="归一化结果")


class EntityRecord(BaseModel):
    name: str = Field(..., description="实体名称")
    type: str = Field(..., description="实体类型")
    confidence: float = Field(default=0.0, description="置信度")
    position: int = Field(default=0, description="起始位置")
    end_position: int = Field(default=0, description="结束位置")
    length: int = Field(default=0, description="实体长度")
    amount: Optional[str] = Field(default=None, description="剂量值")
    unit: Optional[str] = Field(default=None, description="剂量单位")


class RelationAttributes(BaseModel):
    relationship_type: str = Field(..., description="关系类型")
    relationship_name: str = Field(..., description="关系名称")
    description: str = Field(..., description="关系说明")
    confidence: float = Field(default=0.0, description="关系置信度")


class RelationRecord(BaseModel):
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    attributes: RelationAttributes = Field(..., description="关系属性")


class AnalysisResultDto(BaseModel):
    entities: List[EntityRecord] = Field(default_factory=list, description="实体列表")
    statistics: Dict[str, Any] = Field(default_factory=dict, description="统计信息")
    confidence_scores: Dict[str, Any] = Field(default_factory=dict, description="置信度统计")
    relations: List[RelationRecord] = Field(default_factory=list, description="关系预览")
    relation_statistics: Dict[str, Any] = Field(default_factory=dict, description="关系统计")


class AnalysisSummaryDto(BaseModel):
    input_length: int = Field(default=0, description="输入文本长度")
    processed_length: int = Field(default=0, description="处理后文本长度")
    token_count: int = Field(default=0, description="预览 token 数")
    preview_tokens: List[str] = Field(default_factory=list, description="分词预览")
    entity_count: int = Field(default=0, description="实体数量")
    relation_count: int = Field(default=0, description="关系数量")


class AnalyzeDocumentRequest(BaseModel):
    text: str = Field(..., min_length=1, description="待分析文本")
    include_relations: bool = Field(default=True, description="是否返回关系预览")
    max_entities: int = Field(default=20, ge=1, le=100, description="最大实体数")
    max_tokens_preview: int = Field(default=20, ge=1, le=100, description="最大预览 token 数")


class AnalyzeDocumentResponse(BaseModel):
    processed_text: str = Field(..., description="预处理后的文本")
    processing_steps: List[str] = Field(default_factory=list, description="处理步骤")
    analysis_result: AnalysisResultDto = Field(..., description="分析结果 DTO")
    analysis_summary: AnalysisSummaryDto = Field(..., description="分析摘要")


class SystemHealthResponse(BaseModel):
    status: str = Field(..., description="接口健康状态")
    system_status: str = Field(..., description="系统运行状态")
    version: str = Field(..., description="系统版本")
    environment: str = Field(..., description="当前配置环境")
    config_sources: List[str] = Field(default_factory=list, description="已加载配置源")
    overall_health: float = Field(default=0.0, description="综合健康评分")
    summary: Dict[str, Any] = Field(default_factory=dict, description="健康检查摘要")
    checks: List[Dict[str, Any]] = Field(default_factory=list, description="健康检查明细")


class HealthProbeResponse(BaseModel):
    status: str = Field(..., description="探针状态")
    probe_type: str = Field(..., description="探针类型")
    environment: str = Field(..., description="当前配置环境")
    checked_at: Optional[str] = Field(default=None, description="探针检查时间")
    overall_health: float = Field(default=0.0, description="探针综合健康评分")
    summary: Dict[str, Any] = Field(default_factory=dict, description="探针摘要")
    checks: List[Dict[str, Any]] = Field(default_factory=list, description="探针检查明细")


class SystemStatusResponse(BaseModel):
    system_info: Dict[str, Any] = Field(default_factory=dict, description="系统基本信息")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="性能指标")
    module_status: Dict[str, Any] = Field(default_factory=dict, description="模块健康状态")
    standards_compliance: Dict[str, Any] = Field(default_factory=dict, description="标准合规信息")
    health_report: Dict[str, Any] = Field(default_factory=dict, description="监控健康报告")
    analysis_summary: Dict[str, Any] = Field(default_factory=dict, description="系统分析摘要")
    failed_operations: List[Dict[str, Any]] = Field(default_factory=list, description="失败操作列表")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="运行元数据")
    report_metadata: Dict[str, Any] = Field(default_factory=dict, description="报告元数据")


class ArchitectureSummaryResponse(BaseModel):
    system_info: Dict[str, Any] = Field(default_factory=dict, description="系统配置摘要")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="性能摘要")
    analysis_summary: Dict[str, Any] = Field(default_factory=dict, description="分析摘要")
    failed_operations: List[Dict[str, Any]] = Field(default_factory=list, description="失败操作")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="运行元数据")
    report_metadata: Dict[str, Any] = Field(default_factory=dict, description="报告元数据")


class ModuleSummary(BaseModel):
    module_id: str = Field(..., description="模块 ID")
    module_name: str = Field(..., description="模块名称")
    module_type: str = Field(..., description="模块类型")
    version: str = Field(..., description="模块版本")
    status: str = Field(..., description="模块状态")
    dependencies: List[str] = Field(default_factory=list, description="依赖模块")
    created_at: Optional[str] = Field(default=None, description="创建时间")
    updated_at: Optional[str] = Field(default=None, description="更新时间")


class ModuleDetail(ModuleSummary):
    configuration: Dict[str, Any] = Field(default_factory=dict, description="配置信息")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="模块性能指标")
    academic_compliance: Dict[str, Any] = Field(default_factory=dict, description="学术合规信息")
    security_info: Dict[str, Any] = Field(default_factory=dict, description="安全信息")


class ModuleListResponse(BaseModel):
    modules: List[ModuleSummary] = Field(default_factory=list, description="模块列表")
    count: int = Field(default=0, description="模块数量")


class ModuleDependencyResponse(BaseModel):
    module_id: str = Field(..., description="模块 ID")
    dependencies: List[str] = Field(default_factory=list, description="依赖列表")
    count: int = Field(default=0, description="依赖数量")


class ModuleDependentResponse(BaseModel):
    module_id: str = Field(..., description="模块 ID")
    dependents: List[str] = Field(default_factory=list, description="被依赖者列表")
    count: int = Field(default=0, description="数量")


class PersistenceSummaryResponse(BaseModel):
    storage_dir: str = Field(..., description="持久化目录")
    job_file_count: int = Field(default=0, description="任务文件数")
    temp_file_count: int = Field(default=0, description="临时文件数")
    total_size_bytes: int = Field(default=0, description="总占用字节数")
    stored_job_count: int = Field(default=0, description="可解析任务数")
    latest_updated_at: Optional[str] = Field(default=None, description="最近更新时间")


class PersistedJobRecord(BaseModel):
    job_id: str = Field(..., description="任务 ID")
    job: Dict[str, Any] = Field(default_factory=dict, description="任务快照")
    event_count: int = Field(default=0, description="事件数")
    has_result: bool = Field(default=False, description="是否包含最终结果")


class PersistedJobListResponse(BaseModel):
    jobs: List[PersistedJobRecord] = Field(default_factory=list, description="持久化任务记录")
    count: int = Field(default=0, description="返回记录数")
    limit: int = Field(default=0, description="请求限制")


class PersistedJobPayloadResponse(BaseModel):
    version: int = Field(default=1, description="持久化结构版本")
    job: Dict[str, Any] = Field(default_factory=dict, description="任务快照")
    events: List[Dict[str, Any]] = Field(default_factory=list, description="事件流")


class MonitoringMetricsResponse(BaseModel):
    collected_at: Optional[str] = Field(default=None, description="指标采集时间")
    system: Dict[str, Any] = Field(default_factory=dict, description="系统运行指标")
    host: Dict[str, Any] = Field(default_factory=dict, description="主机资源指标")
    jobs: Dict[str, Any] = Field(default_factory=dict, description="任务运行指标")
    persistence: PersistenceSummaryResponse = Field(..., description="持久化层摘要")
    health: Dict[str, Any] = Field(default_factory=dict, description="健康检查结果")
    alerts: List[Dict[str, Any]] = Field(default_factory=list, description="阈值告警结果")


class SystemExportRequest(BaseModel):
    output_name: Optional[str] = Field(default=None, description="导出文件名，仅允许 .json")
    include_payload: bool = Field(default=False, description="是否在响应中直接附带导出内容")


class SystemExportResponse(BaseModel):
    exported: bool = Field(..., description="是否成功导出")
    output_path: str = Field(..., description="导出文件路径")
    file_size_bytes: int = Field(default=0, description="文件大小")
    payload: Optional[Dict[str, Any]] = Field(default=None, description="导出内容")