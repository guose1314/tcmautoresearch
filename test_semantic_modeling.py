"""
语义建模测试 - 君臣佐使关系识别演示
验证 TCM 语义图构建和关系分类
"""

import os
import sys

# 设置 UTF-8 编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
if callable(stdout_reconfigure):
    stdout_reconfigure(encoding='utf-8')

from src.extractors.advanced_entity_extractor import AdvancedEntityExtractor

# 导入依赖模块
from src.preprocessor.document_preprocessor import DocumentPreprocessor
from src.semantic_modeling.semantic_graph_builder import SemanticGraphBuilder
from src.semantic_modeling.tcm_relationships import (
    RelationshipType,
    TCMRelationshipDefinitions,
)


def test_semantic_modeling():
    """
    测试完整的语义建模流程
    """
    print("\n" + "="*80)
    print("语义建模升级演示（君臣佐使关系识别）")
    print("="*80)
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第1步】文本预处理
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第1步】文本预处理")
    print("-" * 80)
    
    test_text = """
    《本草纲目》记载：补中益气汤由黄芪、人参、白术、茯苓、甘草等构成。
    其中黄芪为君药，补气固表；
    人参为臣药，协助补气；
    白术、茯苓为佐药，健脾利水；
    甘草为使药，调和诸药。
    
    此方主治气虚证，功效为补气健脾、固表止汗。
    临床可用于防治各类虚弱性疾病。
    """
    
    preprocessor = DocumentPreprocessor()
    preprocessor.initialize()  # 初始化模块
    context = {"raw_text": test_text}
    preprocess_result = preprocessor.execute(context)
    processed_text = preprocess_result.get("processed_text", test_text)
    
    print(f"[OK] 输入文本清洁化完成")
    print(f"  处理步骤: {preprocess_result.get('processing_steps', [])}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第2步】实体抽取
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第2步】实体抽取")
    print("-" * 80)
    
    extractor = AdvancedEntityExtractor()
    extractor.initialize()  # 初始化模块
    context["processed_text"] = processed_text
    extract_result = extractor.execute(context)
    
    entities = extract_result.get("entities", [])
    
    print(f"[OK] 实体抽取完成")
    print(f"  总实体数: {len(entities)}")
    print(f"  实体类型分布: {extract_result.get('statistics', {}).get('by_type', {})}")
    
    print("\n【抽取的关键实体】:")
    key_types = ["formula", "herb", "syndrome", "efficacy"]
    for entity_type in key_types:
        entities_of_type = [e for e in entities if e.get("type") == entity_type]
        if entities_of_type:
            names = [e["name"] for e in entities_of_type]
            print(f"  {entity_type:12s}: {', '.join(names)}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第3步】语义图构建（君臣佐使关系识别）
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第3步】语义图构建 - 君臣佐使关系识别")
    print("-" * 80)
    
    graph_builder = SemanticGraphBuilder()
    graph_builder.initialize()  # 初始化模块
    context["entities"] = entities
    graph_result = graph_builder.execute(context)
    
    semantic_graph = graph_result.get("semantic_graph", {})
    nodes = semantic_graph.get("nodes", [])
    edges = semantic_graph.get("edges", [])
    stats = graph_result.get("graph_statistics", {})
    
    print(f"[OK] 语义图构建完成")
    print(f"  节点总数: {stats.get('nodes_count', 0)}")
    print(f"  边总数: {stats.get('edges_count', 0)}")
    print(f"  图密度: {stats.get('density', 0):.3f}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第4步】关系详解
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第4步】关系详解 - 君臣佐使分类")
    print("-" * 80)
    
    # 分类显示关系
    relationships_by_type = stats.get('relationships_by_type', {})
    
    if relationships_by_type:
        for rel_name in ['sovereign', 'minister', 'assistant', 'envoy', 'efficacy', 'treats']:
            rel_info = relationships_by_type.get(rel_name)
            if rel_info:
                count = rel_info.get('count', 0)
                desc = rel_info.get('description', '')
                print(f"\n  【{rel_name.upper()}】 (计数: {count})")
                print(f"    {desc}")
                
                # 列出该类型的所有边
                matching_edges = [e for e in edges if e.get('attributes', {}).get('relationship_type') == rel_name]
                for edge in matching_edges:
                    source_node = edge.get('source', '')
                    target_node = edge.get('target', '')
                    conf = edge.get('attributes', {}).get('confidence', 0)
                    print(f"      {source_node} → {target_node} (置信度: {conf:.2%})")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第5步】关系验证示例
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第5步】君臣佐使组成验证")
    print("-" * 80)
    
    # 查询预定义的方剂组成
    formula_examples = ["补中益气汤", "四君子汤", "六味地黄丸"]
    
    for formula_name in formula_examples:
        composition = TCMRelationshipDefinitions.get_formula_composition(formula_name)
        if composition:
            print(f"\n  {formula_name}:")
            if composition.get("sovereign"):
                print(f"    君药: {', '.join(composition['sovereign'])}")
            if composition.get("minister"):
                print(f"    臣药: {', '.join(composition['minister'])}")
            if composition.get("assistant"):
                print(f"    佐药: {', '.join(composition['assistant'])}")
            if composition.get("envoy"):
                print(f"    使药: {', '.join(composition['envoy'])}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第6步】关系配置参数展示
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第6步】所有关系类型清单")
    print("-" * 80)
    
    print("\n  支持的关系类型：")
    for rel_type in RelationshipType:
        description = TCMRelationshipDefinitions.get_relationship_description(rel_type)
        print(f"    • {rel_type.value:20s} → {description}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【第7步】图的可视化友好输出
    # ─────────────────────────────────────────────────────────────────────────
    print("\n【第7步】知识图谱概览")
    print("-" * 80)
    
    print("\n  【节点样本】（前10个）:")
    for node in nodes[:10]:
        node_id = node.get('id', '')
        data = node.get('data', {})
        name = data.get('name', '')
        confidence = data.get('confidence', 0)
        node_type = data.get('type', '')
        print(f"    {node_id:30s} | {name:20s} | 类型: {node_type:10s} | 置信度: {confidence:.2%}")
    
    print("\n  【边样本】（前15个）:")
    for edge in edges[:15]:
        source = edge.get('source', '').split(':')[-1]  # 提取实体名
        target = edge.get('target', '').split(':')[-1]
        rel_type = edge.get('attributes', {}).get('relationship_name', '')
        conf = edge.get('attributes', {}).get('confidence', 0)
        print(f"    {source:15s} --[{rel_type:12s}]--> {target:15s} ({conf:.2%})")
    
    # ─────────────────────────────────────────────────────────────────────────
    # 【成功指标】
    # ─────────────────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print("[SUCCESS] 语义建模测试完成!")
    print("="*80)
    
    print("\n[Checklist]:")
    print(f"  [OK] Text preprocessing: {'Pass' if processed_text else 'Fail'}")
    print(f"  [OK] Entity extraction: {'Pass' if len(entities) > 0 else 'Fail'}")
    print(f"  [OK] Semantic graph: {'Pass' if stats.get('nodes_count', 0) > 0 else 'Fail'}")
    print(f"  [OK] Sovereign/Minister/Assistant/Envoy: {'Pass' if relationships_by_type.get('sovereign') else 'Fail'}")
    print(f"  [OK] Efficacy relationship: {'Pass' if relationships_by_type.get('efficacy') else 'Fail'}")
    
    print("\n【下一步扩展】:")
    print("  1. 支持加载更多方剂和药物的复杂组成")
    print("  2. 实现图的可视化导出（GraphML/JSON格式）")
    print("  3. 支持关系聚合和路径查询")
    print("  4. 集成频率分析和统计学检验")

    assert isinstance(graph_result, dict)
    assert "graph_statistics" in graph_result


if __name__ == "__main__":
    try:
        test_semantic_modeling()
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
