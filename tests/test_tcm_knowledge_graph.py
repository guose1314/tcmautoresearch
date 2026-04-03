"""tests/test_tcm_knowledge_graph.py — TCMKnowledgeGraph 单元测试。"""

import sqlite3
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from src.knowledge.tcm_knowledge_graph import (
    ENTITY_TYPES,
    FOUR_LEVELS,
    IKnowledgeGraph,
    KnowledgeGap,
    TCMKnowledgeGraph,
    _SQLiteBackend,
)

# =========================================================================
# fixtures
# =========================================================================

@pytest.fixture
def kg() -> TCMKnowledgeGraph:
    """纯内存图谱（不加载预置方剂）。"""
    return TCMKnowledgeGraph(db_path=None, preload_formulas=False)


@pytest.fixture
def kg_preloaded() -> TCMKnowledgeGraph:
    """预加载方剂组成的内存图谱。"""
    return TCMKnowledgeGraph(db_path=None, preload_formulas=True)


@pytest.fixture
def tmp_db(tmp_path: Path):
    """返回临时 SQLite 路径。"""
    return tmp_path / "test_kg.db"


# =========================================================================
# 1. 接口与基本 CRUD
# =========================================================================

class TestInterfaceCompliance:
    def test_implements_interface(self, kg: TCMKnowledgeGraph):
        assert isinstance(kg, IKnowledgeGraph)

    def test_add_entity(self, kg: TCMKnowledgeGraph):
        kg.add_entity({"name": "四君子汤", "type": "formula"})
        assert kg.entity_count == 1
        assert "四君子汤" in kg.entities_by_type("formula")

    def test_add_entity_with_metadata(self, kg: TCMKnowledgeGraph):
        kg.add_entity({"name": "人参", "type": "herb", "property": "温"})
        node = kg._graph.nodes["人参"]
        assert node["property"] == "温"

    def test_add_relation(self, kg: TCMKnowledgeGraph):
        kg.add_entity({"name": "A", "type": "formula"})
        kg.add_entity({"name": "B", "type": "syndrome"})
        kg.add_relation("A", "treats", "B")
        assert kg.relation_count == 1
        assert "B" in kg.neighbors("A", "treats")

    def test_add_relation_auto_creates_nodes(self, kg: TCMKnowledgeGraph):
        kg.add_relation("X", "rel", "Y")
        assert kg.entity_count == 2
        assert kg._graph.nodes["X"]["type"] == "generic"

    def test_relation_with_metadata(self, kg: TCMKnowledgeGraph):
        kg.add_relation("A", "treats", "B", {"confidence": 0.9})
        edges = list(kg._graph.edges("A", data=True))
        assert edges[0][2]["confidence"] == 0.9


# =========================================================================
# 2. 预加载方剂组成
# =========================================================================

class TestPreload:
    def test_preloaded_formulas_exist(self, kg_preloaded: TCMKnowledgeGraph):
        formulas = kg_preloaded.entities_by_type("formula")
        assert "四君子汤" in formulas
        assert "补中益气汤" in formulas

    def test_preloaded_herbs_exist(self, kg_preloaded: TCMKnowledgeGraph):
        herbs = kg_preloaded.entities_by_type("herb")
        assert "人参" in herbs
        assert "黄芪" in herbs

    def test_preloaded_efficacy_exist(self, kg_preloaded: TCMKnowledgeGraph):
        effs = kg_preloaded.entities_by_type("efficacy")
        assert "补气" in effs
        assert "活血" in effs

    def test_sovereign_relation(self, kg_preloaded: TCMKnowledgeGraph):
        nbrs = kg_preloaded.neighbors("四君子汤", "sovereign")
        assert "人参" in nbrs

    def test_formula_has_multiple_roles(self, kg_preloaded: TCMKnowledgeGraph):
        roles_found = set()
        for _, _, d in kg_preloaded._graph.out_edges("四君子汤", data=True):
            roles_found.add(d.get("rel_type"))
        assert roles_found >= {"sovereign", "minister", "assistant", "envoy"}


# =========================================================================
# 3. 路径查询
# =========================================================================

