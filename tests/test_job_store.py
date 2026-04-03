"""Persistent job store safety tests."""

import json
import os
import tempfile
import unittest

from web_console.job_store import PersistentJobStore


class TestPersistentJobStore(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.storage_dir = os.path.join(self.tempdir.name, "jobs")
        self.store = PersistentJobStore(self.storage_dir)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_save_and_load_valid_job_payload(self):
        payload = {
            "job": {
                "job_id": "valid-job_001",
                "topic": "测试任务",
                "status": "completed",
            },
            "events": [],
        }

        self.store.save_job(payload)

        stored = self.store.get_job_payload("valid-job_001")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored["job"]["topic"], "测试任务")

    def test_invalid_job_ids_are_rejected_without_touching_parent_paths(self):
        outside_path = os.path.join(self.tempdir.name, "escape.json")
        with open(outside_path, "w", encoding="utf-8") as handle:
            json.dump({"job": {"job_id": "escape"}, "events": []}, handle)

        self.assertIsNone(self.store.get_job_payload("../escape"))
        self.assertFalse(self.store.delete_job("../escape"))
        with self.assertRaises(ValueError):
            self.store.save_job({"job": {"job_id": "../escape"}, "events": []})

        self.assertTrue(os.path.exists(outside_path))
        self.assertEqual(os.listdir(self.storage_dir), [])


if __name__ == "__main__":
    unittest.main()
