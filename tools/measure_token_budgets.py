"""Measure real-world prompt sizes for critical tasks to calibrate token budgets.

Usage:
    python -m tools.measure_token_budgets

Simulates representative prompts for:
  - graph_reasoning (hypothesis_engine.kg_enhanced)
  - paper_full_section (paper_plugin translate + summarize)
  - large_evidence_synthesis (dossier_builder LLM summarize)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infra.token_budget_policy import (
    apply_token_budget_to_prompt,
    estimate_text_tokens,
    reset_token_budget_policy_settings_cache,
    resolve_token_budget,
)

# ───────────────────────────────────────────────────────────────────
# 1. graph_reasoning (hypothesis_engine.kg_enhanced)
#    Template fills: gap_details, kg_structure_summary, context_summary
# ───────────────────────────────────────────────────────────────────

_KG_SYSTEM_PROMPT = (
    "你是中医科研假设生成专家。请基于知识图谱缺口分析与结构证据生成高质量研究假设，"
    "并为每条假设标注来源缺口类型与相关实体。"
)

# Simulate 8 gaps (typical case when multiple TCM entities are under-connected)
_KG_GAP_DETAILS = "\n".join(
    f"{i}. [HIGH] mechanism_gap: {entity} (herb) — "
    f"缺少{entity}对该证候型的作用机制研究，当前知识图谱中无直接通路连接"
    for i, entity in enumerate([
        "黄芪", "当归", "白术", "茯苓", "甘草", "人参", "柴胡", "半夏",
    ], 1)
)

_KG_STRUCTURE_SUMMARY = """图谱节点数: 2847，边数: 6532
「黄芪」邻域: 12 个邻居 (补中益气汤, 脾气虚证, 黄芪多糖, 升阳举陷, 补肺固表)
「当归」邻域: 8 个邻居 (四物汤, 补血活血, 阿魏酸, 血虚证, 妇科病)
「白术」邻域: 6 个邻居 (四君子汤, 健脾燥湿, 苍术酮, 脾虚泄泻, 痰饮)
「茯苓」邻域: 9 个邻居 (五苓散, 利水渗湿, 茯苓酸, 水肿, 心悸)
路径: 黄芪 → 补气 → 脾 → 健脾 → 白术
路径: 当归 → 补血 → 肝 → 疏肝 → 柴胡"""

_KG_CONTEXT_SUMMARY = (
    "研究主题：补中益气汤治疗脾气虚型慢性疲劳综合征的机制探索。"
    "已有文献提示黄芪多糖可通过 TLR4/NF-κB 通路调节免疫功能，"
    "但缺乏整方层面的多靶点协同机制研究。"
    "当前知识图谱中脾气虚证与免疫调节的连接仅依赖少量临床试验报告。"
)

_KG_USER_TEMPLATE = (
    "你是中医科研假设生成专家。请基于以下知识图谱缺口分析生成高质量研究假设。\n\n"
    "## 知识图谱缺口分析\n\n"
    "共发现 {gap_count} 个知识缺口：\n{gap_details}\n\n"
    "## 图谱结构摘要\n\n"
    "{kg_structure_summary}\n\n"
    "## 研究上下文\n\n"
    "{context_summary}\n\n"
    "## 要求\n\n"
    "请基于上述图谱缺口和结构信息，生成 {num_hypotheses} 条可验证的中医科研假设。"
)

# JSON Schema suffix (rendered from _HYPOTHESIS_ENGINE_SCHEMA)
_KG_SCHEMA_SUFFIX = """请严格按以下 JSON Schema 输出，只输出单个 JSON 数组，禁止附加解释。

