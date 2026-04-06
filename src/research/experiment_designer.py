"""中医科研实验方案结构化设计辅助模块。"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from statistics import NormalDist
from typing import Any, Dict, List, Mapping, Optional

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


class StudyType(str, Enum):
    """支持的研究设计类型。"""

    RCT = "rct"
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    NETWORK_PHARMACOLOGY = "network_pharmacology"


_CONTINUOUS_OUTCOME_KEYWORDS = (
    "评分",
    "量表",
    "水平",
    "变化",
    "改善",
    "时间",
    "天数",
    "持续时间",
    "血压",
    "血糖",
    "hba1c",
    "crp",
    "il-6",
)
_BINARY_OUTCOME_KEYWORDS = (
    "率",
    "发生",
    "复发",
    "缓解",
    "反应",
    "有效",
    "事件",
    "死亡",
    "转阴",
    "应答",
    "不良",
    "达标",
)
_MECHANISTIC_OUTCOME_KEYWORDS = (
    "靶点",
    "通路",
    "网络药理",
    "分子对接",
    "ppi",
    "kegg",
    "go 富集",
)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 3:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _coerce_text(value: Any) -> str:
    return str(value or "").strip()


def _ensure_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        normalized: List[str] = []
        for item in value:
            text = _coerce_text(item)
            if text:
                normalized.append(text)
        return normalized
    return []


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


@dataclass
class PICO:
    """PICO 框架：Population / Intervention / Comparison / Outcome。"""

    population: str = ""
    intervention: str = ""
    comparison: str = ""
    outcome: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "population": self.population,
            "intervention": self.intervention,
            "comparison": self.comparison,
            "outcome": self.outcome,
        }


@dataclass
class EligibilityCriteria:
    """研究纳入 / 排除标准模板。"""

    inclusion: List[str] = field(default_factory=list)
    exclusion: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[str]]:
        return {"inclusion": list(self.inclusion), "exclusion": list(self.exclusion)}


@dataclass
class StudyArm:
    """试验组别定义。"""

    name: str = ""
    intervention: str = ""
    description: str = ""
    allocation_ratio: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "intervention": self.intervention,
            "description": self.description,
            "allocation_ratio": self.allocation_ratio,
        }


@dataclass
class VisitScheduleItem:
    """访视与评估时间点。"""

    timepoint: str = ""
    assessments: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timepoint": self.timepoint,
            "assessments": list(self.assessments),
        }


@dataclass
class SampleSizeEstimation:
    """样本量估算参数与结论。"""

    alpha: float = 0.05
    power: float = 0.80
    effect_size: float = 0.5
    estimated_n: int = 0
    method: str = ""
    outcome_type: str = ""
    dropout_rate: float = 0.0
    allocation_ratio: float = 1.0
    base_total_n: int = 0
    per_group_n: int = 0
    formula: str = ""
    rationale: str = ""
    assumptions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "power": self.power,
            "effect_size": self.effect_size,
            "estimated_n": self.estimated_n,
            "method": self.method,
            "outcome_type": self.outcome_type,
            "dropout_rate": self.dropout_rate,
            "allocation_ratio": self.allocation_ratio,
            "base_total_n": self.base_total_n,
            "per_group_n": self.per_group_n,
            "formula": self.formula,
            "rationale": self.rationale,
            "assumptions": dict(self.assumptions),
        }


@dataclass
class StudyProtocol:
    """结构化研究方案协议。"""

    title: str = ""
    objective: str = ""
    background_rationale: str = ""
    study_type: str = ""
    hypothesis: str = ""
    pico: PICO = field(default_factory=PICO)
    sample_size: SampleSizeEstimation = field(default_factory=SampleSizeEstimation)
    eligibility: EligibilityCriteria = field(default_factory=EligibilityCriteria)
    primary_outcome: str = ""
    secondary_outcomes: List[str] = field(default_factory=list)
    arms: List[StudyArm] = field(default_factory=list)
    procedures: List[str] = field(default_factory=list)
    visit_schedule: List[VisitScheduleItem] = field(default_factory=list)
    blinding: str = ""
    randomization: str = ""
    data_collection_plan: List[str] = field(default_factory=list)
    statistical_plan: str = ""
    analysis_populations: List[str] = field(default_factory=list)
    duration: str = ""
    safety_monitoring: str = ""
    ethical_considerations: str = ""
    risk_management: List[str] = field(default_factory=list)
    design_notes: List[str] = field(default_factory=list)
    protocol_source: str = "template"

    REQUIRED_FIELDS = (
        "study_type",
        "hypothesis",
        "pico",
        "sample_size",
        "eligibility",
        "primary_outcome",
        "statistical_plan",
    )

    def filled_required_count(self) -> int:
        """返回已填写的必填字段数量。"""
        count = 0
        for field_name in self.REQUIRED_FIELDS:
            value = getattr(self, field_name)
            if value is None:
                continue
            if isinstance(value, str) and value == "":
                continue
            if isinstance(value, PICO) and not value.population:
                continue
            if isinstance(value, SampleSizeEstimation) and value.estimated_n == 0:
                continue
            if isinstance(value, EligibilityCriteria) and not value.inclusion:
                continue
            count += 1
        return count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "objective": self.objective,
            "background_rationale": self.background_rationale,
            "study_type": self.study_type,
            "hypothesis": self.hypothesis,
            "pico": self.pico.to_dict(),
            "sample_size": self.sample_size.to_dict(),
            "eligibility": self.eligibility.to_dict(),
            "primary_outcome": self.primary_outcome,
            "secondary_outcomes": list(self.secondary_outcomes),
            "arms": [item.to_dict() for item in self.arms],
            "procedures": list(self.procedures),
            "visit_schedule": [item.to_dict() for item in self.visit_schedule],
            "blinding": self.blinding,
            "randomization": self.randomization,
            "data_collection_plan": list(self.data_collection_plan),
            "statistical_plan": self.statistical_plan,
            "analysis_populations": list(self.analysis_populations),
            "duration": self.duration,
            "safety_monitoring": self.safety_monitoring,
            "ethical_considerations": self.ethical_considerations,
            "risk_management": list(self.risk_management),
            "design_notes": list(self.design_notes),
            "protocol_source": self.protocol_source,
        }


_TEMPLATES: Dict[StudyType, Dict[str, Any]] = {
    StudyType.RCT: {
        "blinding": "双盲（受试者与结局评估者）",
        "randomization": "中心分层区组随机，按证候分型进行分层",
        "statistical_plan": "主要分析集采用 ITT，敏感性分析采用 PP；连续变量使用线性混合模型或 ANCOVA，分类变量使用卡方检验或广义线性模型。",
        "duration": "筛选期 1 周，干预期 8-12 周，随访期 4 周。",
        "ethical_considerations": "需通过伦理审批并完成书面知情同意；设置 AE/SAE 报告路径。",
        "default_inclusion": [
            "符合西医诊断标准并满足中医辨证标准",
            "年龄 18-65 岁，愿意完成全部访视",
            "近 2 周病情稳定，可接受随机分组",
        ],
        "default_exclusion": [
            "合并严重心脑肝肾疾病或精神障碍",
            "妊娠、哺乳期或近 3 个月备孕者",
            "近 1 个月参加其他干预性临床试验",
        ],
        "sample_method": "两组均数比较法",
        "default_effect_size": 0.5,
        "background_rationale": "针对中医干预的真实疗效与安全性，需要采用规范随机对照设计完成验证。",
        "default_arms": [
            {
                "name": "试验组",
                "intervention": "目标中药/方剂干预 + 常规治疗",
                "description": "按标准化给药方案实施干预，并记录证候分型。",
                "allocation_ratio": 1.0,
            },
            {
                "name": "对照组",
                "intervention": "安慰剂或指南推荐常规治疗",
                "description": "保持除目标干预外的其他治疗一致。",
                "allocation_ratio": 1.0,
            },
        ],
        "default_procedures": [
            "完成筛选、基线评估与随机分组",
            "按预设疗程执行干预并监测依从性",
            "在末次访视与随访期采集主要/次要结局",
        ],
        "default_visit_schedule": [
            {"timepoint": "筛选期", "assessments": ["诊断确认", "纳排评估", "知情同意"]},
            {"timepoint": "基线", "assessments": ["证候评分", "实验室指标", "随机化"]},
            {"timepoint": "治疗中", "assessments": ["依从性", "不良事件", "疗效趋势"]},
            {"timepoint": "末次访视/随访", "assessments": ["主要结局", "安全性", "复发情况"]},
        ],
        "default_data_collection_plan": ["eCRF 录入", "证候量表评分", "实验室/影像检查", "安全性随访"],
        "default_analysis_populations": ["ITT", "PP", "Safety Set"],
        "default_safety_monitoring": "建立独立安全性监测流程，按访视节点核查肝肾功能、AE/SAE 与停药标准。",
        "default_risk_management": ["设置失访补访机制", "统一干预与评价 SOP", "按证候分层控制基线不平衡"],
        "design_notes": ["建议将证候分型作为随机分层因子", "明确合并用药与救援治疗规则"],
    },
    StudyType.SYSTEMATIC_REVIEW: {
        "blinding": "不适用",
        "randomization": "不适用",
        "statistical_plan": "采用 PRISMA 2020 流程进行文献筛选与定性综合，必要时按证候、剂量、疗程进行分层叙述。",
        "duration": "检索时限自建库至检索日，更新检索至少 1 次。",
        "ethical_considerations": "二次研究通常无需伦理审批，但需保证研究透明与方案预注册。",
        "default_inclusion": ["研究对象与研究问题高度匹配", "报告清晰干预与结局指标", "全文可获得"],
        "default_exclusion": ["重复发表", "无法提取关键数据", "会议摘要且无完整方法学描述"],
        "sample_method": "证据综合设计，以文献数量与总样本覆盖度评估充分性",
        "default_effect_size": 0.0,
        "background_rationale": "需要对既有证据进行系统梳理，以明确当前中医干预证据强弱与研究空白。",
        "default_procedures": ["制定检索式并完成双人独立筛选", "进行数据提取与偏倚风险评估", "形成证据表与叙述性综合结论"],
        "default_data_collection_plan": ["数据库检索记录", "文献筛选日志", "偏倚风险评估表", "证据汇总表"],
        "default_analysis_populations": ["纳入文献全集"],
        "default_safety_monitoring": "不适用，重点关注偏倚风险、证据异质性与报告完整性。",
        "default_risk_management": ["双人交叉核对筛选结果", "记录排除理由", "保留检索与提取审计轨迹"],
        "design_notes": ["建议预注册 PROSPERO 或同类平台", "保留中医术语与现代诊断的桥接规则"],
    },
    StudyType.META_ANALYSIS: {
        "blinding": "不适用",
        "randomization": "不适用",
        "statistical_plan": "优先使用随机效应模型，显式评估异质性（I²、τ²、Q 检验）并进行敏感性分析；必要时开展亚组分析与发表偏倚检验。",
        "duration": "检索时限自建库至检索日，数据提取后完成统计合并。",
        "ethical_considerations": "二次研究通常无需伦理审批，但需保证统计决策可追溯。",
        "default_inclusion": ["研究类型以 RCT 或高质量比较研究为主", "可提取效应量或原始数据", "结局定义可对齐"],
        "default_exclusion": ["结局定义异质且不可统一", "重复发表", "高偏倚风险且无法敏感性处理"],
        "sample_method": "证据综合设计，以效应量精度和异质性控制评估纳入充分性",
        "default_effect_size": 0.0,
        "background_rationale": "需要将分散研究的量化结果合并，以评估中医干预的总体效应及不确定性范围。",
        "default_procedures": ["抽取效应量并统一方向", "完成异质性、敏感性和偏倚分析", "输出森林图与证据结论"],
        "default_data_collection_plan": ["效应量表", "研究质量评分", "亚组变量字典", "敏感性分析日志"],
        "default_analysis_populations": ["可合并研究集", "敏感性分析子集"],
        "default_safety_monitoring": "不适用，重点关注异质性、偏倚与效应量稳定性。",
        "default_risk_management": ["预先定义异质性阈值", "区分临床异质与方法学异质", "执行 leave-one-out 分析"],
        "design_notes": ["需明确主要效应量类型", "中医证候差异宜进入亚组或 Meta 回归"],
    },
    StudyType.COHORT: {
        "blinding": "结局评估者盲法",
        "randomization": "非随机暴露分组，按基线特征匹配或加权",
        "statistical_plan": "采用 Cox 回归、倾向评分匹配/加权和分层分析，报告 HR/RR 与 95% CI。",
        "duration": "基线建档后随访 6-24 个月，按结局事件设定访视窗口。",
        "ethical_considerations": "需伦理审批，保证真实世界暴露记录与隐私保护。",
        "default_inclusion": ["定义清晰的暴露组与对照组", "基线特征可完整收集", "可实现持续随访"],
        "default_exclusion": ["关键暴露信息缺失", "严重合并症导致无法随访", "结局定义不明确"],
        "sample_method": "两组率比较法/事件发生率比较法",
        "default_effect_size": 0.4,
        "background_rationale": "适用于评估中医暴露因素或治疗路径与结局风险之间的长期关联。",
        "default_arms": [
            {
                "name": "暴露组",
                "intervention": "接受目标中医治疗/暴露因素",
                "description": "记录暴露剂量、疗程与证候分型。",
                "allocation_ratio": 1.0,
            },
            {
                "name": "非暴露组",
                "intervention": "未接受目标暴露或接受标准治疗",
                "description": "保持基线资料与结局定义一致。",
                "allocation_ratio": 1.0,
            },
        ],
        "default_procedures": ["基线登记与暴露定义", "定期随访并更新结局事件", "期末完成风险模型分析"],
        "default_visit_schedule": [
            {"timepoint": "基线", "assessments": ["暴露确认", "共变量收集", "结局定义"]},
            {"timepoint": "随访期", "assessments": ["结局事件", "依从性", "混杂因素更新"]},
            {"timepoint": "结题", "assessments": ["结局核验", "统计分析", "敏感性分析"]},
        ],
        "default_data_collection_plan": ["随访表", "结局事件判定表", "暴露剂量记录", "混杂变量更新"],
        "default_analysis_populations": ["全队列", "匹配后队列", "敏感性分析队列"],
        "default_safety_monitoring": "重点监测失访、暴露偏倚和结局判定一致性。",
        "default_risk_management": ["设置失访追踪机制", "定义结局事件判定委员会", "控制时间相关混杂"],
        "design_notes": ["建议保留证候变化轨迹", "可将方剂组合暴露作为时间依赖变量"],
    },
    StudyType.CASE_CONTROL: {
        "blinding": "不适用",
        "randomization": "不适用（回顾性匹配设计）",
        "statistical_plan": "采用条件/非条件 Logistic 回归，报告 OR、95% CI 与分层敏感性分析。",
        "duration": "按病例入组时间窗回顾收集暴露信息。",
        "ethical_considerations": "需伦理审批，重视病历数据与隐私保护。",
        "default_inclusion": ["病例诊断明确", "对照来源可比", "暴露信息可追溯"],
        "default_exclusion": ["病例诊断不稳定", "关键暴露缺失", "存在严重选择偏倚"],
        "sample_method": "病例对照暴露率比较法",
        "default_effect_size": 0.4,
        "background_rationale": "适用于探索中医暴露因素、证候因素与疾病发生之间的关联强度。",
        "default_arms": [
            {
                "name": "病例组",
                "intervention": "确诊目标疾病/结局",
                "description": "按统一标准纳入病例。",
                "allocation_ratio": 1.0,
            },
            {
                "name": "对照组",
                "intervention": "同来源未患病个体",
                "description": "按年龄、性别或就诊时间进行匹配。",
                "allocation_ratio": 1.0,
            },
        ],
        "default_procedures": ["确定病例与对照来源", "回顾性提取暴露信息", "完成匹配与 OR 分析"],
        "default_data_collection_plan": ["病历回顾表", "暴露问卷/电子病历", "匹配记录表"],
        "default_analysis_populations": ["全样本", "匹配样本"],
        "default_safety_monitoring": "重点关注信息偏倚、回忆偏倚与匹配偏倚。",
        "default_risk_management": ["统一病例定义", "预先定义匹配规则", "控制暴露测量偏差"],
        "design_notes": ["病例:对照可按 1:1 至 1:4 配比", "证候因素可作为交互项进入模型"],
    },
    StudyType.NETWORK_PHARMACOLOGY: {
        "blinding": "不适用",
        "randomization": "不适用（计算与机制研究）",
        "statistical_plan": "完成成分筛选、靶点映射、PPI 网络拓扑分析、GO/KEGG 富集和分子对接验证。",
        "duration": "计算分析 2-6 周，必要时追加湿实验验证。",
        "ethical_considerations": "计算研究通常无需伦理审批，若追加动物/临床验证需单独审批。",
        "default_inclusion": ["化合物结构明确", "靶点数据可交叉验证", "疾病相关靶点来源可靠"],
        "default_exclusion": ["结构信息缺失", "靶点非人源且不可转换", "数据库证据冲突严重"],
        "sample_method": "机制探索设计，不以受试者样本量为核心约束",
        "default_effect_size": 0.0,
        "background_rationale": "适用于解释方剂-成分-靶点-通路的多层机制，为后续实证研究提供线索。",
        "default_procedures": ["筛选活性成分", "交并疾病靶点", "构建网络并完成富集分析", "筛选核心靶点并分子对接"],
        "default_data_collection_plan": ["成分数据库记录", "靶点库交集", "网络拓扑指标", "富集分析结果"],
        "default_analysis_populations": ["活性成分集", "候选靶点集", "核心网络子图"],
        "default_safety_monitoring": "重点监测数据库来源一致性与结果可重复性。",
        "default_risk_management": ["记录数据库版本", "保留筛选阈值", "为湿实验验证预留优先级队列"],
        "design_notes": ["可将证候分型映射为疾病亚群", "建议把核心通路回填至临床结局假设"],
    },
}


def _round_up_even(value: float) -> int:
    rounded = int(math.ceil(value))
    return rounded if rounded % 2 == 0 else rounded + 1


def _apply_dropout(base_total_n: int, dropout_rate: float) -> int:
    if base_total_n <= 0:
        return 0
    adjusted = base_total_n / max(0.01, 1 - dropout_rate)
    return _round_up_even(adjusted)


def _split_group_sizes(total_n: int, allocation_ratio: float) -> Dict[str, int]:
    if total_n <= 0:
        return {"group_1": 0, "group_2": 0}
    ratio = max(0.2, allocation_ratio)
    group_1 = int(round(total_n / (1 + ratio)))
    group_1 = max(1, group_1)
    group_2 = max(1, total_n - group_1)
    return {"group_1": group_1, "group_2": group_2}


def _estimate_sample_size(alpha: float = 0.05, power: float = 0.80, effect_size: float = 0.5) -> int:
    """基于 Cohen's d 简化估算两组比较所需总样本量。"""
    return _estimate_continuous_sample_size(alpha=alpha, power=power, effect_size=effect_size)


