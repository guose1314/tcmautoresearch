"""图谱增量挖掘守护进程 (Graph Pattern Mining Daemon)

此模块利用 APScheduler 实现后台定时挖掘，负责拉取 Neo4j 数据库中的新增节点与关系。
核心逻辑是通过 Cypher 查询提取频繁子图模式：
例如 `(Herb)-[CONTAINS]-(Prescription)-[TREATS]-(Symptom)` 的高频模式，并将这些有价值的共现关系送往下游转化成“学习经验（Learning Insights）”。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    def __init__(self, neo4j_driver: Optional[Neo4jDriver] = None, state_dir: str = "data/miner_state",
                 self_learning_engine = None):
        # 默认尝试连本地或接受 mock_driver
        self.neo4j_driver = neo4j_driver
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "last_mining_state.json"
        self.self_learning_engine = self_learning_engine
        
        self.scheduler = BackgroundScheduler() if BackgroundScheduler else None
        self._load_state()

    def _load_state(self):
        """加载上一次挖掘的游标或时间戳。"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_mining_time = data.get("last_mining_time", "2000-01-01T00:00:00")
            except Exception as e:
                logger.warning(f"无法读取挖掘状态文件 {e}，将执行全量挖掘。")
                self.last_mining_time = "2000-01-01T00:00:00"
        else:
            self.last_mining_time = "2000-01-01T00:00:00"

    def _save_state(self, current_time: str):
        """保存当前挖掘游标。"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({"last_mining_time": current_time}, f, ensure_ascii=False, indent=2)
            self.last_mining_time = current_time
        except Exception as e:
            logger.error(f"保存挖掘状态失败: {e}")

    def execute_incremental_mining(self) -> List[Dict[str, Any]]:
        """执行图聚合与增量挖掘。"""
        logger.info(f"开始图谱增量挖掘，上次挖掘时间: {self.last_mining_time}")
        current_time = datetime.now().isoformat()
        
        # 1. 查询高频共现关系，如 (Herb)-[CONTAINS]-(Prescription)-[TREATS]-(Symptom)
        # 此处使用一个简化版的 Cypher 查询演示对增量数据的大致聚合
        cypher_query = """
        MATCH (h:Herb)<-[c:CONTAINS]-(p:Prescription)-[t:TREATS]->(s:Symptom)
        // WHERE p.created_at >= $last_time (若图谱包含创建时间，则此处过滤增量)
        WITH h.name AS herb, p.name AS prescription, s.name AS symptom, 
             count(p) AS occurrence_freq
        WHERE occurrence_freq >= 2
        RETURN herb, prescription, symptom, occurrence_freq
        ORDER BY occurrence_freq DESC
        LIMIT 50
        """
        
        extracted_patterns = []
        try:
            if not self.neo4j_driver:
                logger.warning("未注入有效的 Neo4j 驱动实例，模拟挖掘输出...")
                patterns = [{"herb": "连翘", "prescription": "银翘散", "symptom": "温热表证", "occurrence_freq": 16}]
                self._dispatch_to_learning_engine(patterns)
                self._save_state(current_time)
                return patterns

            with self.neo4j_driver.driver.session() as session:
                result = session.run(cypher_query, last_time=self.last_mining_time)
                for record in result:
                    pattern = {
                        "herb": record["herb"],
                        "prescription": record["prescription"],
                        "symptom": record["symptom"],
                        "occurrence_freq": record["occurrence_freq"]
                    }
                    extracted_patterns.append(pattern)
            
            logger.info(f"图模式挖掘成功：发现 {len(extracted_patterns)} 条高频共现关系。")
            if extracted_patterns:
                self._dispatch_to_learning_engine(extracted_patterns)
                
            # 记录本次成功挖掘时间，当作下次采样的起点
            self._save_state(current_time)
            return extracted_patterns
        except Exception as e:
            logger.error(f"图数据库挖掘发生异常: {e}")
            return []

    def _dispatch_to_learning_engine(self, patterns: List[Dict[str, Any]]):
        """将挖掘到的共现规律送往 SelfLearningEngine，持久化为 Learning Insights。"""
        # 在此将模式转换为具有医学逻辑的实体总结，以便提供给动态 Few-Shot
        if not self.self_learning_engine:
            logger.info("No SelfLearningEngine configured, skipping pattern dispatch.")
            return
            
        for idx, pattern in enumerate(patterns):
            # 将图谱共现实体转换为可读的 pattern description
            desc = (f"配伍规律: 【{pattern.get('prescription', '某方')}】常包含【{pattern.get('herb', '某药')}】"
                    f"用于治疗【{pattern.get('symptom', '某些症状')}】"
                    f"(置信度: 挖掘频次 {pattern.get('occurrence_freq', 0)})")
            
            insight = {
                "pattern_id": f"graph_insight_{idx}",
                "description": desc,
                "confidence": min(pattern.get('occurrence_freq', 0) / 100.0, 1.0), # 简单的频次归一化作置信度
                "frequency": pattern.get('occurrence_freq', 0),
                "metadata": pattern
            }
            logger.debug(f"[Graph Pattern] 频繁规律发现: {desc}")
            self.self_learning_engine.register_graph_insight(insight)

    def start_daemon(self, interval_hours: int = 24):
        """启动后台定时任务。"""
        if not self.scheduler:
            logger.warning("未安装 apscheduler，无法启动定时挖掘任务守护进程 (请执行 `pip install apscheduler`)。")
            return
            
        self.scheduler.add_job(
            self.execute_incremental_mining, 
            'interval', 
            hours=interval_hours,
            id='graph_pattern_mining_job',
            replace_existing=True
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