JSON Schema:
{
  "type": "array",
  "minItems": 1,
  "items": {
    "type": "object",
    "required": ["title", "statement", "rationale", "novelty", "feasibility", "evidence_support", "validation_plan", "keywords"],
    "properties": {
      "title": {"type": "string", "minLength": 1},
      "statement": {"type": "string", "minLength": 1},
      "rationale": {"type": "string", "minLength": 1},
      "novelty": {"type": "number", "minimum": 0, "maximum": 1},
      "feasibility": {"type": "number", "minimum": 0, "maximum": 1},
      "evidence_support": {"type": "number", "minimum": 0, "maximum": 1},
      "validation_plan": {"type": "string", "minLength": 1},
      "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 1},
      "source_gap_type": {"type": "string"},
      "source_entities": {"type": "array", "items": {"type": "string"}}
    }
  }
}"""


# ───────────────────────────────────────────────────────────────────
# 2. paper_full_section (paper_plugin)
#    purpose=paper_plugin → task=paper_full_section
#    Typical: translate/summarize 12000 chars of paper content
# ───────────────────────────────────────────────────────────────────

_PAPER_SYSTEM_PROMPT = "You are an academic paper translator."

# Simulate a typical academic paper section (mixed EN/CN) ~3000 chars
_PAPER_SECTION = (
    "Background: Traditional Chinese Medicine (TCM) has a long history of treating "
    "chronic fatigue syndrome (CFS) through herbal formulas that tonify qi and "
    "strengthen the spleen. Among them, Buzhong Yiqi Decoction (补中益气汤) is the "
    "most widely prescribed. Recent pharmacological studies have identified multiple "
    "active compounds including Astragaloside IV, ferulic acid, and atractylenolide III.\n\n"
    "Methods: We conducted a systematic review of randomized controlled trials (RCTs) "
    "evaluating BZYQD for CFS published between 2010-2025. Databases searched included "
    "PubMed, CNKI, Wanfang, and VIP. Primary outcomes were Chalder Fatigue Scale scores "
    "and TCM syndrome scores.\n\n"
    "Results: A total of 23 RCTs involving 2,156 participants were included. "
    "Meta-analysis showed that BZYQD significantly reduced Chalder Fatigue Scale scores "
    "(SMD = -1.24, 95% CI [-1.58, -0.90], p < 0.001) compared to conventional treatment alone. "
    "Subgroup analysis by treatment duration revealed that courses ≥8 weeks showed "
    "greater effect sizes than shorter treatments.\n\n"
) * 4  # ~3000 chars, simulate a full section


_PAPER_USER_PROMPT = (
    "请把以下论文内容翻译为 中文，保留术语准确性。"
    "如果原文已经是目标语言，可做轻微润色。\n\n"
    f"内容:\n{_PAPER_SECTION[:12000]}"
)


# ───────────────────────────────────────────────────────────────────
# 3. large_evidence_synthesis (dossier LLM summarize)
#    purpose=evidence_synthesis → task=large_evidence_synthesis
#    Typical: multi-phase evidence concatenation needing compression
# ───────────────────────────────────────────────────────────────────

_EVIDENCE_SYSTEM_PROMPT = "你是中医临床证据综合分析师。请对研究证据进行分层整理和批判性评估。"

# Simulate evidence from multiple phases of a research cycle
_EVIDENCE_ITEMS = [
    "Phase 1 文献检索结果：共检索到 45 篇相关文献，其中 RCT 12 篇、队列研究 8 篇、"
    "病例报告 15 篇、综述 10 篇。主要干预措施为补中益气汤加减，对照组多为常规西药治疗。",
    "Phase 2 质量评价：12 篇 RCT 中 Jadad 评分 ≥3 分者仅 5 篇（41.7%），主要缺陷包括"
    "随机方法描述不清（8/12）、未提及分配隐藏（10/12）、未设盲法（7/12）。",
    "Phase 3 知识图谱分析：实体抽取共识别药物 28 种、方剂 6 首、证候 12 种、症状 34 个、"
    "通路 8 条。核心实体为黄芪（度=15）、补中益气汤（度=12）、脾气虚证（度=9）。"
    "发现 3 个关键知识缺口：(1) 黄芪多糖-肠道菌群-免疫轴的机制连接缺失；"
    "(2) 方证量效关系的系统数据空白；(3) 长期疗效随访数据不足。",
    "Phase 4 假设生成：基于缺口分析生成 5 条假设，优先级最高的为："
    "'补中益气汤通过调节肠道菌群组成改善脾气虚型 CFS 患者的疲劳症状，"
    "其效应由黄芪多糖-SCFAs-Treg 细胞轴介导'。"
    "该假设新颖度 0.85、可行性 0.72、证据支撑 0.68。",
    "Phase 5 研究设计建议：推荐开展前瞻性随机双盲安慰剂对照试验，"
    "样本量 ≥120 例，疗程 12 周，主要结局指标为 Chalder 疲劳量表评分变化，"
    "次要指标包括肠道菌群 16S rRNA 测序、血清 SCFAs 水平、外周血 Treg 比例。",
]

_EVIDENCE_USER_PROMPT = (
    "请对以下多阶段研究证据进行综合分析，提出结论和方法学建议：\n\n"
    + "\n\n".join(_EVIDENCE_ITEMS)
)


# ───────────────────────────────────────────────────────────────────
# Measurement
# ───────────────────────────────────────────────────────────────────

def measure_task(
    name: str,
    task: str,
    purpose: str,
    system_prompt: str,
    user_prompt: str,
    suffix_prompt: str = "",
):
    """Measure a task's token consumption and print report."""
    sys_tokens = estimate_text_tokens(system_prompt)
    user_tokens = estimate_text_tokens(user_prompt)
    suffix_tokens = estimate_text_tokens(suffix_prompt) if suffix_prompt else 0
    total_tokens = sys_tokens + user_tokens + suffix_tokens

    resolution = resolve_token_budget(task=task, purpose=purpose)
    budget = resolution.input_budget_tokens

    result = apply_token_budget_to_prompt(
        user_prompt,
        system_prompt=system_prompt,
        task=task,
        purpose=purpose,
        suffix_prompt=suffix_prompt,
    )

    print(f"\n{'='*70}")
    print(f"  Task: {name}")
    print(f"  task_key={task}, purpose={purpose}")
    print(f"{'='*70}")
    print(f"  System prompt:    {sys_tokens:>5} tokens ({len(system_prompt)} chars)")
    print(f"  User body:        {user_tokens:>5} tokens ({len(user_prompt)} chars)")
    print(f"  Schema suffix:    {suffix_tokens:>5} tokens")
    print(f"  Total input:      {total_tokens:>5} tokens")
    print(f"  ────────────────────────────────────")
    print(f"  Current budget:   {budget:>5} tokens (source: {resolution.source})")
    print(f"  Hard cap:         {resolution.hard_cap_tokens:>5} tokens")
    print(f"  ────────────────────────────────────")
    print(f"  After trim:       {result.total_input_tokens_after:>5} tokens")
    print(f"  Trimmed?          {'YES' if result.trimmed else 'No'}")
    print(f"  Headroom:         {budget - total_tokens:>+5} tokens ({'OK' if total_tokens <= budget else 'OVER'})")
    print()

    # Recommend budget
    # For 7B stability: want ~15% headroom on a typical prompt, no trim in normal case
    # But for CAUTIOUS/UNSUITABLE tasks, we may intentionally trim extra context
    recommended = int(total_tokens * 1.15)
    # Round up to nearest 64
    recommended = ((recommended + 63) // 64) * 64
    # Clamp to hard cap
    recommended = min(recommended, resolution.hard_cap_tokens)
    # At least min
    recommended = max(recommended, 512)

    if result.trimmed:
        print(f"  ⚠ Prompt is being trimmed!")
        print(f"    Original body tokens: {result.user_tokens_before}")
        print(f"    Trimmed body tokens:  {result.user_tokens_after}")
        print(f"    Information loss:     ~{100 * (1 - result.user_tokens_after / max(1, result.user_tokens_before)):.0f}%")
    
    print(f"  RECOMMENDED budget: {recommended} tokens")
    print(f"    (based on typical prompt={total_tokens} + 15% headroom, ceil 64)")
    
    return {
        "name": name,
        "task": task,
        "total_tokens": total_tokens,
        "current_budget": budget,
        "trimmed": result.trimmed,
        "recommended": recommended,
    }


def main():
    reset_token_budget_policy_settings_cache()

    print("\n" + "╔" + "═"*68 + "╗")
    print("║  Token Budget Calibration — Real-world Prompt Measurement         ║")
    print("║  Context window: 4096, Reserved output: 1024 → Hard cap: 3072     ║")
    print("╚" + "═"*68 + "╝")

    # graph_reasoning
    kg_user = _KG_USER_TEMPLATE.format(
        gap_count=8,
        gap_details=_KG_GAP_DETAILS,
        kg_structure_summary=_KG_STRUCTURE_SUMMARY,
        context_summary=_KG_CONTEXT_SUMMARY,
        num_hypotheses=5,
    )
    r1 = measure_task(
        name="graph_reasoning (hypothesis_engine.kg_enhanced)",
        task="graph_reasoning",
        purpose="default",
        system_prompt=_KG_SYSTEM_PROMPT,
        user_prompt=kg_user,
        suffix_prompt=_KG_SCHEMA_SUFFIX,
    )

    # paper_full_section
    r2 = measure_task(
        name="paper_full_section (paper_plugin translate)",
        task="paper_full_section",
        purpose="paper_plugin",
        system_prompt=_PAPER_SYSTEM_PROMPT,
        user_prompt=_PAPER_USER_PROMPT,
        suffix_prompt="",  # paper_plugin doesn't use registered schema suffix
    )

    # large_evidence_synthesis
    r3 = measure_task(
        name="large_evidence_synthesis (dossier evidence)",
        task="large_evidence_synthesis",
        purpose="evidence_synthesis",
        system_prompt=_EVIDENCE_SYSTEM_PROMPT,
        user_prompt=_EVIDENCE_USER_PROMPT,
        suffix_prompt="",  # Called via direct engine.generate(), no schema suffix
    )

    # Summary table
    results = [r1, r2, r3]
    print("\n" + "─"*70)
    print("  SUMMARY")
    print("─"*70)
    print(f"  {'Task':<35} {'Now':>6} {'Needed':>7} {'Rec.':>6}  Status")
    print(f"  {'─'*35} {'─'*6} {'─'*7} {'─'*6}  {'─'*10}")
    for r in results:
        status = "TRIMMED" if r["trimmed"] else "OK"
        print(f"  {r['name'][:35]:<35} {r['current_budget']:>6} {r['total_tokens']:>7} {r['recommended']:>6}  {status}")
    print()

    # Suggested config patch
    print("  SUGGESTED config.yml patch (task_input_budgets):")
    print("  ─────────────────────────────────────────────────")
    for r in results:
        print(f"    {r['task']}: {r['recommended']}")
    print()


if __name__ == "__main__":
    main()
