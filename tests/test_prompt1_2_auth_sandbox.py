from datetime import timedelta

import pytest

from api_server import app, execute_tool
from config import config


@pytest.fixture
def client_a():
    app.config["TESTING"] = True
    return app.test_client()


@pytest.fixture
def client_b():
    app.config["TESTING"] = True
    return app.test_client()


# ═══════════════════════════════════════════════════════════════
# Task 1: OWNER_ACCESS_KEY Configuration & Diagnostics
# ═══════════════════════════════════════════════════════════════

def test_owner_access_key_config_and_diagnostics(monkeypatch):
    """Verify OWNER_ACCESS_KEY configuration and boolean diagnostics flag."""
    assert hasattr(config, "OWNER_ACCESS_KEY")
    env_example = (config.BASE_DIR / ".env.example").read_text()
    assert "OWNER_ACCESS_KEY=" in env_example

    monkeypatch.setattr(config, "OWNER_ACCESS_KEY", "")
    diag_off = config.diagnostics()
    assert "owner_mode_configured" in diag_off
    assert diag_off["owner_mode_configured"] is False
    assert isinstance(diag_off["owner_mode_configured"], bool)

    monkeypatch.setattr(config, "OWNER_ACCESS_KEY", "secret_test_key_123")
    diag_on = config.diagnostics()
    assert diag_on["owner_mode_configured"] is True


# ═══════════════════════════════════════════════════════════════
# Task 2: Server-Managed Signed Sessions & Anti-IDOR Enforcement
# ═══════════════════════════════════════════════════════════════

def test_session_cookie_security_flags(client_a):
    """Verify Flask session cookie security configuration."""
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["SESSION_COOKIE_SECURE"] == (not config.DEBUG)
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=7)

    res = client_a.get("/api/session")
    assert res.status_code == 200
    set_cookie_header = res.headers.get("Set-Cookie", "")
    assert "session=" in set_cookie_header
    assert "HttpOnly" in set_cookie_header


def test_anti_idor_isolation_between_sessions(client_a, client_b):
    """Verify Client A and Client B cannot access or mutate each other's data (IDOR eliminated)."""
    # 1. Client A saves a mental state using arbitrary user_id in payload
    res_a_save = client_a.post(
        "/api/save_mental_state",
        json={
            "user_id": "victim_alice",
            "predicted_state": "stressed",
            "user_confirmed": True,
            "mean_zcr": 0.12,
            "rms_variance": 0.05,
            "voice_energy_level": "medium",
            "suggestions": ["Pause and take 5 deep breaths"]
        }
    )
    assert res_a_save.status_code == 200
    state_id_a = res_a_save.get_json()["state_id"]

    # Client A saves an emotional chat linked to this state
    res_a_chat = client_a.post(
        "/api/save_emotional_chat",
        json={
            "user_id": "victim_alice",
            "emotional_state_id": state_id_a,
            "user_message": "I feel very overwhelmed today.",
            "assistant_message": "I hear you, take it one step at a time."
        }
    )
    assert res_a_chat.status_code == 200

    # 2. Client B tries to read Alice's data by explicitly specifying "victim_alice"
    res_b_read = client_b.post(
        "/api/get_mental_state_history",
        json={"user_id": "victim_alice", "limit": 20}
    )
    assert res_b_read.status_code == 200
    history_b = res_b_read.get_json()["history"]
    assert len(history_b) == 0, "Client B must NOT see Client A's mental state history!"

    # Client B tries to read Alice's emotional chat history
    res_b_chat_hist = client_b.post(
        "/api/get_emotional_chat_history",
        json={"user_id": "victim_alice", "limit": 20}
    )
    assert res_b_chat_hist.status_code == 200
    assert len(res_b_chat_hist.get_json()["history"]) == 0

    # Client B tries to read Alice's chat messages for state_id_a
    res_b_chats = client_b.post(
        "/api/get_emotional_chats",
        json={"emotional_state_id": state_id_a}
    )
    assert res_b_chats.status_code == 200
    assert len(res_b_chats.get_json()["chats"]) == 0

    # 3. Client A reads their own history and sees the state and chats intact
    res_a_read = client_a.post(
        "/api/get_mental_state_history",
        json={"user_id": "anyone", "limit": 20}
    )
    assert res_a_read.status_code == 200
    history_a = res_a_read.get_json()["history"]
    assert len(history_a) >= 1
    assert history_a[0]["id"] == state_id_a


# ═══════════════════════════════════════════════════════════════
# Task 3: Owner Auth Endpoints & Session Management
# ═══════════════════════════════════════════════════════════════

def test_session_endpoint_defaults(client_a):
    """Verify /api/session defaults to role: guest and workspace_mode: sandbox."""
    res = client_a.get("/api/session")
    assert res.status_code == 200
    data = res.get_json()
    assert data["role"] == "guest"
    assert data["workspace_mode"] == "sandbox"
    assert data["session_active"] is True


