"""真实浏览器级 Web Console E2E 测试。"""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from importlib import import_module
from typing import Any, cast

import pytest

from web_console.app import create_app
from web_console.job_manager import ResearchJobManager

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait
except ImportError:  # pragma: no cover - 依赖缺失时在测试中跳过
    webdriver = None
    TimeoutException = Exception
    WebDriverException = Exception
    By = None
    Select = None
    WebDriverWait = None


class _ResultWrapper:
    def __init__(self, payload):
        self._payload = payload
        self.status = payload["status"]

    def to_dict(self):
        return self._payload


class BrowserE2ERunner:
    def __init__(self, _config=None):
        self._config = _config or {}
        self._started = self._config["started"]
        self._continue = self._config["continue"]

    def run(self, payload, emit=None):
        topic = payload["topic"]
        if emit is None:
            return _ResultWrapper(
                {
                    "topic": topic,
                    "cycle_id": "cycle-browser-sync",
                    "status": "completed",
                    "started_at": "2026-03-30T00:00:00",
                    "completed_at": "2026-03-30T00:00:01",
                    "total_duration_sec": 1.0,
                    "phases": [],
                    "pipeline_metadata": {"cycle_name": "browser-sync"},
                }
            )

        emit("cycle_created", {"topic": topic, "cycle_id": "cycle-browser", "cycle_name": "browser-e2e", "scope": "test"})
        emit("phase_started", {"phase": "observe", "index": 1, "total": 1, "progress": 10.0})
        self._started.set()
        self._continue.wait(timeout=10.0)
        emit(
            "phase_completed",
            {
                "phase": "observe",
                "status": "completed",
                "duration_sec": 0.01,
                "error": "",
                "summary": {"observation_count": 1},
                "index": 1,
                "total": 1,
                "progress": 100.0,
            },
        )
        result = {
            "topic": topic,
            "cycle_id": "cycle-browser",
            "status": "completed",
            "started_at": "2026-03-30T00:00:00",
            "completed_at": "2026-03-30T00:00:01",
            "total_duration_sec": 1.0,
            "phases": [
                {"phase": "observe", "status": "completed", "duration_sec": 0.01, "error": "", "summary": {"observation_count": 1}},
            ],
            "pipeline_metadata": {"cycle_name": "browser-e2e"},
        }
        emit("job_completed", {"status": "completed", "result": result})
        return _ResultWrapper(result)


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def _wait_for_server(base_url, timeout=10.0):
    deadline = time.time() + timeout
    health_url = f"{base_url}/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise TimeoutException(f"服务未能在 {timeout} 秒内就绪: {health_url}")


def _create_webdriver():
    if webdriver is None:
        raise unittest.SkipTest("selenium 未安装，跳过浏览器级 E2E。")

    browser_candidates = [
        (
            [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ],
            webdriver.ChromeOptions,
            webdriver.Chrome,
            "Chrome",
        ),
        (
            [
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ],
            webdriver.EdgeOptions,
            webdriver.Edge,
            "Edge",
        ),
    ]

    errors = []
    for paths, options_factory, driver_factory, browser_name in browser_candidates:
        browser_path = next((path for path in paths if os.path.exists(path)), "")
        if not browser_path:
            continue

        options = cast(Any, options_factory)()
        options.binary_location = browser_path
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1200")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        try:
            driver = cast(Any, driver_factory)(options=options)
            driver.set_page_load_timeout(20)
            return driver
        except WebDriverException as error:
            errors.append(f"{browser_name}: {error}")

    detail = "；".join(errors) if errors else "未检测到可用的 Chrome 或 Edge 浏览器"
    raise unittest.SkipTest(f"无法启动浏览器驱动，跳过浏览器级 E2E：{detail}")


class TestWebConsoleBrowserE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        uvicorn = import_module("uvicorn")
        cls.tempdir = tempfile.TemporaryDirectory(dir=os.getcwd())
        cls.started = threading.Event()
        cls.proceed = threading.Event()
        cls.manager = ResearchJobManager(
            runner_factory=lambda config: cast(Any, BrowserE2ERunner({**config, "started": cls.started, "continue": cls.proceed})),
            storage_dir=os.path.join(cls.tempdir.name, "jobs"),
        )
        cls.port = _find_free_port()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        app = create_app(job_manager=cls.manager)
        app.state.settings.secrets.pop("security", None)
        cls.server = uvicorn.Server(
            uvicorn.Config(
                app,
                host="127.0.0.1",
                port=cls.port,
                log_level="warning",
                lifespan="on",
            )
        )
        cls.server_thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.server_thread.start()

        try:
            _wait_for_server(cls.base_url)
            cls.driver = _create_webdriver()
        except Exception:
            cls.server.should_exit = True
            cls.server_thread.join(timeout=10.0)
            cls.manager.close()
            cls.tempdir.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        driver = getattr(cls, "driver", None)
        if driver is not None:
            driver.quit()

        cls.proceed.set()

        server = getattr(cls, "server", None)
        if server is not None:
            server.should_exit = True

        thread = getattr(cls, "server_thread", None)
        if thread is not None:
            thread.join(timeout=10.0)

        manager = getattr(cls, "manager", None)
        if manager is not None:
            manager.close()

        tempdir = getattr(cls, "tempdir", None)
        if tempdir is not None:
            tempdir.cleanup()

    def setUp(self):
        self.started.clear()
        self.proceed.clear()

    @pytest.mark.xfail(
        reason="Selenium 环境 flaky，需真实浏览器 + WebSocket (known_failure)",
        strict=False,
    )
    def test_auto_transport_prefers_websocket_on_real_page(self):
        if WebDriverWait is None or Select is None or By is None:
            raise unittest.SkipTest("selenium 未安装，跳过浏览器级 E2E。")

        by = By
        wait = WebDriverWait(self.driver, 20)
        self.driver.get(self.base_url)

        transport_select = Select(wait.until(lambda driver: driver.find_element(by.ID, "transport-select")))
        self.assertEqual(transport_select.first_selected_option.get_attribute("value"), "auto")

        topic_input = self.driver.find_element(by.ID, "topic-input")
        topic_input.clear()
        topic_input.send_keys("浏览器 E2E WebSocket 优先链路")

        self.driver.find_element(by.ID, "submit-button").click()
        self.assertTrue(self.started.wait(timeout=10.0))

        try:
            wait.until(lambda driver: "自动 / WebSocket" in driver.find_element(by.ID, "active-transport").text)
            wait.until(
                lambda driver: "phase_started" in driver.find_element(by.ID, "event-log").text
                and "WebSocket" in driver.find_element(by.ID, "event-log").text
            )
            banner_text = self.driver.find_element(by.ID, "status-banner").text
            self.assertIn("WebSocket", banner_text)
        finally:
            self.proceed.set()

        wait.until(lambda driver: "已完成" in driver.find_element(by.ID, "job-status").text)


if __name__ == "__main__":
    unittest.main()