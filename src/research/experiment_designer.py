"""中医科研实验方案结构化设计辅助模块。"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from src.core.module_base import BaseModule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 研究类型枚举
# ---------------------------------------------------------------------------

class StudyType(str, Enum):
    """支持的研究设计类型。"""

    RCT = "rct"
    SYSTEMATIC_REVIEW = "systematic_review"
    META_ANALYSIS = "meta_analysis"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    NETWORK_PHARMACOLOGY = "network_pharmacology"


# ---------------------------------------------------------------------------
# PICO 框架
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 纳排标准
# ---------------------------------------------------------------------------

@dataclass
class EligibilityCriteria:
    """研究纳入 / 排除标准模板。"""

    inclusion: List[str] = field(default_factory=list)
    exclusion: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, List[str]]:
        return {"inclusion": list(self.inclusion), "exclusion": list(self.exclusion)}


# ---------------------------------------------------------------------------
# 样本量估算
# ---------------------------------------------------------------------------

@dataclass
class SampleSizeEstimation:
    """样本量估算参数与结论。"""

    alpha: float = 0.05
    power: float = 0.80
    effect_size: float = 0.5
    estimated_n: int = 0
    method: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "power": self.power,
            "effect_size": self.effect_size,
            "estimated_n": self.estimated_n,
            "method": self.method,
        }


# ---------------------------------------------------------------------------
# 研究协议
# ---------------------------------------------------------------------------

@dataclass
class StudyProtocol:
    """结构化研究方案协议。"""

    study_type: str = ""
    hypothesis: str = ""
    pico: PICO = field(default_factory=PICO)
    sample_size: SampleSizeEstimation = field(default_factory=SampleSizeEstimation)
    eligibility: EligibilityCriteria = field(default_factory=EligibilityCriteria)
    primary_outcome: str = ""
    secondary_outcomes: List[str] = field(default_factory=list)
    blinding: str = ""
    randomization: str = ""
    statistical_plan: str = ""
    duration: str = ""
    ethical_considerations: str = ""
    design_notes: List[str] = field(default_factory=list)

    # 必填字段集——验收标准要求 ≥ 5
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
        for f in self.REQUIRED_FIELDS:
            val = getattr(self, f)
            if val is None:
                continue
            if isinstance(val, str) and val == "":
                continue
            if isinstance(val, PICO) and not val.population:
                continue
            if isinstance(val, SampleSizeEstimation) and val.estimated_n == 0:
                continue
            if isinstance(val, EligibilityCriteria) and not val.inclusion:
                continue
            count += 1
        return count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "study_type": self.study_type,
            "hypothesis": self.hypothesis,
            "pico": self.pico.to_dict(),
            "sample_size": self.sample_size.to_dict(),
            "eligibility": self.eligibility.to_dict(),
            "primary_outcome": self.primary_outcome,
            "secondary_outcomes": list(self.secondary_outcomes),
            "blinding": self.blinding,
            "randomization": self.randomization,
            "statistical_plan": self.statistical_plan,
            "duration": self.duration,
            "ethical_considerations": self.ethical_considerations,
            "design_notes": list(self.design_notes),
        }


# ---------------------------------------------------------------------------
# 各研究类型的模板
# ---------------------------------------------------------------------------

_TEMPLATES: Dict[str, Dict[str, Any]] = {
    StudyType.RCT: {
        "blinding": "双盲（受试者与评估者）",
        "randomization": "中心随机化，区组大小 4-6",
        "statistical_plan": "ITT 分析为主，PP 分析为辅；连续变量使用 t 检验或 ANCOVA，分类变量使用卡方检验",
        "duration": "干预期 8-12 周 + 随访 4 周",
        "ethical_considerations": "需获得伦理委员会批准，所有受试者签署知情同意书",
        "default_inclusion": [
            "符合西医诊断标准",
            "符合中医辨证标准",
            "年龄 18-65 岁",
            "签署知情同意书",
        ],
        "default_exclusion": [
            "合并严重心脑血管、肝肾等器质性疾病",
            "妊娠或哺乳期女性",
            "过敏体质或已知对试验药物过敏",
            "近 1 个月内参加过其他临床试验",
        ],
        "sample_method": "两组均数比较法",
        "default_effect_size": 0.5,
        "design_notes": [
            "采用随机、双盲、安慰剂/阳性药对照设计",
            "设置洗脱期以消除残留效应",
        ],
    },
    StudyType.SYSTEMATIC_REVIEW: {
        "blinding": "不适用",
        "randomization": "不适用",
        "statistical_plan": "定性综合 + 必要时亚组分析；使用 PRISMA 流程报告",
        "duration": "检索时限从建库至检索日",
        "ethical_considerations": "无需伦理审批（二次研究）",
        "default_inclusion": [
            "研究类型为 RCT 或高质量队列研究",
            "干预措施包含目标中药/方剂",
            "设有明确对照组",
            "报告了主要结局指标",
        ],
        "default_exclusion": [
            "重复发表或数据不完整",
            "动物实验或体外研究",
            "会议摘要无全文",
        ],
        "sample_method": "基于检索策略的纳入文献数",
        "default_effect_size": 0.0,
        "design_notes": [
            "制定全面的检索策略，覆盖中英文主要数据库",
            "两名研究者独立筛选与提取数据",
            "使用 Cochrane 偏倚风险评估工具",
        ],
    },
    StudyType.META_ANALYSIS: {
        "blinding": "不适用",
        "randomization": "不适用",
        "statistical_plan": "固定/随机效应模型；异质性检验（I² / Q 检验）；漏斗图 + Egger 检验评估发表偏倚",
        "duration": "检索时限从建库至检索日",
        "ethical_considerations": "无需伦理审批（二次研究）",
        "default_inclusion": [
            "研究类型为 RCT",
            "干预组使用目标中药/方剂",
            "报告了可合并的效应量数据",
        ],
        "default_exclusion": [
            "无法提取有效数据",
            "研究质量极低（Jadad ≤ 1 分）",
            "重复发表",
        ],
        "sample_method": "纳入研究数 × 各研究样本量",
        "default_effect_size": 0.0,
        "design_notes": [
            "遵循 PRISMA 声明",
            "进行敏感性分析以验证结果稳健性",
            "按亚组（剂量、疗程、证型）进行分层分析",
        ],
    },
    StudyType.COHORT: {
        "blinding": "评估者盲法",
        "randomization": "非随机（前瞻性观察设计）",
        "statistical_plan": "Cox 比例风险模型；倾向性评分匹配控制混杂",
        "duration": "随访 ≥ 12 个月",
        "ethical_considerations": "需获得伦理委员会批准",
        "default_inclusion": [
            "暴露组：接受目标中医治疗方案",
            "非暴露组：接受常规治疗或不治疗",
            "基线资料完整",
        ],
        "default_exclusion": [
            "预期随访依从性差",
            "合并需紧急干预的疾病",
        ],
        "sample_method": "Cox 模型所需最小事件数估算",
        "default_effect_size": 0.4,
        "design_notes": [
            "前瞻性队列设计，设置暴露组与非暴露组",
            "定期随访收集结局事件与混杂变量",
        ],
    },
    StudyType.CASE_CONTROL: {
        "blinding": "不适用",
        "randomization": "不适用（回顾性设计）",
        "statistical_plan": "条件 / 非条件 Logistic 回归；OR 值及 95% CI",
        "duration": "回顾性收集",
        "ethical_considerations": "需获得伦理委员会批准",
        "default_inclusion": [
            "病例组：确诊目标疾病",
            "对照组：同时期同医院未患病者",
            "病历资料完整",
        ],
        "default_exclusion": [
            "诊断不明确",
            "关键暴露信息缺失",
        ],
        "sample_method": "Kelsey 公式（病例对照）",
        "default_effect_size": 0.4,
        "design_notes": [
            "按年龄、性别匹配，病例 : 对照 = 1 : 1-4",
            "采用结构化问卷或病历回顾收集暴露因素",
        ],
    },
    StudyType.NETWORK_PHARMACOLOGY: {
        "blinding": "不适用",
        "randomization": "不适用（计算生物学设计）",
        "statistical_plan": "拓扑分析（Degree / Betweenness / Closeness）；GO & KEGG 富集分析；分子对接验证",
        "duration": "计算周期 1-4 周",
        "ethical_considerations": "无需伦理审批（计算研究）",
        "default_inclusion": [
            "化合物来源于目标方剂",
            "OB ≥ 30%，DL ≥ 0.18",
            "靶点来源于 GeneCards / OMIM / TTD",
        ],
        "default_exclusion": [
            "无明确 SMILES 结构的化合物",
            "物种非人源的靶点",
        ],
        "sample_method": "活性成分数量 × 靶点数量",
        "default_effect_size": 0.0,
        "design_notes": [
            "基于 TCMSP / BATMAN-TCM 获取活性成分",
            "构建 PPI 网络并筛选核心靶点",
            "使用 AutoDock Vina 进行分子对接验证",
        ],
    },
}


# ---------------------------------------------------------------------------
# 样本量估算辅助
# ---------------------------------------------------------------------------

def _estimate_sample_size(alpha: float = 0.05, power: float = 0.80,
                          effect_size: float = 0.5) -> int:
    """基于 Cohen's d 简化估算两组比较所需每组样本量。

    n = (z_alpha/2 + z_beta)^2 * 2 / d^2
    """
    from statistics import NormalDist
    if effect_size <= 0:
        return 0
    norm = NormalDist()
    z_alpha = norm.inv_cdf(1 - alpha / 2)
    z_beta = norm.inv_cdf(power)
    n_per_group = math.ceil((z_alpha + z_beta) ** 2 * 2 / (effect_size ** 2))
    return n_per_group * 2  # 两组总量


# ---------------------------------------------------------------------------
# ExperimentDesigner
# ---------------------------------------------------------------------------

class ExperimentDesigner(BaseModule):
    """中医科研实验方案结构化设计辅助。

    提供 RCT、系统综述、Meta 分析、队列、病例对照、网络药理学
    六种研究设计的模板化方案生成。
    """

    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__(module_name="ExperimentDesigner", config=config)

    # -- BaseModule abstract implementations --------------------------------

    def _do_initialize(self) -> bool:
        return True

    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis = context.get("hypothesis", "")
        study_type = context.get("study_type", "rct")
        protocol = self.design_study(hypothesis, study_type)
        return {"protocol": protocol.to_dict()}

    def _do_cleanup(self) -> bool:
        return True

    # -- public api ---------------------------------------------------------

    def design_study(
        self,
        hypothesis: str,
        study_type: str | StudyType,
        *,
        population: str = "",
        intervention: str = "",
        comparison: str = "",
        outcome: str = "",
        alpha: float = 0.05,
        power: float = 0.80,
        effect_size: float | None = None,
    ) -> StudyProtocol:
        """根据假设与研究类型生成结构化 StudyProtocol。

        Parameters
        ----------
        hypothesis : str
            研究假设陈述。
        study_type : str | StudyType
            研究设计类型。
        population, intervention, comparison, outcome : str
            PICO 各要素，不提供则使用模板默认文本。
        alpha, power, effect_size : float
            样本量估算参数。
        """
        stype = self._resolve_study_type(study_type)
        tmpl = _TEMPLATES.get(stype, {})

        pico = PICO(
            population=population or f"[待填写 — {stype.value} 研究人群]",
            intervention=intervention or "[待填写 — 干预措施]",
            comparison=comparison or "[待填写 — 对照措施]",
            outcome=outcome or "[待填写 — 主要结局指标]",
        )

        es = effect_size if effect_size is not None else tmpl.get("default_effect_size", 0.5)
        estimated_n = _estimate_sample_size(alpha, power, es) if es > 0 else 0
        sample = SampleSizeEstimation(
            alpha=alpha,
            power=power,
            effect_size=es,
            estimated_n=estimated_n,
            method=tmpl.get("sample_method", ""),
        )

        eligibility = EligibilityCriteria(
            inclusion=list(tmpl.get("default_inclusion", [])),
            exclusion=list(tmpl.get("default_exclusion", [])),
        )

        protocol = StudyProtocol(
            study_type=stype.value,
            hypothesis=hypothesis,
            pico=pico,
            sample_size=sample,
            eligibility=eligibility,
            primary_outcome=outcome or "[待填写 — 主要结局指标]",
            blinding=tmpl.get("blinding", ""),
            randomization=tmpl.get("randomization", ""),
            statistical_plan=tmpl.get("statistical_plan", ""),
            duration=tmpl.get("duration", ""),
            ethical_considerations=tmpl.get("ethical_considerations", ""),
            design_notes=list(tmpl.get("design_notes", [])),
        )

        logger.info(
            "design_study: type=%s, filled_required=%d",
            stype.value,
            protocol.filled_required_count(),
        )
        return protocol

    def list_study_types(self) -> List[str]:
        """返回所有可用研究类型名称。"""
        return [t.value for t in StudyType]

    # -- internal helpers ---------------------------------------------------

    @staticmethod
    def _resolve_study_type(raw: str | StudyType) -> StudyType:
        if isinstance(raw, StudyType):
            return raw
        normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
        for member in StudyType:
            if member.value == normalized or member.name.lower() == normalized:
                return member
        raise ValueError(f"不支持的研究类型: {raw!r}，可选: {[t.value for t in StudyType]}")
