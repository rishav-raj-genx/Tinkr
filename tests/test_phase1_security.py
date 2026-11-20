"""Phase 1 Automated Security, Identity & Resilience Regression Test Suite.

Covers:
1. Input validation rejecting malformed and oversized payloads (>5 MB, base64 pcm, Pydantic bounds).
2. Session isolation preventing Insecure Direct Object References (anti-IDOR).
3. Portfolio Demo Sandbox protecting Google Workspace tools for unauthenticated visitors.
4. Owner authentication lifecycle (constant-time verification, session upgrade/downgrade).
5. SQL tool security (read-only SQLite URI, injection blocks, mutation blocks, row caps, opcode limit).
6. Sliding-window rate limiter enforcing HTTP 429 and Retry-After.
7. Defense-in-depth security headers and sanitized global 500 error responses.
"""

import base64
import json
import sqlite3
from unittest.mock import patch

import pytest

from api_server import app, execute_tool
from config import config
from security import rate_limiter
from setup_db import setup_database
from sql_tool import execute_sql_query


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Ensure rate limit buckets are cleared before and after each test."""
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture
def client():
    """Provides a fresh Flask test client."""
    app.config["TESTING"] = True
    return app.test_client()


def test_pydantic_pinned_in_requirements():
    """Verify pydantic is pinned with an exact version in requirements.txt."""
    req_path = config.BASE_DIR / "requirements.txt"
    assert req_path.exists()
    content = req_path.read_text(encoding="utf-8")
    assert "pydantic==" in content


# ═══════════════════════════════════════════════════════════════
# 1. test_input_validation_rejects_malformed_and_oversized_payloads
# ═══════════════════════════════════════════════════════════════


def test_input_validation_rejects_malformed_and_oversized_payloads(client):
    """Verify invalid chat lengths, malformed audio base64, and >5 MB payloads return 400/413/422."""
    # 1. >5 MB payload returns 413 Payload Too Large
    oversized = "x" * (5 * 1024 * 1024 + 1024)
    res_413 = client.post("/api/chat_stream", data=oversized, content_type="application/json")
    assert res_413.status_code == 413
    assert "Payload Too Large" in res_413.get_json()["error"]

    # 2. Malformed JSON / wrong Content-Type returns 400 Bad Request
    res_400_ct = client.post("/api/chat_stream", data="plain text", content_type="text/plain")
    assert res_400_ct.status_code == 400
    res_400_json = client.post("/api/chat_stream", data="{bad-json", content_type="application/json")
    assert res_400_json.status_code == 400

    # 3. ChatStreamRequest length validation: empty string & >2000 chars return 422
    res_empty = client.post("/api/chat_stream", json={"text": ""})
    assert res_empty.status_code == 422
    assert "details" in res_empty.get_json()

    res_long = client.post("/api/chat_stream", json={"text": "a" * 2001})
    assert res_long.status_code == 422

    # Forbidden extra fields return 422
    res_extra = client.post("/api/chat_stream", json={"text": "Hello", "injected": "payload"})
    assert res_extra.status_code == 422

    # 4. AnalyzeAudioRequest base64 validation
    # Malformed base64 chars
    res_b64_invalid = client.post("/api/analyze_audio", json={"audio_base64": "!!!not_b64!!!"})
    assert res_b64_invalid.status_code == 422

    # Odd byte length (not int16 PCM)
    odd_bytes = b"12345678901234567"  # 17 bytes
    odd_b64 = base64.b64encode(odd_bytes).decode("ascii")
    res_b64_odd = client.post("/api/analyze_audio", json={"audio_base64": odd_b64})
    assert res_b64_odd.status_code == 422
    assert "even length" in str(res_b64_odd.get_json())

    # String too short (< 16 chars)
    res_b64_short = client.post("/api/analyze_audio", json={"audio_base64": "AAAA"})
    assert res_b64_short.status_code == 422

    # 5. SaveMentalStateRequest invalid enum state returns 422
    res_enum = client.post(
        "/api/save_mental_state",
        json={"user_id": "test_user", "predicted_state": "hyperactive"}
    )
    assert res_enum.status_code == 422

    # 6. HistoryQueryRequest bounds (<1 or >50) return 422
    res_hist_low = client.post("/api/get_mental_state_history", json={"user_id": "u", "limit": 0})
    assert res_hist_low.status_code == 422
    res_hist_high = client.post("/api/get_mental_state_history", json={"user_id": "u", "limit": 51})
    assert res_hist_high.status_code == 422


# ═══════════════════════════════════════════════════════════════
# 2. test_session_isolation_prevents_idor
# ═══════════════════════════════════════════════════════════════


def test_session_isolation_prevents_idor():
    """Verify Client A's data is isolated to its session sid and Client B cannot access it."""
    client_a = app.test_client()
    client_b = app.test_client()

    # Client A creates mental state record
    res_save = client_a.post(
        "/api/save_mental_state",
        json={
            "user_id": "client_a_user",
            "predicted_state": "stressed",
            "user_confirmed": True,
            "mean_zcr": 0.08,
            "rms_variance": 0.003,
            "voice_energy_level": "high",
            "suggestions": ["Take a break"]
        }
    )
    assert res_save.status_code == 200
    state_id = res_save.get_json()["state_id"]

    # Client A attaches an emotional chat to this state
    res_chat = client_a.post(
        "/api/save_emotional_chat",
        json={
            "user_id": "client_a_user",
            "emotional_state_id": state_id,
            "user_message": "I feel very overwhelmed",
            "assistant_message": "I hear you, take it one step at a time."
        }
    )
    assert res_chat.status_code == 200

    # Client A queries own history -> finds record
    history_a = client_a.post(
        "/api/get_mental_state_history",
        json={"user_id": "client_a_user", "limit": 10}
    ).get_json()
    assert history_a["success"] is True
    assert len(history_a["history"]) >= 1
    assert history_a["history"][0]["predicted_state"] == "stressed"

    # Client B queries history attempting IDOR by passing client_a_user
    history_b = client_b.post(
        "/api/get_mental_state_history",
        json={"user_id": "client_a_user", "limit": 10}
    ).get_json()
    assert history_b["success"] is True
    assert len(history_b["history"]) == 0  # Client B cannot view Client A's session data

    # Client B queries emotional chat history passing client_a_user
    chats_b = client_b.post(
        "/api/get_emotional_chat_history",
        json={"user_id": "client_a_user", "limit": 10}
    ).get_json()
    assert chats_b["success"] is True
    assert len(chats_b["history"]) == 0  # Client B receives zero records