class TestQueryPath:
    def test_direct_path(self, kg: TCMKnowledgeGraph):
        kg.add_relation("A", "treats", "B")
        kg.add_relation("B", "associated_target", "C")
        paths = kg.query_path("A", "C")
        assert len(paths) >= 1
        assert paths[0] == ["A", "B", "C"]

    def test_no_path(self, kg: TCMKnowledgeGraph):
        kg.add_entity({"name": "X", "type": "formula"})
        kg.add_entity({"name": "Y", "type": "target"})
        paths = kg.query_path("X", "Y")
        assert paths == []

    def test_nonexistent_node(self, kg: TCMKnowledgeGraph):
        assert kg.query_path("不存在", "也不存在") == []

    def test_multi_hop_path(self, kg: TCMKnowledgeGraph):
        kg.add_relation("F1", "treats", "S1")
        kg.add_relation("S1", "associated_target", "T1")
        kg.add_relation("T1", "participates_in", "P1")
        paths = kg.query_path("F1", "P1")
        assert any(len(p) == 4 for p in paths)  # 4 nodes in path


# =========================================================================
# 4. 子图提取
# =========================================================================

class TestGetSubgraph:
    def test_subgraph_contains_center(self, kg: TCMKnowledgeGraph):
        kg.add_relation("A", "rel", "B")
        sub = kg.get_subgraph("A", depth=1)
        assert "A" in sub.nodes

    def test_depth_limit(self, kg: TCMKnowledgeGraph):
        kg.add_relation("A", "r", "B")
        kg.add_relation("B", "r", "C")
        kg.add_relation("C", "r", "D")
        sub = kg.get_subgraph("A", depth=1)
        assert "A" in sub and "B" in sub
        assert "D" not in sub  # too far

    def test_nonexistent_entity(self, kg: TCMKnowledgeGraph):
        sub = kg.get_subgraph("不存在")
        assert len(sub.nodes) == 0


# =========================================================================
# 5. 知识缺口识别 (find_gaps)
# =========================================================================

class TestFindGaps:
    def test_orphan_entity(self, kg: TCMKnowledgeGraph):
        kg.add_entity({"name": "lone", "type": "herb"})
        gaps = kg.find_gaps()
        orphans = [g for g in gaps if g.gap_type == "orphan_entity"]
        assert any(g.entity == "lone" for g in orphans)

    def test_missing_downstream_formula(self, kg: TCMKnowledgeGraph):
        """方剂无 syndrome 下游 → missing_downstream。"""
        kg.add_entity({"name": "方A", "type": "formula"})
        kg.add_relation("方A", "sovereign", "药X")
        gaps = kg.find_gaps()
        missing = [g for g in gaps if g.gap_type == "missing_downstream"
                   and g.entity == "方A"]
        assert len(missing) == 1
        assert missing[0].severity == "high"

    def test_missing_downstream_syndrome(self, kg: TCMKnowledgeGraph):
        """证候无 target 下游。"""
        kg.add_entity({"name": "证A", "type": "syndrome"})
        gaps = kg.find_gaps()
        missing = [g for g in gaps if g.gap_type == "missing_downstream"
                   and g.entity == "证A"]
        assert len(missing) == 1

    def test_missing_downstream_target(self, kg: TCMKnowledgeGraph):
        """靶点无 pathway 下游。"""
        kg.add_entity({"name": "靶A", "type": "target"})
        gaps = kg.find_gaps()
        missing = [g for g in gaps if g.gap_type == "missing_downstream"
                   and g.entity == "靶A"]
        assert len(missing) == 1

    def test_incomplete_composition(self, kg: TCMKnowledgeGraph):
        """方剂只有 sovereign 缺少其他角色。"""
        kg.add_entity({"name": "方B", "type": "formula"})
        kg.add_relation("方B", "sovereign", "药A")
        gaps = kg.find_gaps()
        inc = [g for g in gaps if g.gap_type == "incomplete_composition"
               and g.entity == "方B"]
        assert len(inc) == 1
        assert "minister" in inc[0].description

    def test_three_gap_types_detectable(self, kg: TCMKnowledgeGraph):
        """验收标准: 至少 3 类缺口类型。"""
        kg.add_entity({"name": "孤立", "type": "herb"})
        kg.add_entity({"name": "方无下游", "type": "formula"})
        kg.add_relation("方无下游", "sovereign", "某草")
        gaps = kg.find_gaps()
        gap_types = {g.gap_type for g in gaps}
        assert len(gap_types) >= 3, f"仅识别到 {gap_types}"

    def test_no_gaps_for_complete_chain(self, kg: TCMKnowledgeGraph):
        """完整四级链不会报 missing_downstream。"""
        kg.add_entity({"name": "F", "type": "formula"})
        kg.add_entity({"name": "S", "type": "syndrome"})
        kg.add_entity({"name": "T", "type": "target"})
        kg.add_entity({"name": "P", "type": "pathway"})
        kg.add_relation("F", "sovereign", "药1")
        kg.add_relation("F", "minister", "药2")
        kg.add_relation("F", "assistant", "药3")
        kg.add_relation("F", "envoy", "药4")
        kg.add_relation("F", "treats", "S")
        kg.add_relation("S", "associated_target", "T")
        kg.add_relation("T", "participates_in", "P")
        gaps = kg.find_gaps()
        formula_gaps = [g for g in gaps if g.entity == "F"]
        assert all(g.gap_type != "missing_downstream" for g in formula_gaps)
        assert all(g.gap_type != "incomplete_composition" for g in formula_gaps)


