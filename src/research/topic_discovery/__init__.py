"""topic_discovery 子域 — 研究选题（文献研究法环节①）。

将"研究方向 seed → 3-5 个候选课题"落为可审计、可序列化、可被
ResearchPipeline 在 observe 之前调用的独立子阶段。

公开 API:
  - TopicProposal / TOPIC_PROPOSAL_CONTRACT_VERSION
  - propose_topics

实现细节请见 contract.py / topic_discovery_service.py。
"""

from src.research.topic_discovery.contract import (
    TOPIC_PROPOSAL_CONTRACT_VERSION,
    TOPIC_PROPOSAL_MAX,
    TOPIC_PROPOSAL_MIN,
    TopicProposal,
    TopicSourceCandidate,
    build_topic_discovery_summary,
    normalize_topic_proposals,
)
from src.research.topic_discovery.topic_discovery_service import (
    TopicDiscoveryService,
    propose_topics,
)

__all__ = [
    "TOPIC_PROPOSAL_CONTRACT_VERSION",
    "TOPIC_PROPOSAL_MIN",
    "TOPIC_PROPOSAL_MAX",
    "TopicProposal",
    "TopicSourceCandidate",
    "TopicDiscoveryService",
    "build_topic_discovery_summary",
    "normalize_topic_proposals",
    "propose_topics",
]
