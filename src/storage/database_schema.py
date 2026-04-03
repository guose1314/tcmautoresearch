"""
数据库模式定义 - PostgreSQL初始化脚本
中医古籍全自动研究系统 - 持久化存储
"""

# SQL Schema for PostgreSQL initialization
DATABASE_INIT_SCRIPT = """
-- 为中医古籍研究系统启用必要的扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "hstore";

-- ==================== 核心表定义 ====================

-- 1. 文档表 - 记录处理的源文件信息
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_file VARCHAR(500) NOT NULL UNIQUE,
    processing_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    objective VARCHAR(255),
    raw_text_size INTEGER DEFAULT 0,
    entities_extracted_count INTEGER DEFAULT 0,
    process_status VARCHAR(50) DEFAULT 'pending' CHECK (
        process_status IN ('pending', 'processing', 'completed', 'failed')
    ),
    quality_score FLOAT DEFAULT 0.0 CHECK (quality_score >= 0 AND quality_score <= 1),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_status ON documents(process_status);
CREATE INDEX idx_documents_timestamp ON documents(processing_timestamp DESC);
CREATE INDEX idx_documents_file ON documents(source_file);

-- 2. 实体表 - 核心实体数据
CREATE TYPE entity_type_enum AS ENUM ('formula', 'herb', 'syndrome', 'efficacy', 'property', 'taste', 'meridian', 'other');

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    type entity_type_enum NOT NULL,
    confidence FLOAT DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    position INTEGER NOT NULL,
    length INTEGER NOT NULL,
    alternative_names TEXT[] DEFAULT ARRAY[]::TEXT[],
    description TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_entities_document ON entities(document_id);
CREATE INDEX idx_entities_type ON entities(type);
CREATE INDEX idx_entities_name ON entities(name);
CREATE INDEX idx_entities_confidence ON entities(confidence DESC);

-- 3. 关系类型定义表
CREATE TABLE IF NOT EXISTS relationship_types (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relationship_name VARCHAR(100) NOT NULL UNIQUE,
    relationship_type VARCHAR(50) NOT NULL,
    description TEXT,
    category VARCHAR(50) CHECK (category IN ('composition', 'therapeutic', 'property', 'similarity', 'other')),
    confidence_baseline FLOAT DEFAULT 0.7 CHECK (confidence_baseline >= 0 AND confidence_baseline <= 1),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rel_types_name ON relationship_types(relationship_name);

-- 预置常见关系类型
INSERT INTO relationship_types (relationship_name, relationship_type, description, category, confidence_baseline)
VALUES
    ('君', 'SOVEREIGN', '方剂中的主要成分，发挥主要治疗作用', 'composition', 0.95),
    ('臣', 'MINISTER', '方剂中的辅助成分，协助君药发挥作用', 'composition', 0.92),
    ('佐', 'ASSISTANT', '方剂中的配合成分，起支持或对抗作用', 'composition', 0.90),
    ('使', 'ENVOY', '方剂中的调和成分，促进诸药的协调', 'composition', 0.88),
    ('治疗', 'TREATS', '中药/方剂治疗特定症候', 'therapeutic', 0.75),
    ('功效', 'HAS_EFFICACY', '中药具有特定功效', 'property', 0.82),
    ('类似', 'SIMILAR_TO', '两个方剂或中药成分相似', 'similarity', 0.70),
    ('包含', 'CONTAINS', '方剂包含特定中药', 'composition', 0.99)
ON CONFLICT (relationship_name) DO NOTHING;

-- 4. 实体关系表 - 记录实体间的所有关系
CREATE TABLE IF NOT EXISTS entity_relationships (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type_id UUID NOT NULL REFERENCES relationship_types(id),
    confidence FLOAT DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
    created_by_module VARCHAR(100),
    evidence TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_rel_source ON entity_relationships(source_entity_id);
CREATE INDEX idx_rel_target ON entity_relationships(target_entity_id);
CREATE INDEX idx_rel_type ON entity_relationships(relationship_type_id);
CREATE INDEX idx_rel_module ON entity_relationships(created_by_module);

-- 5. 处理统计表
CREATE TABLE IF NOT EXISTS processing_statistics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    formulas_count INTEGER DEFAULT 0,
    herbs_count INTEGER DEFAULT 0,
    syndromes_count INTEGER DEFAULT 0,
    efficacies_count INTEGER DEFAULT 0,
    relationships_count INTEGER DEFAULT 0,
    graph_nodes_count INTEGER DEFAULT 0,
    graph_edges_count INTEGER DEFAULT 0,
    graph_density FLOAT DEFAULT 0.0,
    connected_components INTEGER DEFAULT 0,
    source_modules TEXT[] DEFAULT ARRAY[]::TEXT[],
    processing_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stats_document ON processing_statistics(document_id);

-- 6. 质量指标表
CREATE TABLE IF NOT EXISTS quality_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    confidence_score FLOAT DEFAULT 0.0,
    completeness FLOAT DEFAULT 0.0,
    entity_precision FLOAT DEFAULT 0.0,
    relationship_precision FLOAT DEFAULT 0.0,
    graph_quality_score FLOAT DEFAULT 0.0,
    evaluation_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    evaluator VARCHAR(100),
    assessment_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_quality_document ON quality_metrics(document_id);
CREATE INDEX idx_quality_score ON quality_metrics(confidence_score DESC);

-- 7. 研究分析表（存储复杂的分析结果）
CREATE TABLE IF NOT EXISTS research_analyses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    research_perspectives JSONB DEFAULT '{}'::JSONB,
    formula_comparisons JSONB DEFAULT '{}'::JSONB,
    herb_properties_analysis JSONB DEFAULT '{}'::JSONB,
    pharmacology_integration JSONB DEFAULT '{}'::JSONB,
    network_pharmacology JSONB DEFAULT '{}'::JSONB,
    supramolecular_physicochemistry JSONB DEFAULT '{}'::JSONB,
    knowledge_archaeology JSONB DEFAULT '{}'::JSONB,
    complexity_dynamics JSONB DEFAULT '{}'::JSONB,
    research_scoring_panel JSONB DEFAULT '{}'::JSONB,
    summary_analysis JSONB DEFAULT '{}'::JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analysis_document ON research_analyses(document_id);

-- 8. 处理日志表 - 审计追踪
CREATE TABLE IF NOT EXISTS processing_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    module_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) CHECK (status IN ('start', 'success', 'failure', 'warning')),
    message TEXT,
    error_details TEXT,
    execution_time_ms INTEGER DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_logs_document ON processing_logs(document_id);
CREATE INDEX idx_logs_module ON processing_logs(module_name);
CREATE INDEX idx_logs_status ON processing_logs(status);
CREATE INDEX idx_logs_timestamp ON processing_logs(timestamp DESC);

-- ==================== 视图定义 ====================

-- 1. 文档处理摘要视图
CREATE OR REPLACE VIEW v_document_summary AS
SELECT
    d.id,
    d.source_file,
    d.process_status,
    d.quality_score,
    ps.formulas_count,
    ps.herbs_count,
    ps.syndromes_count,
    ps.relationships_count,
    ps.graph_density,
    COUNT(DISTINCT e.id) as unique_entities,
    d.processing_timestamp
FROM documents d
LEFT JOIN processing_statistics ps ON d.id = ps.document_id
LEFT JOIN entities e ON d.id = e.document_id
GROUP BY d.id, ps.id;

-- 2. 关系分析视图
CREATE OR REPLACE VIEW v_relationship_analysis AS
SELECT
    rt.relationship_name,
    rt.relationship_type,
    COUNT(er.id) as count,
    AVG(er.confidence) as avg_confidence,
    MIN(er.confidence) as min_confidence,
    MAX(er.confidence) as max_confidence
FROM relationship_types rt
LEFT JOIN entity_relationships er ON rt.id = er.relationship_type_id
GROUP BY rt.id, rt.relationship_name, rt.relationship_type;

-- 3. 实体类型分布视图
CREATE OR REPLACE VIEW v_entity_distribution AS
SELECT
    document_id,
    type as entity_type,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence
FROM entities
GROUP BY document_id, type;

-- ==================== 钩子和触发器 ====================

-- 1. 自动更新 documents 的 updated_at
CREATE OR REPLACE FUNCTION update_documents_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_documents_timestamp
BEFORE UPDATE ON documents
FOR EACH ROW
EXECUTE FUNCTION update_documents_timestamp();

-- 2. 自动更新 entities 的 updated_at
CREATE OR REPLACE FUNCTION update_entities_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_entities_timestamp
BEFORE UPDATE ON entities
FOR EACH ROW
EXECUTE FUNCTION update_entities_timestamp();

-- 3. 自动更新 research_analyses 的 updated_at
CREATE OR REPLACE FUNCTION update_analyses_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_analyses_timestamp
BEFORE UPDATE ON research_analyses
FOR EACH ROW
EXECUTE FUNCTION update_analyses_timestamp();
"""

# ==================== 导出脚本 ====================

def get_init_script() -> str:
    """返回数据库初始化脚本"""
    return DATABASE_INIT_SCRIPT


def get_cleanup_script() -> str:
    """返回数据清理脚本（开发用）"""
    return """
    -- 清理所有数据（保留表结构）
    DELETE FROM processing_logs;
    DELETE FROM research_analyses;
    DELETE FROM quality_metrics;
    DELETE FROM processing_statistics;
    DELETE FROM entity_relationships;
    DELETE FROM entities;
    DELETE FROM documents;
    
    -- 重置序列
    -- ALTER TABLE documents ALTER COLUMN id RESTART;
    """


def get_backup_script() -> str:
    """返回备份脚本"""
    return """
    -- 备份关键数据到JSON
    COPY (
        SELECT row_to_json(d.*) FROM documents d
    ) TO STDOUT;
    
    COPY (
        SELECT row_to_json(e.*) FROM entities e
    ) TO STDOUT;
    """
