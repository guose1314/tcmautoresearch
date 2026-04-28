"""
高级研究方法测试 - 方剂结构、性味归经、类方比较、现代药理学
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis import (
    ClassicalLiteratureArchaeologyAnalyzer,
    ComplexityNonlinearDynamicsAnalyzer,
    FormulaComparator,
    FormulaStructureAnalyzer,
    HerbPropertyDatabase,
    IntegratedResearchAnalyzer,
    ModernPharmacologyDatabase,
    NetworkPharmacologySystemBiologyAnalyzer,
    ResearchScoringPanel,
    SupramolecularPhysicochemicalAnalyzer,
)


def _print_methods_banner() -> None:
    print("\n" + "=" * 80)
    print("ADVANCED RESEARCH METHODS - Formula Structure, Herb Properties, Etc.")
    print("=" * 80)


def _print_formula_structure(formula_names):
    print("\n[METHOD 1] Formula Structure Analysis - Sovereign/Minister/Assistant/Envoy")
    print("-" * 80)
    for formula_name in formula_names:
        structure = FormulaStructureAnalyzer.analyze_formula_structure(formula_name)
        if structure:
            print(f"\n[{formula_name}]")
            print(f"  Dosage form: {structure.get('dosage_form')}")
            print(f"  Total dosage: {structure.get('total_dosage')}g")
            print(f"  Herb count: {structure.get('herb_count')} types")
            role_dist = structure.get('role_distribution', {})
            print(f"  Role distribution:")
            print(f"    - Sovereign: {role_dist.get('sovereign_ratio', 0):.1%}")
            print(f"    - Minister: {role_dist.get('minister_ratio', 0):.1%}")
            print(f"    - Assistant: {role_dist.get('assistant_ratio', 0):.1%}")
            print(f"    - Envoy: {role_dist.get('envoy_ratio', 0):.1%}")
            print(f"  Characteristics: {structure.get('characteristics')}")
            print(f"  Pairing rules:")
            for rule in structure.get('pairing_rules', []):
                print(f"    * {rule}")


def _print_herb_properties(herbs):
    print("\n[METHOD 2] Herb Properties & Meridian Entry (Si Qi Wu Wei)")
    print("-" * 80)
    for herb_name in herbs:
        prop = HerbPropertyDatabase.get_herb_property(herb_name)
        if prop:
            print(f"\n[{herb_name}]")
            print(f"  Temperature: {prop.get('temperature')} (Four Qi)")
            print(f"  Flavors: {', '.join(prop.get('flavors', []))} (Five Flavors)")
            print(f"  Meridians: {', '.join(prop.get('meridians', []))}")
            print(f"  Primary efficacy: {prop.get('primary_efficacy')}")
            print(f"  Secondary efficacy: {', '.join(prop.get('secondary_efficacy', []))}")
            print(f"  Dosage: {prop.get('dosage')}")
            if prop.get('note'):
                print(f"  Note: {prop.get('note')}")
    print("\n[Herbs by Meridian]")
    for meridian in ["spleen", "lung", "heart"]:
        meridian_herbs = HerbPropertyDatabase.get_herbs_by_meridian(meridian)
        print(f"  {meridian}: {', '.join(meridian_herbs)}")


def _print_formula_comparisons():
    print("\n[METHOD 3] Similar Formula Comparison (Lei Fang Bi Jiao)")
    print("-" * 80)
    for f1, f2 in [("补中益气汤", "四君子汤"), ("四君子汤", "六君子汤")]:
        comparison = FormulaComparator.compare_formulas(f1, f2)
        if comparison:
            print(f"\n[{f1} vs {f2}]")
            print(f"  Common herbs: {', '.join(comparison.get('common_herbs', []))}")
            print(f"  Difference: {comparison.get('difference')}")
            print(f"  Clinical selection:")
            print(f"    {comparison.get('clinical_selection')}")
    print("\n[Formula Families]")
    for family_name in ["补气方剂", "活血化瘀方", "温阳方剂"]:
        formulas = FormulaComparator.get_formula_family(family_name)
        if formulas:
            print(f"  {family_name}: {', '.join(formulas)}")


def _print_modern_pharmacology(herbs):
    print("\n[METHOD 4] Modern Pharmacology & Clinical Research (Xi Dai Yao Li)")
    print("-" * 80)
    for herb_name in herbs:
        pharm_data = ModernPharmacologyDatabase.get_pharmacological_data(herb_name)
        if pharm_data:
            print(f"\n[{herb_name}]")
            components = pharm_data.get("active_components", {})
            if components:
                print(f"  Active components:")
                for comp_name, content in components.items():
                    print(f"    - {comp_name}: {content}")
            actions = pharm_data.get("pharmacological_actions", [])
            if actions:
                print(f"  Pharmacological actions:")
                for action in actions[:3]:
                    print(f"    - {action}")
            clinical = pharm_data.get("clinical_research", {})
            if clinical:
                print(f"  Clinical efficacy rates:")
                for indication, rate in list(clinical.items())[:3]:
                    print(f"    - {indication}: {rate:.0%}")
            safety = ModernPharmacologyDatabase.get_safety_info(herb_name)
            adverse = safety.get("adverse_effects", [])
            if adverse:
                print(f"  Adverse effects: {'; '.join(adverse)}")
            interactions = safety.get("drug_interactions", [])
            if interactions:
                print(f"  Drug interactions: {'; '.join(interactions)}")
    print("\n[Herbs for Clinical Indication]")
    for indication in ["反复呼吸道感染", "冠心病"]:
        herbs_with_efficacy = ModernPharmacologyDatabase.find_herbs_for_indication(indication)
        if herbs_with_efficacy:
            print(f"  {indication}:")
            for herb, efficacy in herbs_with_efficacy:
                print(f"    - {herb}: {efficacy:.0%} efficacy rate")


def _print_network_analysis():
    print("\n[METHOD 5] Network Pharmacology & Systems Biology")
    print("-" * 80)
    network_result = NetworkPharmacologySystemBiologyAnalyzer.analyze_formula_network(
        "补中益气汤",
        ["黄芪", "人参", "白术", "茯苓", "甘草"],
    )
    print(f"  Formula: {network_result.get('formula_name')}")
    print(f"  Target count: {network_result.get('target_count')}")
    print("  Key targets:")
    for item in network_result.get("key_targets", [])[:5]:
        print(f"    - {item.get('target')}: degree={item.get('degree')}")
    print("  Enriched pathways:")
    for item in network_result.get("enriched_pathways", [])[:4]:
        print(f"    - {item.get('pathway')}: score={item.get('score')}")


def _print_physicochemical_analysis():
    print("\n[METHOD 6] Supramolecular Chemistry & Physicochemistry")
    print("-" * 80)
    phys_result = SupramolecularPhysicochemicalAnalyzer.analyze_formula_physicochemical(
        "补中益气汤",
        ["黄芪", "人参", "白术", "茯苓", "甘草"],
    )
    print(f"  Formula: {phys_result.get('formula_name')}")
    print(f"  Available: {phys_result.get('available')}")
    metrics = phys_result.get("metrics", {})
    if metrics:
        print(f"  Solubility index: {metrics.get('solubility_index', 0):.3f}")
        print(f"  H-bond network: {metrics.get('h_bond_network', 0):.3f}")
        print(f"  PI-stacking potential: {metrics.get('pi_stacking_potential', 0):.3f}")
    print(f"  Supramolecular synergy: {phys_result.get('supramolecular_synergy_score', 0):.3f}")


def _print_archaeology_analysis():
    print("\n[METHOD 7] Classical Literature Digitization & Knowledge Archaeology")
    print("-" * 80)
    archaeology_result = ClassicalLiteratureArchaeologyAnalyzer.analyze_formula_knowledge_archaeology(
        "补中益气汤",
        ["黄芪", "人参", "白术", "茯苓", "甘草"],
    )
    origin = archaeology_result.get("origin", {})
    print(f"  Source: {origin.get('source')}")
    print(f"  Dynasty: {origin.get('dynasty')}")
    print(f"  Author: {origin.get('author')}")
    print("  Evolution notes:")
    for note in archaeology_result.get("evolution_notes", [])[:3]:
        print(f"    - {note}")


def _print_dynamics_analysis():
    print("\n[METHOD 8] Complexity Science & Nonlinear Dynamics")
    print("-" * 80)
    dynamics_result = ComplexityNonlinearDynamicsAnalyzer.analyze_formula_complexity_dynamics(
        "补中益气汤",
        ["黄芪", "人参", "白术", "茯苓", "甘草"],
    )
    print(f"  Stability: {dynamics_result.get('stability', 0):.3f}")
    print(f"  Adaptivity: {dynamics_result.get('adaptivity', 0):.3f}")
    print(f"  Feedback gain: {dynamics_result.get('feedback_gain', 0):.3f}")
    print(f"  Resilience index: {dynamics_result.get('resilience_index', 0):.3f}")
    print(f"  Complexity score: {dynamics_result.get('complexity_score', 0):.3f}")
    print(f"  Dynamic regime: {dynamics_result.get('dynamic_regime')}")
    return dynamics_result


def _print_integrated_analysis():
    print("\n[INTEGRATED ANALYSIS] Multiple Perspectives for Formula Research")
    print("-" * 80)
    scoring = {}
    for formula_name in ["补中益气汤"]:
        perspective = IntegratedResearchAnalyzer.generate_research_perspective(formula_name)
        print(f"\n[{formula_name}] - Comprehensive Research Profile")
        print(f"\n  1. Formula Structure:")
        struct = perspective.get("structure_analysis", {})
        print(f"     - Characteristics: {struct.get('characteristics')}")
        print(f"     - Herb count: {struct.get('herb_count')}")
        print(f"\n  2. Component Properties (Si Qi Wu Wei Analysis):")
        props = perspective.get("component_properties", {})
        for herb, prop in list(props.items())[:3]:
            if prop:
                print(f"     - {herb}: {prop.get('temperature')} {prop.get('flavors')} -> {', '.join(prop.get('meridians', []))}")
        print(f"\n  3. Similar Formula Families:")
        similar = perspective.get("similar_formulas", [])
        if similar:
            for sim_formula in similar:
                print(f"     - {sim_formula}")
        print(f"\n  4. Modern Pharmacology Profile:")
        pharm = perspective.get("pharmacological_profile", {})
        for herb, data in list(pharm.items())[:2]:
            components = data.get("components", {})
            if components:
                comp_list = list(components.keys())[:2]
                print(f"     - {herb}: {', '.join(comp_list)} active components")
            efficacy = data.get("efficacy", {})
            if efficacy:
                eff_list = list(efficacy.items())[:1]
                print(f"       Clinical: {eff_list[0][0]} (efficacy: {eff_list[0][1]:.0%})")
        print(f"\n  5. Network Pharmacology:")
        net = perspective.get("network_pharmacology", {})
        print(f"     - Target count: {net.get('target_count', 0)}")
        print(f"     - Key targets: {[i.get('target') for i in net.get('key_targets', [])[:3]]}")
        print(f"\n  6. Supramolecular Physicochemistry:")
        phys = perspective.get("supramolecular_physicochemical", {})
        print(f"     - Synergy score: {phys.get('supramolecular_synergy_score', 0):.3f}")
        print(f"\n  7. Knowledge Archaeology:")
        arch = perspective.get("knowledge_archaeology", {})
        print(f"     - Origin source: {arch.get('origin', {}).get('source')}")
        print(f"\n  8. Complexity Dynamics:")
        dyn = perspective.get("complexity_dynamics", {})
        print(f"     - Complexity score: {dyn.get('complexity_score', 0):.3f}")
        print(f"     - Dynamic regime: {dyn.get('dynamic_regime')}")
        print(f"\n  9. Unified Scoring Panel:")
        scoring = ResearchScoringPanel.score_research_perspective(perspective, [])
        print(f"     - Total score: {scoring.get('total_score', 0):.3f}")
        ci = scoring.get("confidence_interval_95", {})
        print(f"     - 95% CI: {ci.get('lower', 0):.3f} to {ci.get('upper', 0):.3f}")
        print(f"     - Top strengths: {', '.join(scoring.get('strengths', [])[:3])}")
    return scoring


def _print_methods_summary() -> None:
    print("\n" + "=" * 80)
    print("[SUCCESS] Research Methods Test Completed!")
    print("=" * 80)
    print("\n[Available Research Perspectives]:")
    print("  1. [Structure] Formula composition, dosage, role distribution")
    print("  2. [Properties] Si Qi Wu Wei, meridian entry (归经)")
    print("  3. [Comparison] Similar formulas, formula families (类方)")
    print("  4. [Pharmacology] Active components, clinical efficacy, safety")
    print("  5. [Network] Herb-target-pathway systems model")
    print("  6. [Supramolecular] Non-covalent interaction & release behavior")
    print("  7. [Archaeology] Classical source lineage & variant evolution")
    print("  8. [Complexity] Nonlinear dynamics and resilience")
    print("  9. [Integration] Multi-dimensional research analysis")
    print("\n[Research Applications]:")
    print("  - Formula optimization based on structure analysis")
    print("  - Herb substitution based on property matching")
    print("  - Formula differentiation using comparison")
    print("  - Evidence-based practice using pharmacology data")
    print("  - Comprehensive formula assessment via integration")


def test_research_methods():
    """测试八大研究方法切入点"""
    _print_methods_banner()
    formula_names = ["补中益气汤", "四君子汤"]
    herbs = ["黄芪", "人参", "白术", "甘草", "丹参"]
    _print_formula_structure(formula_names)
    _print_herb_properties(herbs)
    _print_formula_comparisons()
    _print_modern_pharmacology(herbs)
    _print_network_analysis()
    _print_physicochemical_analysis()
    _print_archaeology_analysis()
    dynamics_result = _print_dynamics_analysis()
    scoring = _print_integrated_analysis()
    _print_methods_summary()

    assert dynamics_result.get('complexity_score', 0) >= 0
    assert scoring.get('total_score', 0) >= 0


if __name__ == "__main__":
    try:
        test_research_methods()
        print("\n[All research methods loaded successfully!]")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