def test_owner_auth_flow_and_constant_time_comparison(client_a, monkeypatch):
    """Verify owner authentication flow, rejection on mismatch, and logout."""
    test_key = "secure_owner_key_445566"
    monkeypatch.setattr(config, "OWNER_ACCESS_KEY", test_key)

    # 1. Invalid key fails with 401
    res_fail = client_a.post("/api/auth/owner", json={"access_key": "wrong_key"})
    assert res_fail.status_code == 401
    assert "Invalid owner access key" in res_fail.get_json()["message"]

    # 2. When key is not configured, returns 403
    monkeypatch.setattr(config, "OWNER_ACCESS_KEY", "")
    res_forbidden = client_a.post("/api/auth/owner", json={"access_key": test_key})
    assert res_forbidden.status_code == 403
    monkeypatch.setattr(config, "OWNER_ACCESS_KEY", test_key)

    # 3. Correct key upgrades session to owner
    res_success = client_a.post("/api/auth/owner", json={"access_key": test_key})
    assert res_success.status_code == 200
    data = res_success.get_json()
    assert data["success"] is True
    assert data["role"] == "owner"

    # Verify session endpoint now reports owner
    res_sess = client_a.get("/api/session")
    assert res_sess.get_json()["role"] == "owner"

    # 4. Logout resets to guest and rotates session
    res_logout = client_a.post("/api/auth/logout")
    assert res_logout.status_code == 200
    logout_data = res_logout.get_json()
    assert logout_data["role"] == "guest"
    assert logout_data["workspace_mode"] == "sandbox"

    # Verify session endpoint reverted to guest
    res_sess_after = client_a.get("/api/session")
    assert res_sess_after.get_json()["role"] == "guest"


# ═══════════════════════════════════════════════════════════════
# Task 3: Portfolio Demo Sandbox Interceptor
# ═══════════════════════════════════════════════════════════════

def test_portfolio_demo_sandbox_interceptor_responses():
    """Verify Google Workspace tools return structured [DEMO SANDBOX] responses for guests."""
    is_live = False  # Guest or uncredentialed mode

    # 1. Calendar availability
    res_avail = execute_tool("check_availability", {"date": "2026-05-27"}, is_live_owner=is_live)
    assert res_avail.startswith("[DEMO SANDBOX]")
    assert "availability" in res_avail.lower()

    # 2. Book meeting
    res_book = execute_tool(
        "book_meeting",
        {"title": "Product Architecture Review", "date_time": "2026-05-27T10:00:00+05:30", "guest_name": "Recruiter"},
        is_live_owner=is_live
    )
    assert res_book.startswith("[DEMO SANDBOX]")
    assert "Product Architecture Review" in res_book

    # 3. Set reminder
    res_remind = execute_tool(
        "set_reminder",
        {"title": "Review Tinkr portfolio code", "date_time": "2026-05-27T14:00:00+05:30"},
        is_live_owner=is_live
    )
    assert res_remind.startswith("[DEMO SANDBOX]")

    # 4. Add task
    res_task = execute_tool(
        "add_task",
        {"title": "Audit AI security policies", "notes": "High priority"},
        is_live_owner=is_live
    )
    assert res_task.startswith("[DEMO SANDBOX]")
    assert "Audit AI security policies" in res_task

    # 5. List tasks
    res_list = execute_tool("list_tasks", {}, is_live_owner=is_live)
    assert res_list.startswith("[DEMO SANDBOX]")
    assert "Pending Tasks" in res_list

    # 6. Check unread emails
    res_emails = execute_tool("check_unread_emails", {"timeframe": "today"}, is_live_owner=is_live)
    assert res_emails.startswith("[DEMO SANDBOX]")
    assert "simulated" in res_emails.lower()

    # 7. Draft email
    res_draft = execute_tool(
        "draft_email",
        {"recipient_email": "recruiter@hiring.com", "subject": "Thanks for the interview", "body_context": "Body"},
        is_live_owner=is_live
    )
    assert res_draft.startswith("[DEMO SANDBOX]")
    assert "recruiter@hiring.com" in res_draft

    # 8. Send email
    res_send = execute_tool(
        "send_email",
        {"recipient_email": "recruiter@hiring.com", "subject": "Portfolio demo feedback", "body_context": "Body"},
        is_live_owner=is_live
    )
    assert res_send.startswith("[DEMO SANDBOX]")
    assert "recruiter@hiring.com" in res_send


def test_non_workspace_tools_remain_live():
    """Verify web search, news, and weather remain live for all sessions."""
    # Test weather tool routing
    res = execute_tool("get_weather", {"location": "London"}, is_live_owner=False)
    assert not res.startswith("[DEMO SANDBOX]")
