from fastapi.testclient import TestClient

from web.app import app


def test_login_and_dashboard_pages_render_mobile_auth_ui():
    client = TestClient(app)
    login = client.get("/login")
    dashboard = client.get("/dashboard")

    assert login.status_code == 200
    assert 'name="viewport"' in login.text
    assert "Получить код" in login.text
    assert 'autocomplete="one-time-code"' in login.text
    assert 'inputmode="numeric"' in login.text
    assert "Не могу войти" in login.text

    assert dashboard.status_code == 200
    assert "Личный кабинет" in dashboard.text
    assert "Реферальный код" in dashboard.text
    assert "Root ID" in dashboard.text
    assert 'id="logout-button"' in dashboard.text


def test_auth_static_assets_are_served():
    client = TestClient(app)
    stylesheet = client.get("/static/auth.css")
    script = client.get("/static/auth.js")

    assert stylesheet.status_code == 200
    assert ".auth-card" in stylesheet.text
    assert script.status_code == 200
    assert "/auth/request-code" in script.text
    assert "/auth/verify-code" in script.text
    assert "/auth/me" in script.text
