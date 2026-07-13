from fastapi.testclient import TestClient

from app.main import app


def test_restart_service_endpoint_schedules_pixelforge_restart(monkeypatch):
    from app.routes import admin as admin_routes

    calls = []

    def fake_schedule_restart(*, service_name: str, delay_seconds: int = 1):
        calls.append((service_name, delay_seconds))
        return {
            "scheduled": True,
            "service_name": service_name,
            "delay_seconds": delay_seconds,
            "restart_command": ["systemctl", "--user", "restart", service_name],
            "scheduler": "systemd-run",
        }

    monkeypatch.setattr(admin_routes, "schedule_user_service_restart", fake_schedule_restart)

    response = TestClient(app).post("/v1/admin/service/restart")

    assert response.status_code == 202
    assert response.json()["scheduled"] is True
    assert response.json()["service_name"] == "pixelforge.service"
    assert response.json()["delay_seconds"] == 1
    assert calls == [("pixelforge.service", 1)]
