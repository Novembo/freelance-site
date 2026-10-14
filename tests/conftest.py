"""Configuration des tests : base temporaire et variables d'environnement
fixées AVANT l'import de l'application (database.py lit DB_PATH à l'import)."""

import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="site-tests-")
os.environ["DB_PATH"] = str(Path(_tmp) / "test.db")
os.environ["ADMIN_TOKEN"] = "jeton-de-test"
os.environ["ALLOWED_ORIGINS"] = "https://obed.example"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture()
def client():
    return TestClient(main.app)


@pytest.fixture()
def admin():
    return {"X-Admin-Token": "jeton-de-test"}


@pytest.fixture()
def make_order(client):
    def _make(plan="API REST au forfait", name="Awa", email="awa@example.com"):
        r = client.post("/api/orders", json={"plan_name": plan, "client_name": name, "client_email": email})
        assert r.status_code == 200, r.text
        return r.json()
    return _make


@pytest.fixture()
def kkiapay_ok(monkeypatch):
    """Simule une transaction Kkiapay réussie du montant de l'acompte du forfait API REST."""
    monkeypatch.setattr(main, "_verify_with_kkiapay", lambda tx: (True, 52500, "SUCCESS"))