def _estimate_continuous_sample_size(
    alpha: float = 0.05,
    power: float = 0.80,
    effect_size: float = 0.5,
    allocation_ratio: float = 1.0,
) -> int:
    if effect_size <= 0:
        return 0
    norm = NormalDist()
    z_alpha = norm.inv_cdf(1 - alpha / 2)
    z_beta = norm.inv_cdf(power)
    equal_total_n = (z_alpha + z_beta) ** 2 * 2 / (effect_size ** 2)
    imbalance_factor = ((1 + allocation_ratio) ** 2) / (4 * max(0.2, allocation_ratio))
    return _round_up_even(equal_total_n * imbalance_factor)


def _estimate_binary_sample_size(
    alpha: float,
    power: float,
    control_rate: float,
    target_rate: float,
) -> int:
    delta = abs(target_rate - control_rate)
    if delta <= 0:
        return 0
    p1 = _clamp(control_rate, 0.01, 0.99)
    p2 = _clamp(target_rate, 0.01, 0.99)
    pooled = (p1 + p2) / 2
    norm = NormalDist()
    z_alpha = norm.inv_cdf(1 - alpha / 2)
    z_beta = norm.inv_cdf(power)
    numerator = (
        z_alpha * math.sqrt(2 * pooled * (1 - pooled))
        + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    )
    return _round_up_even(2 * (numerator ** 2) / (delta ** 2))


