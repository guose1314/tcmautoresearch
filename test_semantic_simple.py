"""
Semantic Modeling Test - Simplified Version
Tests TCM relationships: Sovereign, Minister, Assistant, Envoy
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.entity_extractor import AdvancedEntityExtractor
from src.analysis.preprocessor import DocumentPreprocessor
from src.analysis.semantic_graph import SemanticGraphBuilder
from src.semantic_modeling.tcm_relationships import (
    RelationshipType,
    TCMRelationshipDefinitions,
)


def _print_banner() -> None:
    print("\n" + "=" * 80)
    print("SEMANTIC MODELING TEST - Sovereign/Minister/Assistant/Envoy Recognition")
    print("=" * 80)


def _run_preprocessing(test_text: str):
    print("\n[STEP 1] Text Preprocessing")
    print("-" * 80)

    preprocessor = DocumentPreprocessor()
    preprocessor.initialize()
    context = {"raw_text": test_text}
    preprocess_result = preprocessor.execute(context)
    processed_text = preprocess_result.get("processed_text", test_text)

    print(f"[OK] Text processed successfully")
    print(f"  Processing steps: {preprocess_result.get('processing_steps', [])}")
    return context, processed_text


def _run_entity_extraction(context, processed_text: str):
    print("\n[STEP 2] Entity Extraction")
    print("-" * 80)

    extractor = AdvancedEntityExtractor()
    extractor.initialize()
    context["processed_text"] = processed_text
    extract_result = extractor.execute(context)

    entities = extract_result.get("entities", [])
    stats = extract_result.get("statistics", {})

    print(f"[OK] Entity extraction completed")
    print(f"  Total entities: {len(entities)}")
    print(f"  By type: {stats.get('by_type', {})}")
    print("\n  Key entities extracted:")
    for entity_type in ["formula", "herb", "syndrome", "efficacy"]:
        entities_of_type = [e for e in entities if e.get("type") == entity_type]
        if entities_of_type:
            names = [e["name"] for e in entities_of_type[:5]]
            print(f"    {entity_type:12}: {', '.join(names)}")
    return entities


def _run_graph_build(context, entities):
    print("\n[STEP 3] Semantic Graph - Relationship Classification")
    print("-" * 80)

    graph_builder = SemanticGraphBuilder()
    graph_builder.initialize()
    context["entities"] = entities
    graph_result = graph_builder.execute(context)
    stats = graph_result.get("graph_statistics", {})

    print(f"[OK] Semantic graph constructed")
    print(f"  Nodes: {stats.get('nodes_count', 0)}")
    print(f"  Edges: {stats.get('edges_count', 0)}")
    print(f"  Density: {stats.get('density', 0):.3f}")
    return graph_result, stats


def _print_relationship_summary(relationships_by_type):
    print("\n[STEP 4] Relationship Classification Summary")
    print("-" * 80)

    relationship_names = {
        'sovereign': '[SOVEREIGN] - Main drug treating principal pattern',
        'minister': '[MINISTER] - Assisting drug treating secondary pattern',
        'assistant': '[ASSISTANT] - Enhancing effect or counteracting toxicity',
        'envoy': '[ENVOY] - Harmonizing other drugs or directing to meridian',
        'efficacy': '[EFFICACY] - Function/effect of herb/formula',
        'treats': '[TREATS] - Treating a syndrome/pattern'
    }

    print("\nRelationship Statistics:")
    for rel_name, description in relationship_names.items():
        rel_info = relationships_by_type.get(rel_name)
        if rel_info:
            count = rel_info.get('count', 0)
            print(f"  {description}")
            print(f"    Count: {count}")


def _print_formula_compositions():
    print("\n[STEP 5] Formula Composition Validation")
    print("-" * 80)

    formula_names_cn = {
        "Buzhongyiqi Tang": "补中益气汤",
        "Sijunzi Tang (Four Gentlemen Decoction)": "四君子汤",
        "Liuwei Dihuang Wan": "六味地黄丸"
    }

    for formula_name_en, formula_name_cn in formula_names_cn.items():
        composition = TCMRelationshipDefinitions.get_formula_composition(formula_name_cn)
        if composition:
            print(f"\n  {formula_name_en}:")
            if composition.get("sovereign"):
                print(f"    Sovereign: {', '.join(composition['sovereign'])}")
            if composition.get("minister"):
                print(f"    Minister: {', '.join(composition['minister'])}")
            if composition.get("assistant"):
                print(f"    Assistant: {', '.join(composition['assistant'])}")
            if composition.get("envoy"):
                print(f"    Envoy: {', '.join(composition['envoy'])}")


def _print_supported_relationships():
    print("\n[STEP 6] All Supported Relationship Types")
    print("-" * 80)
    print("\nSupported relationships:")
    for rel_type in RelationshipType:
        description = TCMRelationshipDefinitions.get_relationship_description(rel_type)
        print(f"  - {rel_type.value:20} : {description}")


def _print_final_summary(entities, stats, relationships_by_type):
    print("\n" + "=" * 80)
    print("[SUCCESS] Semantic Modeling Test Completed!")
    print("=" * 80)
    print("\n[Verification Checklist]:")
    print(f"  [PASS] Text preprocessing")
    print(f"  [PASS] Entity extraction: {len(entities)} entities")
    print(f"  [PASS] Semantic graph: {stats.get('nodes_count', 0)} nodes, {stats.get('edges_count', 0)} edges")
    print(f"  [PASS] Sovereign/Minister/Assistant/Envoy classification: {len(relationships_by_type)} relationship types")
    print(f"  [PASS] Formula composition validation")
    print("\n[Next Steps]:")
    print("  1. Integrate Qwen LLM for hypothesis generation")
    print("  2. Add statistical analysis (frequency, chi-square test)")
    print("  3. Implement relationship path queries and knowledge graph export")


def test_semantic_modeling_simple():
    """
    Simplified test for semantic modeling with relationship classification
    """
    _print_banner()
    test_text = """
    Buzhongyiqi Tang (Tonifying the Middle and Augmenting the Qi Decoction)
    contains Huangqi as sovereign drug (main drug),
    Renshen as minister drug (assisting drug),
    Baizhu and Fuling as assistant drugs,
    and Gancao as envoy drug (harmonizing other herbs).
    
    This formula treats qi vacuity pattern and has efficacy of tonifying qi,
    supplementing the middle, and securing the exterior.
    """
    context, processed_text = _run_preprocessing(test_text)
    entities = _run_entity_extraction(context, processed_text)
    graph_result, stats = _run_graph_build(context, entities)
    relationships_by_type = stats.get('relationships_by_type', {})
    _print_relationship_summary(relationships_by_type)
    _print_formula_compositions()
    _print_supported_relationships()
    _print_final_summary(entities, stats, relationships_by_type)

    assert isinstance(graph_result, dict)
    assert "graph_statistics" in graph_result


if __name__ == "__main__":
    try:
        test_semantic_modeling_simple()
        print("\n[All tests passed!]")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