# =========================================================================
# 6. SQLite 持久化
# =========================================================================

class TestSQLitePersistence:
    def test_persist_entity(self, tmp_db: Path):
        kg = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        kg.add_entity({"name": "A", "type": "herb"})
        kg.close()

        kg2 = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        assert "A" in kg2.entities_by_type("herb")
        kg2.close()

    def test_persist_relation(self, tmp_db: Path):
        kg = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        kg.add_relation("A", "treats", "B")
        kg.close()

        kg2 = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        assert kg2.relation_count == 1
        assert "B" in kg2.neighbors("A", "treats")
        kg2.close()

    def test_save_full_sync(self, tmp_db: Path):
        kg = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=True)
        kg.save()
        assert kg._db.entity_count() > 0
        assert kg._db.relation_count() > 0
        kg.close()

    def test_reopen_after_preload(self, tmp_db: Path):
        kg = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=True)
        kg.save()
        count1 = kg.entity_count
        kg.close()

        kg2 = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        assert kg2.entity_count == count1
        kg2.close()


# =========================================================================
# 7. 批量导入 & 验收标准: 1000+ 实体 / 3000+ 关系
# =========================================================================

class TestBulkAndScale:
    def test_bulk_add_entities(self, kg: TCMKnowledgeGraph):
        ents = [{"name": f"E{i}", "type": "target"} for i in range(100)]
        added = kg.bulk_add_entities(ents)
        assert added == 100
        assert kg.entity_count == 100

    def test_bulk_add_relations(self, kg: TCMKnowledgeGraph):
        rels = [(f"S{i}", "rel", f"D{i}", None) for i in range(200)]
        added = kg.bulk_add_relations(rels)
        assert added == 200
        assert kg.relation_count == 200

    def test_scale_1000_entities_3000_relations(self, kg: TCMKnowledgeGraph):
        """验收标准: 可容纳 1000+ 实体 & 3000+ 关系。"""
        ents = [{"name": f"node_{i}", "type": FOUR_LEVELS[i % 4]} for i in range(1200)]
        kg.bulk_add_entities(ents)

        rels = [
            (f"node_{i}", "link", f"node_{(i + 1) % 1200}", None)
            for i in range(3500)
        ]
        kg.bulk_add_relations(rels)

        assert kg.entity_count >= 1000
        assert kg.relation_count >= 3000

    def test_scale_with_sqlite(self, tmp_db: Path):
        """持久化也能处理大规模数据。"""
        kg = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        ents = [{"name": f"e{i}", "type": "target"} for i in range(1000)]
        kg.bulk_add_entities(ents)
        rels = [(f"e{i}", "r", f"e{(i+1)%1000}", None) for i in range(3000)]
        kg.bulk_add_relations(rels)
        kg.close()

        kg2 = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        assert kg2.entity_count >= 1000
        assert kg2.relation_count >= 3000
        kg2.close()


# =========================================================================
# 8. 边界 & 辅助
# =========================================================================

class TestEdgeCases:
    def test_neighbors_nonexistent(self, kg: TCMKnowledgeGraph):
        assert kg.neighbors("非实体") == []

    def test_entities_by_type_empty(self, kg: TCMKnowledgeGraph):
        assert kg.entities_by_type("pathway") == []

    def test_close_idempotent(self, tmp_db: Path):
        kg = TCMKnowledgeGraph(db_path=tmp_db, preload_formulas=False)
        kg.close()
        kg.close()  # 不应抛异常

    def test_save_noop_without_db(self, kg: TCMKnowledgeGraph):
        kg.add_entity({"name": "A", "type": "herb"})
        kg.save()  # 不应抛异常

    def test_knowledge_gap_dataclass(self):
        gap = KnowledgeGap(
            gap_type="orphan_entity",
            entity="x",
            entity_type="herb",
            description="test",
            severity="low",
        )
        assert gap.gap_type == "orphan_entity"
        assert gap.severity == "low"
