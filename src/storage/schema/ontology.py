from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """核心节点标签 (Node Labels) 规范"""
    LITERATURE = "Literature"
    PRESCRIPTION = "Prescription"
    HERB = "Herb"
    SYMPTOM = "Symptom"
    PATHOGENESIS = "Pathogenesis"


class RelationType(str, Enum):
    """核心边关系 (Relationship Types) 规范"""
    APPEARS_IN = "APPEARS_IN"
    CONTAINS = "CONTAINS"
    TREATS = "TREATS"
    MODULATES = "MODULATES"
    REFERENCES = "REFERENCES"


# ==========================================
# 节点模型 (Node Models)
# ==========================================
class GraphNodeBase(BaseModel):
    """图节点基类"""
    id: str = Field(..., description="节点的唯一标识符符(UUID或经过消歧的标准化名称)")


class LiteratureNode(GraphNodeBase):
    """文献节点
    属性含 title, author, dynasty, chapter
    """
    label: NodeType = Field(default=NodeType.LITERATURE, frozen=True)
    title: str = Field(..., description="文献名称")
    author: Optional[str] = Field(None, description="作者")
    dynasty: Optional[str] = Field(None, description="成书朝代")
    chapter: Optional[str] = Field(None, description="篇章/卷数")


class PrescriptionNode(GraphNodeBase):
    """方剂节点
    属性含 name, alias, source
    """
    label: NodeType = Field(default=NodeType.PRESCRIPTION, frozen=True)
    name: str = Field(..., description="方名")
    alias: Optional[str] = Field(None, description="别名")
    source: Optional[str] = Field(None, description="出处(若文本直接提及的字面出处)")


class HerbNode(GraphNodeBase):
    """中药节点
    属性含 name, nature (四气), flavor (五味)
    """
    label: NodeType = Field(default=NodeType.HERB, frozen=True)
    name: str = Field(..., description="药名")
    nature: Optional[str] = Field(None, description="四气(寒、热、温、凉、平)")
    flavor: Optional[str] = Field(None, description="五味(酸、苦、甘、辛、咸)")


class SymptomNode(GraphNodeBase):
    """证候/症状节点
    属性含 name, description
    """
    label: NodeType = Field(default=NodeType.SYMPTOM, frozen=True)
    name: str = Field(..., description="证候或症状名称")
    description: Optional[str] = Field(None, description="描述或表征")


class PathogenesisNode(GraphNodeBase):
    """病机节点
    属性含 name, mechanism
    """
    label: NodeType = Field(default=NodeType.PATHOGENESIS, frozen=True)
    name: str = Field(..., description="指代的病机名称")
    mechanism: Optional[str] = Field(None, description="病理机制描述")


# ==========================================
# 边关系模型 (Relationship Models)
# ==========================================
class GraphRelationBase(BaseModel):
    """图边关系基类"""
    source_id: str = Field(..., description="起始节点ID")
    target_id: str = Field(..., description="目标节点ID")


class AppearsInRelation(GraphRelationBase):
    """(Prescription)-[:APPEARS_IN]->(Literature)：出自某文献"""
    type: RelationType = Field(default=RelationType.APPEARS_IN, frozen=True)


class ContainsRelation(GraphRelationBase):
    """(Prescription)-[:CONTAINS {dosage: "..."}]->(Herb)：方剂包含某药味及剂量"""
    type: RelationType = Field(default=RelationType.CONTAINS, frozen=True)
    dosage: Optional[str] = Field(None, description="相关药材的剂量、炮制要求等")


class TreatsRelation(GraphRelationBase):
    """(Prescription)-[:TREATS]->(Symptom)：方剂主治"""
    type: RelationType = Field(default=RelationType.TREATS, frozen=True)


class ModulatesRelation(GraphRelationBase):
    """(Herb)-[:MODULATES]->(Pathogenesis)：中药调节/针对某病机"""
    type: RelationType = Field(default=RelationType.MODULATES, frozen=True)


class ReferencesRelation(GraphRelationBase):
    """(Literature)-[:REFERENCES {confidence: 0.9}]->(Literature)：文献间的沿袭与引用"""
    type: RelationType = Field(default=RelationType.REFERENCES, frozen=True)
    confidence: float = Field(default=0.9, description="引用推测的置信度(0.0-1.0)")
