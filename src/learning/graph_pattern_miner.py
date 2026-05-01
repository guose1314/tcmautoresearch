"""图谱增量挖掘守护进程 (Graph Pattern Mining Daemon)

此模块利用 APScheduler 实现后台定时挖掘，负责拉取 Neo4j 数据库中的新增节点与关系。
核心逻辑是通过 Cypher 查询提取频繁子图模式：
例如 `(Herb)-[CONTAINS]-(Prescription)-[TREATS]-(Symptom)` 的高频模式，并将这些有价值的共现关系送往下游转化成“学习经验（Learning Insights）”。
"""

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler = None  # 仅在装有 apscheduler 时启用真实调度

from src.storage.neo4j_driver import Neo4jDriver

logger = logging.getLogger(__name__)


class GraphPatternMiningDaemon:
    """增量图网络挖掘守护进程。

    使用定时任务定期从 Neo4j 拉取最新提取的知识图谱数据，提取模式提鲜。
    """

    def __init__(
        self,
        neo4j_driver: Optional[Neo4jDriver] = None,
        state_dir: str = "data/miner_state",
        self_learning_engine=None,
        allow_mock_patterns: bool = False,
    ):
        # 默认尝试连本地或接受 mock_driver
        self.neo4j_driver = neo4j_driver
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "last_mining_state.json"
        self.self_learning_engine = self_learning_engine
        self.allow_mock_patterns = bool(allow_mock_patterns)

        self.scheduler = BackgroundScheduler() if BackgroundScheduler else None
        self._load_state()

    def _load_state(self):
        """加载上一次挖掘的游标或时间戳。"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_mining_time = data.get(
                        "last_mining_time", "2000-01-01T00:00:00"
                    )
            except Exception as e:
                logger.warning(f"无法读取挖掘状态文件 {e}，将执行全量挖掘。")
                self.last_mining_time = "2000-01-01T00:00:00"
        else:
            self.last_mining_time = "2000-01-01T00:00:00"

    def _save_state(self, current_time: str):
        """保存当前挖掘游标。"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"last_mining_time": current_time}, f, ensure_ascii=False, indent=2
                )
            self.last_mining_time = current_time
        except Exception as e:
            logger.error(f"保存挖掘状态失败: {e}")

    def execute_incremental_mining(self) -> List[Dict[str, Any]]:
        """执行图聚合与增量挖掘。"""
        logger.info(f"开始图谱增量挖掘，上次挖掘时间: {self.last_mining_time}")
        current_time = datetime.now(timezone.utc).isoformat()

        # 1. 查询高频共现关系，如 (Herb)-[CONTAINS]-(Prescription)-[TREATS]-(Symptom)
        # 此处使用一个简化版的 Cypher 查询演示对增量数据的大致聚合
        cypher_query = """
        MATCH (h:Herb)<-[c:CONTAINS]-(p:Prescription)-[t:TREATS]->(s:Symptom)
        WHERE coalesce(
            p.created_at,
            p.outbox_processed_at,
            p.projected_at,
            p.updated_at,
            "2000-01-01T00:00:00"
        ) >= $last_time
        WITH h.name AS herb, p.name AS prescription, s.name AS symptom, 
             count(p) AS occurrence_freq
        WHERE occurrence_freq >= 2
        RETURN herb, prescription, symptom, occurrence_freq
        ORDER BY occurrence_freq DESC
        LIMIT 50
        """

        extracted_patterns = []
        try:
            session_opener = self._resolve_session_opener()
            if session_opener is None:
                if not self.allow_mock_patterns:
                    logger.warning(
                        "未注入有效的 Neo4j 驱动实例，跳过图模式挖掘；"
                        "测试需要模拟输出时请显式设置 allow_mock_patterns=True。"
                    )
                    return []
                logger.warning("allow_mock_patterns=True，返回显式测试模拟图模式。")
                patterns = [self._mock_pattern()]
                self._dispatch_to_learning_engine(patterns)
                self._save_state(current_time)
                return patterns

            with session_opener() as session:
                result = session.run(cypher_query, last_time=self.last_mining_time)
                for record in result:
                    pattern = {
                        "herb": self._record_field(record, "herb"),
                        "prescription": self._record_field(record, "prescription"),
                        "symptom": self._record_field(record, "symptom"),
                        "occurrence_freq": self._record_field(
                            record, "occurrence_freq"
                        ),
                    }
                    extracted_patterns.append(pattern)

            logger.info(
                f"图模式挖掘成功：发现 {len(extracted_patterns)} 条高频共现关系。"
            )
            if extracted_patterns:
                self._dispatch_to_learning_engine(extracted_patterns)

            # 记录本次成功挖掘时间，当作下次采样的起点
            self._save_state(current_time)
            return extracted_patterns
        except Exception as e:
            logger.error(f"图数据库挖掘发生异常: {e}")
            return []

    def mine_learning_insights(
        self, cycle_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """执行挖掘并转换为 LearningInsight repository 可写入的 payload。"""
        patterns = self.execute_incremental_mining()
        return self.patterns_to_learning_insights(patterns, cycle_id=cycle_id)

    def patterns_to_learning_insights(
        self,
        patterns: List[Dict[str, Any]],
        *,
        cycle_id: Optional[str] = None,
        target_phase: str = "hypothesis",
    ) -> List[Dict[str, Any]]:
        """将图模式输出转换为 LearningInsight 标准字典。"""
        insights: List[Dict[str, Any]] = []
        normalized_cycle_id = str(cycle_id or "graph-mining").strip()
        for idx, pattern in enumerate(patterns or []):
            if not isinstance(pattern, Mapping):
                continue
            description = self._describe_pattern(pattern)
            insight_id = self._build_insight_id(normalized_cycle_id, description, idx)
            insights.append(
                {
                    "insight_id": insight_id,
                    "source": "neo4j_graph_pattern_miner",
                    "target_phase": str(target_phase or "hypothesis"),
                    "insight_type": "prompt_bias",
                    "description": description,
                    "confidence": min(
                        float(
                            pattern.get("confidence")
                            or pattern.get("occurrence_freq")
                            or 0
                        )
                        / (1.0 if pattern.get("confidence") else 100.0),
                        1.0,
                    ),
                    "evidence_refs_json": [dict(pattern)],
                    "status": "active",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
        return insights

    def _dispatch_to_learning_engine(self, patterns: List[Dict[str, Any]]):
        """将挖掘到的共现规律送往 SelfLearningEngine，持久化为 Learning Insights。"""
        # 在此将模式转换为具有医学逻辑的实体总结，以便提供给动态 Few-Shot
        if not self.self_learning_engine:
            logger.info("No SelfLearningEngine configured, skipping pattern dispatch.")
            return

        for idx, pattern in enumerate(patterns):
            # 将图谱共现实体转换为可读的 pattern description
            desc = (
                f"配伍规律: 【{pattern.get('prescription', '某方')}】常包含【{pattern.get('herb', '某药')}】"
                f"用于治疗【{pattern.get('symptom', '某些症状')}】"
                f"(置信度: 挖掘频次 {pattern.get('occurrence_freq', 0)})"
            )

            insight = {
                "pattern_id": f"graph_insight_{idx}",
                "description": desc,
                "confidence": min(
                    pattern.get("occurrence_freq", 0) / 100.0, 1.0
                ),  # 简单的频次归一化作置信度
                "frequency": pattern.get("occurrence_freq", 0),
                "metadata": pattern,
            }
            logger.debug(f"[Graph Pattern] 频繁规律发现: {desc}")
            self.self_learning_engine.register_graph_insight(insight)

    def _resolve_session_opener(self):
        if self.neo4j_driver is None:
            return None
        inner = getattr(self.neo4j_driver, "driver", None)
        if inner is not None and hasattr(inner, "session"):
            return inner.session
        if hasattr(self.neo4j_driver, "session"):
            return self.neo4j_driver.session
        return None

    @staticmethod
    def _record_field(record: Any, key: str) -> Any:
        if hasattr(record, "get"):
            try:
                return record.get(key)
            except Exception:
                pass
        try:
            return record[key]
        except Exception:
            return None

    @staticmethod
    def _mock_pattern() -> Dict[str, Any]:
        return {
            "herb": "连翘",
            "prescription": "银翘散",
            "symptom": "温热表证",
            "occurrence_freq": 16,
            "mock": True,
        }

    @staticmethod
    def _describe_pattern(pattern: Mapping[str, Any]) -> str:
        return (
            f"配伍规律: 【{pattern.get('prescription', '某方')}】常包含"
            f"【{pattern.get('herb', '某药')}】用于治疗"
            f"【{pattern.get('symptom', '某些症状')}】。"
        )

    @staticmethod
    def _build_insight_id(cycle_id: str, description: str, index: int) -> str:
        seed = f"neo4j_graph_pattern_miner|{cycle_id}|{description}|{index}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
        return f"neo4j_graph_pattern_miner:{cycle_id}:{digest}"[:128]

    def start_daemon(self, interval_hours: int = 24):
        """启动后台定时任务。"""
        if not self.scheduler:
            logger.warning(
                "未安装 apscheduler，无法启动定时挖掘任务守护进程 (请执行 `pip install apscheduler`)。"
            )
            return

        self.scheduler.add_job(
            self.execute_incremental_mining,
            "interval",
            hours=interval_hours,
            id="graph_pattern_mining_job",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(f"图谱增量挖掘守护进程已启动，执行周期: {interval_hours} 小时/次。")

    def stop_daemon(self):
        """停止后台守护进程。"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("图谱增量挖掘守护进程已停止。")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    daemon = GraphPatternMiningDaemon()
    # 模拟触发一次挖掘（立即执行）
    daemon.execute_incremental_mining()