def _estimate_case_control_sample_size(
    alpha: float,
    power: float,
    control_exposure_rate: float,
    odds_ratio: float,
) -> int:
    if odds_ratio <= 0:
        return 0
    p0 = _clamp(control_exposure_rate, 0.01, 0.95)
    p1 = (odds_ratio * p0) / (1 - p0 + odds_ratio * p0)
    return _estimate_binary_sample_size(alpha=alpha, power=power, control_rate=p0, target_rate=p1)


def _infer_outcome_type(
    primary_outcome: str,
    study_type: StudyType,
    sample_payload: Mapping[str, Any],
) -> str:
    explicit = _coerce_text(sample_payload.get("outcome_type")).lower()
    if explicit:
        return explicit

    outcome_text = primary_outcome.lower()
    if study_type in (StudyType.SYSTEMATIC_REVIEW, StudyType.META_ANALYSIS):
        return "evidence_synthesis"
    if study_type == StudyType.NETWORK_PHARMACOLOGY or any(keyword in outcome_text for keyword in _MECHANISTIC_OUTCOME_KEYWORDS):
        return "mechanistic"
    if study_type == StudyType.CASE_CONTROL:
        return "case_control"
    if any(keyword in outcome_text for keyword in _BINARY_OUTCOME_KEYWORDS):
        return "binary"
    if any(keyword in outcome_text for keyword in _CONTINUOUS_OUTCOME_KEYWORDS):
        return "continuous"
    if study_type == StudyType.COHORT:
        return "binary"
    return "continuous"