# ═══════════════════════════════════════════════════════════════
# 3. test_portfolio_demo_sandbox_protects_workspace
# ═══════════════════════════════════════════════════════════════


def test_portfolio_demo_sandbox_protects_workspace(client):
    """Guest session calling Calendar/Gmail/Tasks receives [DEMO SANDBOX] output without real API calls."""
    workspace_tool_calls = [
        ("check_availability", {"time_min": "2026-11-17T09:00:00Z", "time_max": "2026-11-17T17:00:00Z"}),
        ("book_meeting", {"summary": "Security Sync", "start_time": "2026-11-17T10:00:00Z", "end_time": "2026-11-17T10:30:00Z"}),
        ("set_reminder", {"task": "Review PR", "remind_time": "2026-11-17T14:00:00Z"}),
        ("add_task", {"title": "Hardening QA Check"}),
        ("list_tasks", {}),
        ("check_unread_emails", {}),
        ("draft_email", {"to": "visitor@example.com", "subject": "Test", "body": "Sandbox body"}),
        ("send_email", {"to": "visitor@example.com", "subject": "Test", "body": "Sandbox body"}),
    ]

    for tool_name, args in workspace_tool_calls:
        # Execute in sandbox mode (guest)
        result = execute_tool(tool_name, args, is_live_owner=False)
        assert "[DEMO SANDBOX]" in result, f"Tool {tool_name} failed sandbox isolation"

    # Non-workspace tools (e.g. search_company_db, query_web_search) must not be simulated
    non_workspace = execute_tool("search_company_db", {"query": "SELECT name FROM customers LIMIT 1"}, is_live_owner=False)
    assert "[DEMO SANDBOX]" not in non_workspace


# ═══════════════════════════════════════════════════════════════
# 4. test_owner_auth_lifecycle
# ═══════════════════════════════════════════════════════════════


def test_owner_auth_lifecycle(client):
    """Test wrong key returns 401; valid key returns 200 and upgrades session; logout downgrades to guest."""
    with patch.object(config, "OWNER_ACCESS_KEY", "super-secret-pass-2026"):
        # 1. Initial state is guest
        session_res = client.get("/api/session").get_json()
        assert session_res["role"] == "guest"
        assert session_res["workspace_mode"] == "sandbox"

        # 2. Wrong key returns 401
        wrong_res = client.post("/api/auth/owner", json={"access_key": "wrong_password"})
        assert wrong_res.status_code == 401
        assert "Invalid" in str(wrong_res.get_json())

        # 3. Valid key returns 200 and upgrades to owner
        valid_res = client.post("/api/auth/owner", json={"access_key": "super-secret-pass-2026"})
        assert valid_res.status_code == 200
        assert valid_res.get_json()["role"] == "owner"

        upgraded_session = client.get("/api/session").get_json()
        assert upgraded_session["role"] == "owner"

        # 4. Logout downgrades back to guest and rotates sid
        logout_res = client.post("/api/auth/logout")
        assert logout_res.status_code == 200
        assert logout_res.get_json()["role"] == "guest"

        downgraded_session = client.get("/api/session").get_json()
        assert downgraded_session["role"] == "guest"
        assert downgraded_session["workspace_mode"] == "sandbox"


