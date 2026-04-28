import logging
logging.basicConfig(level=logging.DEBUG)
import traceback
from unittest.mock import patch
from src.orchestration.research_runtime_service import ResearchRuntimeService

config = {"phases": ["observe"], "database": {"type": "postgresql"}}

def run():
    try:
        r = ResearchRuntimeService(orchestrator_config=config)
        print("SF:", r._storage_factory)
    except Exception:
        traceback.print_exc()

run()