class ExperimentDesigner(BaseModule):
    """中医科研实验方案结构化设计辅助。"""

    PROTOCOL_SYSTEM_PROMPT = (
        "你是一位中医临床研究与方法学专家，熟悉 RCT、队列研究、病例对照、系统综述、Meta 分析和网络药理学研究设计。"
        "请输出严格 JSON，不要输出 Markdown，不要解释。"
        "你的任务是补全研究协议字段，并给出样本量计算假设；最终样本量会由系统重新计算。"
    )

    def __init__(self, config: Dict[str, Any] | None = None, llm_engine: Any = None):
        super().__init__(module_name="ExperimentDesigner", config=config)
        self.llm_engine = llm_engine or self.config.get("llm_engine") or self.config.get("llm_service")

    def _do_initialize(self) -> bool:
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis = context.get("hypothesis", "")
        study_type = context.get("study_type", "rct")
        protocol = self.design_study(
            hypothesis,
            study_type,
            title=_coerce_text(context.get("title")),
            objective=_coerce_text(context.get("objective") or context.get("research_objective")),
            population=_coerce_text(context.get("population")),
            intervention=_coerce_text(context.get("intervention")),
            comparison=_coerce_text(context.get("comparison")),
            outcome=_coerce_text(context.get("outcome") or context.get("primary_outcome")),
            alpha=_coerce_float(context.get("alpha"), 0.05),
            power=_coerce_float(context.get("power"), 0.80),
            effect_size=context.get("effect_size"),
            llm_engine=context.get("llm_engine") or context.get("llm_service"),
            use_llm=context.get("use_llm_protocol_generation"),
            additional_context=context,
            sample_size_override=context.get("sample_size"),
        )
        payload = protocol.to_dict()
        return {"protocol": payload, "study_protocol": payload}

    def _do_cleanup(self) -> bool:
        return True

    def design_study(
        self,
        hypothesis: str,
        study_type: str | StudyType,
        *,
        title: str = "",
        objective: str = "",
        population: str = "",
        intervention: str = "",
        comparison: str = "",
        outcome: str = "",
        alpha: float = 0.05,
        power: float = 0.80,
        effect_size: float | None = None,
        llm_engine: Any = None,
        use_llm: Optional[bool] = None,
        additional_context: Optional[Dict[str, Any]] = None,
        sample_size_override: int | None = None,
    ) -> StudyProtocol:
        """根据假设与研究类型生成结构化 StudyProtocol。"""
        stype = self._resolve_study_type(study_type)
        template = _TEMPLATES.get(stype, {})
        protocol = self._build_template_protocol(
            stype,
            hypothesis=hypothesis,
            title=title,
            objective=objective,
            population=population,
            intervention=intervention,
            comparison=comparison,
            outcome=outcome,
            template=template,
        )

        sample_payload: Dict[str, Any] = {}
        resolved_llm = self._resolve_llm_engine(llm_engine)
        should_use_llm = bool(resolved_llm) if use_llm is None else bool(use_llm)
        if should_use_llm and resolved_llm is not None:
            llm_payload = self._generate_protocol_payload(
                hypothesis=hypothesis,
                study_type=stype,
                protocol=protocol,
                additional_context=additional_context or {},
                llm_engine=resolved_llm,
            )
            if llm_payload:
                protocol = self._merge_protocol_payload(protocol, llm_payload)
                protocol.protocol_source = "llm_enhanced"
                candidate_sample = llm_payload.get("sample_size")
                if isinstance(candidate_sample, dict):
                    sample_payload = dict(candidate_sample)

        protocol.sample_size = self._build_sample_size_estimation(
            stype,
            template=template,
            primary_outcome=protocol.primary_outcome,
            alpha=alpha,
            power=power,
            effect_size=effect_size,
            sample_payload=sample_payload,
            sample_size_override=sample_size_override,
        )
        protocol = self._ensure_protocol_completeness(protocol, stype, hypothesis, template)

        logger.info(
            "design_study: type=%s, protocol_source=%s, filled_required=%d, sample_size=%d",
            stype.value,
            protocol.protocol_source,
            protocol.filled_required_count(),
            protocol.sample_size.estimated_n,
        )
        return protocol

    def list_study_types(self) -> List[str]:
        return [item.value for item in StudyType]

    def _build_template_protocol(
        self,
        study_type: StudyType,
        *,
        hypothesis: str,
        title: str,
        objective: str,
        population: str,
        intervention: str,
        comparison: str,
        outcome: str,
        template: Mapping[str, Any],
    ) -> StudyProtocol:
        base_title = title or f"{study_type.value} 研究方案：{hypothesis[:28]}"
        primary_outcome = outcome or "[待填写 - 主要结局指标]"
        protocol = StudyProtocol(
            title=base_title,
            objective=objective or hypothesis,
            background_rationale=_coerce_text(template.get("background_rationale")),
            study_type=study_type.value,
            hypothesis=hypothesis,
            pico=PICO(
                population=population or f"[待填写 - {study_type.value} 研究人群]",
                intervention=intervention or "[待填写 - 目标干预]",
                comparison=comparison or "[待填写 - 对照措施]",
                outcome=primary_outcome,
            ),
            eligibility=EligibilityCriteria(
                inclusion=list(template.get("default_inclusion", [])),
                exclusion=list(template.get("default_exclusion", [])),
            ),
            primary_outcome=primary_outcome,
            secondary_outcomes=["安全性", "依从性", "证候评分变化"],
            arms=self._build_study_arms(template.get("default_arms")),
            procedures=_ensure_text_list(template.get("default_procedures")),
            visit_schedule=self._build_visit_schedule(template.get("default_visit_schedule")),
            blinding=_coerce_text(template.get("blinding")),
            randomization=_coerce_text(template.get("randomization")),
            data_collection_plan=_ensure_text_list(template.get("default_data_collection_plan")),
            statistical_plan=_coerce_text(template.get("statistical_plan")),
            analysis_populations=_ensure_text_list(template.get("default_analysis_populations")),
            duration=_coerce_text(template.get("duration")),
            safety_monitoring=_coerce_text(template.get("default_safety_monitoring")),
            ethical_considerations=_coerce_text(template.get("ethical_considerations")),
            risk_management=_ensure_text_list(template.get("default_risk_management")),
            design_notes=_ensure_text_list(template.get("design_notes")),
            protocol_source="template",
        )
        return protocol

    def _build_study_arms(self, raw_arms: Any) -> List[StudyArm]:
        arms: List[StudyArm] = []
        if not isinstance(raw_arms, list):
            return arms
        for item in raw_arms:
            if not isinstance(item, Mapping):
                continue
            arm = StudyArm(
                name=_coerce_text(item.get("name")),
                intervention=_coerce_text(item.get("intervention")),
                description=_coerce_text(item.get("description")),
                allocation_ratio=max(0.1, _coerce_float(item.get("allocation_ratio"), 1.0)),
            )
            if arm.name:
                arms.append(arm)
        return arms

    def _build_visit_schedule(self, raw_schedule: Any) -> List[VisitScheduleItem]:
        schedule: List[VisitScheduleItem] = []
        if not isinstance(raw_schedule, list):
            return schedule
        for item in raw_schedule:
            if not isinstance(item, Mapping):
                continue
            timepoint = _coerce_text(item.get("timepoint"))
            if not timepoint:
                continue
            schedule.append(
                VisitScheduleItem(
                    timepoint=timepoint,
                    assessments=_ensure_text_list(item.get("assessments")),
                )
            )
        return schedule

    def _resolve_llm_engine(self, llm_engine: Any) -> Any:
        return llm_engine or self.llm_engine or self.config.get("llm_engine") or self.config.get("llm_service")

    def _generate_protocol_payload(
        self,
        *,
        hypothesis: str,
        study_type: StudyType,
        protocol: StudyProtocol,
        additional_context: Dict[str, Any],
        llm_engine: Any,
    ) -> Dict[str, Any]:
        if llm_engine is None or not hasattr(llm_engine, "generate"):
            return {}

        prompt = self._build_llm_prompt(hypothesis, study_type, protocol, additional_context)
        try:
            raw = llm_engine.generate(prompt, system_prompt=self.PROTOCOL_SYSTEM_PROMPT)
        except Exception as exc:
            logger.warning("ExperimentDesigner LLM 生成失败，回退模板: %s", exc)
            return {}

        payload = self._parse_protocol_payload(raw)
        if not isinstance(payload, dict):
            logger.warning("ExperimentDesigner LLM 返回无法解析的协议 JSON，回退模板")
            return {}
        return payload

    def _build_llm_prompt(
        self,
        hypothesis: str,
        study_type: StudyType,
        protocol: StudyProtocol,
        additional_context: Dict[str, Any],
    ) -> str:
        context_digest = {
            "research_objective": additional_context.get("research_objective") or additional_context.get("objective"),
            "research_scope": additional_context.get("research_scope"),
            "validation_plan": additional_context.get("validation_plan"),
            "data_sources": additional_context.get("data_sources"),
            "supporting_signals": additional_context.get("supporting_signals"),
            "contradiction_signals": additional_context.get("contradiction_signals"),
            "evidence_profile": additional_context.get("evidence_profile"),
            "gap_priority_summary": additional_context.get("gap_priority_summary"),
        }
        return (
            f"研究假设: {hypothesis}\n"
            f"研究类型: {study_type.value}\n"
            "请基于以下模板，生成一个更完整、可执行的中医研究协议。\n"
            "要求: 返回单个 JSON 对象，字段必须与模板一致，可新增内容但不得删除关键字段。\n"
            "sample_size 字段只给出计算假设，不要给出自由文本表格。\n"
            "若研究类型为系统综述/Meta/网络药理，sample_size 可给出设计说明并令 estimated_n 为 0。\n\n"
            f"模板: {json.dumps(protocol.to_dict(), ensure_ascii=False)}\n\n"
            f"上下文: {json.dumps(context_digest, ensure_ascii=False)}"
        )

    def _parse_protocol_payload(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        text = _strip_code_fence(_coerce_text(raw))
        if not text:
            return {}
        try:
            payload = json.loads(text)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            try:
                payload = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}

    def _merge_protocol_payload(self, protocol: StudyProtocol, payload: Mapping[str, Any]) -> StudyProtocol:
        protocol.title = _coerce_text(payload.get("title")) or protocol.title
        protocol.objective = _coerce_text(payload.get("objective")) or protocol.objective
        protocol.background_rationale = _coerce_text(payload.get("background_rationale")) or protocol.background_rationale
        protocol.primary_outcome = _coerce_text(payload.get("primary_outcome")) or protocol.primary_outcome
        protocol.secondary_outcomes = _ensure_text_list(payload.get("secondary_outcomes")) or protocol.secondary_outcomes
        protocol.blinding = _coerce_text(payload.get("blinding")) or protocol.blinding
        protocol.randomization = _coerce_text(payload.get("randomization")) or protocol.randomization
        protocol.statistical_plan = _coerce_text(payload.get("statistical_plan")) or protocol.statistical_plan
        protocol.duration = _coerce_text(payload.get("duration")) or protocol.duration
        protocol.safety_monitoring = _coerce_text(payload.get("safety_monitoring")) or protocol.safety_monitoring
        protocol.ethical_considerations = _coerce_text(payload.get("ethical_considerations")) or protocol.ethical_considerations

        pico_payload = payload.get("pico")
        if isinstance(pico_payload, Mapping):
            protocol.pico.population = _coerce_text(pico_payload.get("population")) or protocol.pico.population
            protocol.pico.intervention = _coerce_text(pico_payload.get("intervention")) or protocol.pico.intervention
            protocol.pico.comparison = _coerce_text(pico_payload.get("comparison")) or protocol.pico.comparison
            protocol.pico.outcome = _coerce_text(pico_payload.get("outcome")) or protocol.pico.outcome

        eligibility_payload = payload.get("eligibility")
        if isinstance(eligibility_payload, Mapping):
            protocol.eligibility.inclusion = _ensure_text_list(eligibility_payload.get("inclusion")) or protocol.eligibility.inclusion
            protocol.eligibility.exclusion = _ensure_text_list(eligibility_payload.get("exclusion")) or protocol.eligibility.exclusion

        merged_arms = self._build_study_arms(payload.get("arms"))
        if merged_arms:
            protocol.arms = merged_arms

        merged_schedule = self._build_visit_schedule(payload.get("visit_schedule"))
        if merged_schedule:
            protocol.visit_schedule = merged_schedule

        protocol.procedures = _ensure_text_list(payload.get("procedures")) or protocol.procedures
        protocol.data_collection_plan = _ensure_text_list(payload.get("data_collection_plan")) or protocol.data_collection_plan
        protocol.analysis_populations = _ensure_text_list(payload.get("analysis_populations")) or protocol.analysis_populations
        protocol.risk_management = _ensure_text_list(payload.get("risk_management")) or protocol.risk_management
        protocol.design_notes = _ensure_text_list(payload.get("design_notes")) or protocol.design_notes
        return protocol

    def _build_sample_size_estimation(
        self,
        study_type: StudyType,
        *,
        template: Mapping[str, Any],
        primary_outcome: str,
        alpha: float,
        power: float,
        effect_size: float | None,
        sample_payload: Mapping[str, Any],
        sample_size_override: int | None,
    ) -> SampleSizeEstimation:
        resolved_alpha = _clamp(_coerce_float(sample_payload.get("alpha"), alpha), 0.001, 0.2)
        resolved_power = _clamp(_coerce_float(sample_payload.get("power"), power), 0.5, 0.99)
        resolved_effect_size = _coerce_float(
            effect_size if effect_size is not None else sample_payload.get("effect_size"),
            _coerce_float(template.get("default_effect_size"), 0.5),
        )
        allocation_ratio = max(0.2, _coerce_float(sample_payload.get("allocation_ratio"), 1.0))
        default_dropout = 0.15 if study_type in (StudyType.RCT, StudyType.COHORT, StudyType.CASE_CONTROL) else 0.0
        dropout_rate = _clamp(_coerce_float(sample_payload.get("dropout_rate"), default_dropout), 0.0, 0.4)
        outcome_type = _infer_outcome_type(primary_outcome, study_type, sample_payload)

        if sample_size_override is not None:
            override_n = max(0, int(sample_size_override))
            group_sizes = _split_group_sizes(override_n, allocation_ratio)
            return SampleSizeEstimation(
                alpha=resolved_alpha,
                power=resolved_power,
                effect_size=resolved_effect_size,
                estimated_n=override_n,
                method="上游指定样本量",
                outcome_type=outcome_type,
                dropout_rate=dropout_rate,
                allocation_ratio=allocation_ratio,
                base_total_n=override_n,
                per_group_n=max(group_sizes.values()) if group_sizes else 0,
                formula="manual_override",
                rationale="使用上游上下文提供的样本量，不再重复计算。",
                assumptions={"group_sizes": group_sizes},
            )

        if outcome_type == "continuous":
            base_total_n = _estimate_continuous_sample_size(
                alpha=resolved_alpha,
                power=resolved_power,
                effect_size=max(0.05, resolved_effect_size),
                allocation_ratio=allocation_ratio,
            )
            estimated_n = _apply_dropout(base_total_n, dropout_rate)
            group_sizes = _split_group_sizes(estimated_n, allocation_ratio)
            return SampleSizeEstimation(
                alpha=resolved_alpha,
                power=resolved_power,
                effect_size=resolved_effect_size,
                estimated_n=estimated_n,
                method=_coerce_text(template.get("sample_method")) or "两组均数比较法",
                outcome_type=outcome_type,
                dropout_rate=dropout_rate,
                allocation_ratio=allocation_ratio,
                base_total_n=base_total_n,
                per_group_n=max(group_sizes.values()),
                formula="n_total = ((Zα/2 + Zβ)^2 × 2 / d^2) × 不等比分组修正，再按失访率上调",
                rationale=f"按连续型主要结局估算，假设效应量 d={resolved_effect_size:.2f}，并按 {int(dropout_rate * 100)}% 失访率上调。",
                assumptions={"group_sizes": group_sizes},
            )

        if outcome_type == "binary":
            control_rate = _clamp(_coerce_float(sample_payload.get("control_rate") or sample_payload.get("baseline_rate"), 0.50), 0.05, 0.95)
            absolute_improvement = _coerce_float(sample_payload.get("absolute_improvement"), 0.15)
            target_rate = _clamp(
                _coerce_float(sample_payload.get("target_rate"), control_rate + absolute_improvement),
                0.05,
                0.99,
            )
            if abs(target_rate - control_rate) < 0.01:
                target_rate = _clamp(control_rate + 0.10, 0.05, 0.99)
            base_total_n = _estimate_binary_sample_size(
                alpha=resolved_alpha,
                power=resolved_power,
                control_rate=control_rate,
                target_rate=target_rate,
            )
            estimated_n = _apply_dropout(base_total_n, dropout_rate)
            group_sizes = _split_group_sizes(estimated_n, allocation_ratio)
            return SampleSizeEstimation(
                alpha=resolved_alpha,
                power=resolved_power,
                effect_size=resolved_effect_size,
                estimated_n=estimated_n,
                method="两组率比较法",
                outcome_type=outcome_type,
                dropout_rate=dropout_rate,
                allocation_ratio=allocation_ratio,
                base_total_n=base_total_n,
                per_group_n=max(group_sizes.values()),
                formula="n_total = 2 × (Zα/2√(2p(1-p)) + Zβ√(p1(1-p1)+p2(1-p2)))^2 / (p2-p1)^2，再按失访率上调",
                rationale=f"按二分类结局估算，假设对照组事件率 {control_rate:.2f}、干预组事件率 {target_rate:.2f}。",
                assumptions={
                    "control_rate": control_rate,
                    "target_rate": target_rate,
                    "group_sizes": group_sizes,
                },
            )

        if outcome_type == "case_control":
            control_exposure_rate = _clamp(_coerce_float(sample_payload.get("control_exposure_rate"), 0.30), 0.05, 0.95)
            odds_ratio = max(1.1, _coerce_float(sample_payload.get("odds_ratio"), 2.0))
            base_total_n = _estimate_case_control_sample_size(
                alpha=resolved_alpha,
                power=resolved_power,
                control_exposure_rate=control_exposure_rate,
                odds_ratio=odds_ratio,
            )
            estimated_n = _apply_dropout(base_total_n, dropout_rate)
            group_sizes = _split_group_sizes(estimated_n, allocation_ratio)
            return SampleSizeEstimation(
                alpha=resolved_alpha,
                power=resolved_power,
                effect_size=resolved_effect_size,
                estimated_n=estimated_n,
                method=_coerce_text(template.get("sample_method")) or "病例对照暴露率比较法",
                outcome_type=outcome_type,
                dropout_rate=dropout_rate,
                allocation_ratio=allocation_ratio,
                base_total_n=base_total_n,
                per_group_n=max(group_sizes.values()),
                formula="先根据 OR 与对照暴露率换算病例暴露率，再按两组率比较公式计算",
                rationale=f"按病例对照设计估算，假设对照暴露率 {control_exposure_rate:.2f}、预期 OR={odds_ratio:.2f}。",
                assumptions={
                    "control_exposure_rate": control_exposure_rate,
                    "odds_ratio": odds_ratio,
                    "group_sizes": group_sizes,
                },
            )

        return SampleSizeEstimation(
            alpha=resolved_alpha,
            power=resolved_power,
            effect_size=resolved_effect_size,
            estimated_n=0,
            method=_coerce_text(template.get("sample_method")),
            outcome_type=outcome_type,
            dropout_rate=dropout_rate,
            allocation_ratio=allocation_ratio,
            base_total_n=0,
            per_group_n=0,
            formula="not_applicable",
            rationale="当前设计以证据综合或机制探索为主，不以受试者样本量作为核心约束。",
            assumptions={},
        )

    def _ensure_protocol_completeness(
        self,
        protocol: StudyProtocol,
        study_type: StudyType,
        hypothesis: str,
        template: Mapping[str, Any],
    ) -> StudyProtocol:
        protocol.title = protocol.title or f"{study_type.value} 研究方案"
        protocol.objective = protocol.objective or hypothesis
        protocol.background_rationale = protocol.background_rationale or _coerce_text(template.get("background_rationale"))
        protocol.pico.outcome = protocol.pico.outcome or protocol.primary_outcome
        if not protocol.arms:
            protocol.arms = self._build_study_arms(template.get("default_arms"))
        if not protocol.procedures:
            protocol.procedures = _ensure_text_list(template.get("default_procedures"))
        if not protocol.visit_schedule:
            protocol.visit_schedule = self._build_visit_schedule(template.get("default_visit_schedule"))
        if not protocol.data_collection_plan:
            protocol.data_collection_plan = _ensure_text_list(template.get("default_data_collection_plan"))
        if not protocol.analysis_populations:
            protocol.analysis_populations = _ensure_text_list(template.get("default_analysis_populations"))
        if not protocol.risk_management:
            protocol.risk_management = _ensure_text_list(template.get("default_risk_management"))
        if not protocol.secondary_outcomes:
            protocol.secondary_outcomes = ["安全性", "依从性"]
        return protocol

    @staticmethod
    def _resolve_study_type(raw: str | StudyType) -> StudyType:
        if isinstance(raw, StudyType):
            return raw
        normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
        for member in StudyType:
            if member.value == normalized or member.name.lower() == normalized:
                return member
        raise ValueError(f"不支持的研究类型: {raw!r}，可选: {[item.value for item in StudyType]}")


__all__ = [
    "EligibilityCriteria",
    "ExperimentDesigner",
    "PICO",
    "SampleSizeEstimation",
    "StudyArm",
    "StudyProtocol",
    "StudyType",
    "VisitScheduleItem",
    "_estimate_case_control_sample_size",
    "_estimate_binary_sample_size",
    "_estimate_continuous_sample_size",
    "_estimate_sample_size",
]