# ═══════════════════════════════════════════════════════════════
# 5. test_sql_tool_blocks_injection_and_mutations
# ═══════════════════════════════════════════════════════════════


def test_sql_tool_blocks_injection_and_mutations():
    """Verify sql_tool rejects stacked queries, comments, DDL/DML mutations, and caps rows."""
    blocked_attempts = [
        "SELECT 1; DROP TABLE employees",
        "PRAGMA table_info(employees)",
        "ATTACH DATABASE '/tmp/hacked.db' AS evil",
        "UPDATE employees SET name='hacked'",
        "DELETE FROM customers",
        "INSERT INTO customers (name, region) VALUES ('a', 'b')",
        "SELECT * FROM customers -- inline comment",
        "SELECT /* block comment */ * FROM customers",
    ]

    for malicious_query in blocked_attempts:
        raw_res = execute_sql_query(malicious_query)
        parsed = json.loads(raw_res)
        assert "error" in parsed
        assert "Only SELECT queries are allowed" in parsed["error"]

    # Legitimate SELECT query succeeds
    valid_res = execute_sql_query("SELECT id, name, region FROM customers LIMIT 3")
    parsed_valid = json.loads(valid_res)
    assert isinstance(parsed_valid, list)
    assert len(parsed_valid) <= 3


def test_sql_max_row_cap_and_opcode_limit(tmp_path, monkeypatch):
    """Verify row cap (100) and opcode limit abortion."""
    temp_db = tmp_path / "security_db.db"
    monkeypatch.setattr(config, "DB_PATH", temp_db)
    setup_database()

    # Seed 120 rows
    conn = sqlite3.connect(temp_db)
    conn.executemany(
        "INSERT INTO customers (name, region) VALUES (?, ?)",
        [(f"Customer_{i}", "Global") for i in range(120)]
    )
    conn.commit()
    conn.close()

    # Query all -> capped to 100
    rows = json.loads(execute_sql_query("SELECT * FROM customers"))
    assert len(rows) == 100

    # Opcode runaway abort
    runaway = (
        "SELECT count(*) FROM ("
        "WITH RECURSIVE cnt(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM cnt) "
        "SELECT x FROM cnt"
        ")"
    )
    opcode_res = json.loads(execute_sql_query(runaway))
    assert "error" in opcode_res
    assert "opcode limit exceeded" in opcode_res["error"]


# ═══════════════════════════════════════════════════════════════
# 6. test_rate_limiter_enforces_429
# ═══════════════════════════════════════════════════════════════


def test_rate_limiter_enforces_429(client):
    """Sends burst exceeding endpoint limit and verifies HTTP 429 with Retry-After header."""
    # POST /api/auth/owner limit is 5 / 900s
    with patch.object(config, "OWNER_ACCESS_KEY", "prod-key"):
        for _ in range(5):
            res = client.post("/api/auth/owner", json={"access_key": "bad_key"})
            assert res.status_code == 401

        # 6th request triggers 429
        burst_res = client.post("/api/auth/owner", json={"access_key": "bad_key"})
        assert burst_res.status_code == 429
        assert "Retry-After" in burst_res.headers
        data = burst_res.get_json()
        assert "Rate limit exceeded" in data["error"]


# ═══════════════════════════════════════════════════════════════
# 7. test_security_headers_and_sanitized_500
# ═══════════════════════════════════════════════════════════════


def test_security_headers_and_sanitized_500(client, monkeypatch):
    """Confirms security headers on responses and verifies internal exceptions return sanitized 500."""
    # 1. Security Headers
    res = client.get("/")
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "microphone=(self)" in res.headers.get("Permissions-Policy", "")

    csp = res.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "https://fonts.googleapis.com" in csp

    # 2. Simulated Internal Exception Returns Generic 500 without leaking stack trace
    def mock_db_crash(*args, **kwargs):
        raise RuntimeError("CRITICAL_INTERNAL_DB_PASSWORD=SuperSecret123; path=/etc/shadow; table=finance")

    monkeypatch.setattr("api_server.save_emotional_state_db", mock_db_crash)

    crash_res = client.post(
        "/api/save_mental_state",
        json={"user_id": "safe_user", "predicted_state": "calm"}
    )
    assert crash_res.status_code == 500
    data = crash_res.get_json()
    assert data["error"] == "Internal server error"

    # Verify no leaks in response text
    body = crash_res.get_data(as_text=True)
    assert "SuperSecret123" not in body
    assert "/etc/shadow" not in body
    assert "Traceback" not in body
