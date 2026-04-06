# -*- coding: utf-8 -*-
"""登录链路在 cwd 漂移场景下的健壮性测试。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from src.web.app import create_app
from src.web.routes import auth as auth_routes


def _write_secrets(path: Path) -> None:
    path.write_text(
        """
security:
  jwt_secret_key: "unit-test-jwt-secret-from-file"
  management_api_key: "mgmt-key"
  console_auth:
    users:
      - username: "login_user"
        password: "login_pass"
        display_name: "Login User"
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_auth_login_still_works_when_cwd_changes(tmp_path: Path, monkeypatch) -> None:
    fake_project_root = tmp_path / "fake_project"
    fake_project_root.mkdir(parents=True, exist_ok=True)
    _write_secrets(fake_project_root / "secrets.yml")

    monkeypatch.setattr(auth_routes, "_PROJECT_ROOT", fake_project_root)
    monkeypatch.setenv("JWT_SECRET_KEY", "unit-test-jwt-secret")
    auth_routes.reset_user_cache()

    original_cwd = Path.cwd()
    external_cwd = tmp_path / "external_cwd"
    external_cwd.mkdir(parents=True, exist_ok=True)

    try:
        os.chdir(external_cwd)
        client = TestClient(create_app())

        status_resp = client.get("/api/auth/status")
        assert status_resp.status_code == 200
        status_payload = status_resp.json()
        assert status_payload["supports_password_login"] is True
        assert status_payload["supports_api_key_login"] is True

        password_login_resp = client.post(
            "/api/auth/login",
            json={"username": "login_user", "password": "login_pass"},
        )
        assert password_login_resp.status_code == 200
        password_payload = password_login_resp.json()
        assert password_payload["auth_source"] == "password"

        me_resp = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {password_payload['access_token']}"},
        )
        assert me_resp.status_code == 200
        assert me_resp.json()["username"] == "login_user"

        api_key_login_resp = client.post(
            "/api/auth/login",
            json={"api_key": "mgmt-key", "username": "admin"},
        )
        assert api_key_login_resp.status_code == 200
        assert api_key_login_resp.json()["auth_source"] == "api_key"
    finally:
        os.chdir(original_cwd)
        auth_routes.reset_user_cache()
