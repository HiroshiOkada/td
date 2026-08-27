"""ハイスコア送信のハッシュ検証とソルト計算の回帰テスト。"""

import hashlib
import re
from pathlib import Path

import pytest

import app as app_module

TEMPLATE_PATH = Path(app_module.__file__).resolve().parent / "templates" / "index.html"
NULL_CURRENT_SCRIPT_SALT = "td_secret_salt_2026_0"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "DATABASE", str(tmp_path / "test.db"))
    app_module._cached_salt = None
    app_module.init_db()
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


def client_side_salt():
    """読み込み時の document.currentScript.textContent と同じ本文からソルトを作る。"""
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    matches = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    assert matches, "index.html に script タグがありません"
    clean = re.sub(r"[ \f\n\r\t\v]+", "", matches[-1])
    return "td_secret_salt_2026_" + str(len(clean))


def sha256_hex(score, wave, salt):
    return hashlib.sha256(f"{score}{wave}{salt}".encode("utf-8")).hexdigest()


def test_dynamic_salt_matches_captured_script_and_is_not_length_zero():
    salt = app_module.get_dynamic_salt()
    assert salt == client_side_salt()
    assert salt != NULL_CURRENT_SCRIPT_SALT
    length = int(salt.rsplit("_", 1)[-1])
    assert length > 0


def test_submit_score_accepts_hash_from_captured_script(client):
    score, wave = 1200, 3
    response = client.post(
        "/api/high_scores",
        json={
            "score": score,
            "wave": wave,
            "hash": sha256_hex(score, wave, client_side_salt()),
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data[0]["score"] == score
    assert data[0]["wave"] == wave


def test_submit_score_rejects_null_currentscript_salt(client):
    """ゲームオーバー後に currentScript が null だと使われていたソルトは 400 になる。"""
    score, wave = 1200, 3
    response = client.post(
        "/api/high_scores",
        json={
            "score": score,
            "wave": wave,
            "hash": sha256_hex(score, wave, NULL_CURRENT_SCRIPT_SALT),
        },
    )
    assert response.status_code == 400
    assert "integrity" in response.get_json()["error"].lower()


def test_submit_score_uses_saved_script_text_not_current_script():
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    iife_start = html.index("(() => {")
    submit_at = html.index("async function submitScore")
    load_at = html.index("async function loadHighScores")
    prefix = html[iife_start:submit_at]
    submit_body = html[submit_at:load_at]
    assert "document.currentScript" in prefix
    assert "ownScriptText" in prefix
    assert "document.currentScript" not in submit_body
    assert "ownScriptText" in submit_body
