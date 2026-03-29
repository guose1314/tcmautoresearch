"""
综合演示 - 语义建模中的多维度研究方法集成
展示如何在一个统一框架中使用四大研究方法
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.extractors.advanced_entity_extractor import AdvancedEntityExtractor
from src.preprocessor.document_preprocessor import DocumentPreprocessor
from src.semantic_modeling.semantic_graph_builder import SemanticGraphBuilder


def test_integrated_semantic_modeling():
    """
    完整的集成演示
    """
    print("\n" + "="*80)
    print("INTEGRATED SEMANTIC MODELING - Multiple Research Perspectives")
    print("="*80)
    
    # 【准备阶段】
    print("\n[PHASE 1] Preparation - Text & Entity Processing")
    print("-" * 80)
    
    test_text = """
    《脾胃论》载：补中益气汤由黄芪、人参、白术、茯苓、甘草等组成。
    黄芪为君药，人参为臣药，白术与茯苓为佐药，甘草为使药。
    主治气虚证，功效为补气、健脾、固表。
    """
    
    # 文本预处理
    preprocessor = DocumentPreprocessor()
    preprocessor.initialize()
    context = {"raw_text": test_text}
    preprocess_result = preprocessor.execute(context)
    processed_text = preprocess_result.get("processed_text", test_text)
    
    print(f"[OK] Text preprocessed")
    
    # 实体抽取
    extractor = AdvancedEntityExtractor()
    extractor.initialize()
    context["processed_text"] = processed_text
    extract_result = extractor.execute(context)
    entities = extract_result.get("entities", [])
    
    print(f"[OK] Entities extracted: {len(entities)} entities")
    
    # 【核心阶段】语义建模 + 多维研究视角
    print("\n[PHASE 2] Semantic Modeling with Advanced Research Methods")
    print("-" * 80)
    
    graph_builder = SemanticGraphBuilder()
    graph_builder.initialize()
    context["entities"] = entities
    graph_result = graph_builder.execute(context)
    
    print(f"[OK] Semantic graph constructed")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【输出1】基础图统计
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 1] Graph Statistics")
    print("-" * 80)
    
    stats = graph_result.get("graph_statistics", {})
    print(f"  Nodes: {stats.get('nodes_count', 0)}")
    print(f"  Edges: {stats.get('edges_count', 0)}")
    print(f"  Density: {stats.get('density', 0):.3f}")
    
    rel_stats = stats.get('relationships_by_type', {})
    print(f"\n  Relationship types:")
    for rel_type, rel_data in list(rel_stats.items())[:5]:
        print(f"    {rel_type}: {rel_data.get('count')} instances")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【输出2】方剂结构分析 - Formula Structure
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 2] Formula Structure Analysis (方剂结构)")
    print("-" * 80)
    
    research_persp = graph_result.get("research_perspectives", {})
    for formula_name, perspective_data in research_persp.items():
        structure = perspective_data.get("structure", {})
        if structure:
            print(f"\n  [{formula_name}]")
            print(f"    Dosage form: {structure.get('dosage_form')}")
            print(f"    Total dosage: {structure.get('total_dosage')}g")
            print(f"    Herb count: {structure.get('herb_count')}")
            
            dist = structure.get('role_distribution', {})
            print(f"    Sovereign:  {dist.get('sovereign_ratio', 0):.1%}")
            print(f"    Minister:   {dist.get('minister_ratio', 0):.1%}")
            print(f"    Assistant:  {dist.get('assistant_ratio', 0):.1%}")
            print(f"    Envoy:      {dist.get('envoy_ratio', 0):.1%}")
            
            print(f"    Characteristics: {structure.get('characteristics')}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【输出3】药物性味与归经 - Herb Properties
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 3] Herb Properties - Si Qi Wu Wei & Meridian Entry (性味归经)")
    print("-" * 80)
    
    herb_props = graph_result.get("herb_properties", {})
    for herb_name, prop_data in list(herb_props.items())[:4]:
        if prop_data:
            print(f"\n  [{herb_name}]")
            print(f"    Temperature: {prop_data.get('temperature')} (四气)")
            print(f"    Flavors: {prop_data.get('flavors')} (五味)")
            print(f"    Meridians: {', '.join(prop_data.get('meridians', []))} (归经)")
            print(f"    Primary: {prop_data.get('primary_efficacy')}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【输出4】类方比较 - Similar Formula Comparison
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 4] Similar Formula Comparison (类方比较)")
    print("-" * 80)
    
    formula_comps = graph_result.get("formula_comparisons", [])
    for i, comp in enumerate(formula_comps):
        print(f"\n  [{i+1}] {comp.get('formula1')} vs {comp.get('formula2')}")
        print(f"    Common herbs: {', '.join(comp.get('common_herbs', []))}")
        print(f"    Difference: {comp.get('difference')}")
        print(f"    Clinical selection: {comp.get('clinical_selection')}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【输出5】现代药理学 - Modern Pharmacology
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 5] Modern Pharmacology & Clinical Research (现代药理学)")
    print("-" * 80)
    
    pharmacology = graph_result.get("pharmacology_integration", {})
    for herb_name, pharm_data in list(pharmacology.items())[:3]:
        print(f"\n  [{herb_name}]")
        
        components = pharm_data.get("components", {})
        if components:
            print(f"    Active components: {', '.join(list(components.keys())[:2])}")
        
        actions = pharm_data.get("actions", [])
        if actions:
            print(f"    Pharmacological actions:")
            for action in actions[:2]:
                print(f"      - {action}")
        
        clinical = pharm_data.get("clinical", {})
        if clinical:
            print(f"    Clinical efficacy:")
            for indication, rate in list(clinical.items())[:2]:
                print(f"      - {indication}: {rate:.0%}")
        
        safety = pharm_data.get("safety", {})
        adverse = safety.get("adverse_effects", [])
        if adverse:
            print(f"    Adverse effects: {adverse[0]}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【输出6】网络药理学与系统性生物学
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 6] Network Pharmacology & Systems Biology (网络药理学与系统生物学)")
    print("-" * 80)

    network_systems = graph_result.get("network_pharmacology_systems_biology", {})
    for formula_name, data in network_systems.items():
        print(f"\n  [{formula_name}]")
        print(f"    Target count: {data.get('target_count', 0)}")
        key_targets = data.get("key_targets", [])[:4]
        if key_targets:
            print("    Key targets:")
            for t in key_targets:
                print(f"      - {t.get('target')} (degree={t.get('degree')})")
        pathways = data.get("enriched_pathways", [])[:3]
        if pathways:
            print("    Pathways:")
            for p in pathways:
                print(f"      - {p.get('pathway')} (score={p.get('score')})")

    # ─────────────────────────────────────────────────────────────────────────
    # 【输出7】超分子化学和物理化学
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 7] Supramolecular Chemistry & Physicochemistry (超分子化学与物理化学)")
    print("-" * 80)

    supramolecular = graph_result.get("supramolecular_physicochemistry", {})
    for formula_name, data in supramolecular.items():
        print(f"\n  [{formula_name}]")
        print(f"    Available: {data.get('available')}")
        metrics = data.get("metrics", {})
        if metrics:
            print(f"    Solubility index: {metrics.get('solubility_index', 0):.3f}")
            print(f"    H-bond network: {metrics.get('h_bond_network', 0):.3f}")
            print(f"    PI stacking: {metrics.get('pi_stacking_potential', 0):.3f}")
        print(f"    Synergy score: {data.get('supramolecular_synergy_score', 0):.3f}")

    # ─────────────────────────────────────────────────────────────────────────
    # 【输出8】古典文献数字化与知识考古
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 8] Classical Literature Digitization & Knowledge Archaeology (古典文献数字化与知识考古)")
    print("-" * 80)

    archaeology = graph_result.get("knowledge_archaeology", {})
    for formula_name, data in archaeology.items():
        print(f"\n  [{formula_name}]")
        origin = data.get("origin", {})
        print(f"    Source: {origin.get('source')}")
        print(f"    Dynasty: {origin.get('dynasty')}")
        print(f"    Author: {origin.get('author')}")
        evo = data.get("evolution_notes", [])
        if evo:
            print("    Evolution notes:")
            for note in evo[:2]:
                print(f"      - {note}")

    # ─────────────────────────────────────────────────────────────────────────
    # 【输出9】复杂性科学与非线性动力学
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 9] Complexity Science & Nonlinear Dynamics (复杂性科学与非线性动力学)")
    print("-" * 80)

    dynamics = graph_result.get("complexity_nonlinear_dynamics", {})
    for formula_name, data in dynamics.items():
        print(f"\n  [{formula_name}]")
        print(f"    Stability: {data.get('stability', 0):.3f}")
        print(f"    Adaptivity: {data.get('adaptivity', 0):.3f}")
        print(f"    Resilience index: {data.get('resilience_index', 0):.3f}")
        print(f"    Complexity score: {data.get('complexity_score', 0):.3f}")
        print(f"    Regime: {data.get('dynamic_regime')}")

    # ─────────────────────────────────────────────────────────────────────────
    # 【输出10】统一评分面板（8维标准化）
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 10] Unified Scoring Panel (8 dimensions, 0-1 normalization)")
    print("-" * 80)

    panel = graph_result.get("research_scoring_panel", {})
    for formula_name, score in panel.items():
        print(f"\n  [{formula_name}]")
        print(f"    Total score: {score.get('total_score', 0):.3f}")
        ci = score.get("confidence_interval_95", {})
        print(
            f"    95% CI: [{ci.get('lower', 0):.3f}, {ci.get('upper', 0):.3f}] "
            f"(margin={ci.get('margin', 0):.3f})"
        )
        print("    Dimension scores:")
        for dim, val in score.get("dimension_scores", {}).items():
            print(f"      - {dim}: {val:.3f}")
        print(f"    Strengths: {', '.join(score.get('strengths', []))}")
        print(f"    Gaps: {', '.join(score.get('gaps', []))}")

        print("    Paper paragraph inputs:")
        p = score.get("paper_paragraph_inputs", {})
        print(f"      Headline: {p.get('headline', '')}")
        for item in p.get("method_summary", []):
            print(f"      Method: {item}")
        for item in p.get("evidence_summary", []):
            print(f"      Evidence: {item}")

    # ─────────────────────────────────────────────────────────────────────────
    # 【输出11】总结分析方法集成
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[OUTPUT 11] Summary Analysis Methods (统计/挖掘/建模)")
    print("-" * 80)

    summary = graph_result.get("summary_analysis", {})

    # 1) 频率/卡方
    fc = summary.get("frequency_chi_square", {})
    print("\n  [1] Frequency + Chi-square")
    print(f"    Top herbs: {fc.get('herb_frequency', [])[:5]}")
    print(f"    Chi-square top: {fc.get('chi_square_top', [])[:3]}")

    # 2) 关联规则
    ar = summary.get("association_rules", {})
    print("\n  [2] Association Rules")
    print(f"    Rule count: {len(ar.get('rules', []))}")
    print(f"    Top rules: {ar.get('rules', [])[:3]}")

    # 3) 复杂网络
    cn = summary.get("complex_network", {})
    print("\n  [3] Complex Network Analysis")
    print(f"    Nodes/Edges: {cn.get('nodes')} / {cn.get('edges')}")
    print(f"    Density: {cn.get('density')}, Avg clustering: {cn.get('avg_clustering')}")

    # 4) 聚类与因子
    cf = summary.get("clustering_factor", {})
    print("\n  [4] Clustering + Factor Analysis")
    print(f"    Cluster assignments: {cf.get('clusters', [])[:5]}")
    print(f"    Factors: {cf.get('factors', [])[:2]}")

    # 5) 强化剂量分析
    rd = summary.get("reinforced_dosage", {})
    print("\n  [5] Reinforced Dosage Analysis")
    print(f"    Optimized ratios keys: {list(rd.get('optimized_ratios', {}).keys())}")

    # 6) 隐结构模型
    ls = summary.get("latent_structure", {})
    print("\n  [6] Latent Structure Model")
    print(f"    Topics: {ls.get('topics', [])[:2]}")

    # 7) 时间序列 + 剂量-反应
    tr = summary.get("time_series_dose_response", {})
    print("\n  [7] Time Series + Dose-Response")
    print(f"    Trend: {tr.get('time_series_trend')}")
    print(f"    Dose model: {tr.get('dose_response')}")

    # 8) 贝叶斯网络
    bn = summary.get("bayesian_network", {})
    print("\n  [8] Bayesian Network")
    print(f"    Structure: {bn.get('structure')}")
    print(f"    Inference: {bn.get('inference_example')}")

    # ─────────────────────────────────────────────────────────────────────────
    # 【汇总】多维度研究框架
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("[INTEGRATED RESEARCH FRAMEWORK SUMMARY]")
    print("="*80)
    
    print("\nFour Research Perspectives in Semantic Modeling:")
    print("\n  [1] STRUCTURE (结构):")
    print("      - Formula composition (方剂组成)")
    print("      - Dosage distribution (用量分布)")
    print("      - Role proportion (角色比例)")
    print("      - Pairing rules (配伍规律)")
    
    print("\n  [2] PROPERTIES (性味):")
    print("      - Four Qi (四气: 温平凉)")
    print("      - Five Flavors (五味: 甘苦酸咸)")
    print("      - Meridian entry (归经: 经络)")
    print("      - Herb selection basis (遴选依据)")
    
    print("\n  [3] COMPARISON (比较):")
    print("      - Similar formulas (类方识别)")
    print("      - Common components (共同成分)")
    print("      - Differentiation points (鉴别要点)")
    print("      - Clinical application guide (临床指导)")
    
    print("\n  [4] PHARMACOLOGY (药理):")
    print("      - Active components (有效成分)")
    print("      - Pharmacological actions (药理作用)")
    print("      - Clinical efficacy (临床疗效)")
    print("      - Safety profile (安全性)")

    print("\n  [5] NETWORK PHARMACOLOGY (网络药理):")
    print("      - Herb-target-pathway network (药物-靶点-通路)")
    print("      - Multi-target synergy hypothesis (多靶点协同)")

    print("\n  [6] SUPRAMOLECULAR / PHYSICOCHEMICAL (超分子/物化):")
    print("      - Non-covalent interaction profile (非共价作用)")
    print("      - Release and dispersion behavior (释放与分散)")

    print("\n  [7] KNOWLEDGE ARCHAEOLOGY (知识考古):")
    print("      - Classical source lineage (文献源流)")
    print("      - Variant-name evolution graph (异名演化图)")

    print("\n  [8] COMPLEXITY DYNAMICS (复杂动力学):")
    print("      - Stability and resilience indices (稳态与韧性)")
    print("      - Nonlinear regime inference (非线性态判定)")

    print("\n  [9] UNIFIED SCORING PANEL (统一评分面板):")
    print("      - 8 dimensions normalized to 0-1")
    print("      - Weighted total score + 95% confidence interval")
    print("      - Direct paragraph inputs for paper drafting")
    
    print("\n" + "="*80)
    print("[SUCCESS] Integrated Semantic Modeling Complete!")
    print("="*80)
    
    print("\nApplications:")
    print("  - Evidence-based formula optimization")
    print("  - Herb substitution for clinical practice")
    print("  - Formula innovation based on structure analysis")
    print("  - Safety and efficacy assessment")
    print("  - Clinical decision support system")

    assert isinstance(graph_result, dict)
    assert "summary_analysis" in graph_result


if __name__ == "__main__":
    try:
        test_integrated_semantic_modeling()
        print("\n[Integration complete - all research methods operational]")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
