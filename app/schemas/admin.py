from __future__ import annotations

from pydantic import BaseModel


class ServiceRestartResponse(BaseModel):
    scheduled: bool
    service_name: str
    delay_seconds: int
    restart_command: list[str]
    scheduler: str | None = None
    scheduler_command: list[str] | None = None
    scheduler_pid: int | None = None
    stdout: str | None = None
