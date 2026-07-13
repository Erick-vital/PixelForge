from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def schedule_user_service_restart(*, service_name: str, delay_seconds: int = 1) -> dict[str, Any]:
    """Schedule a user-service restart after the HTTP response has been sent."""
    systemd_run = shutil.which("systemd-run")
    systemctl = shutil.which("systemctl")
    if not systemctl:
        raise RuntimeError("systemctl is required to restart the service")

    restart_command = [systemctl, "--user", "restart", service_name]
    if systemd_run:
        unit_name = f"{Path(service_name).stem}-restart"
        command = [
            systemd_run,
            "--user",
            "--unit",
            unit_name,
            f"--on-active={delay_seconds}s",
            *restart_command,
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "Failed to schedule service restart")
        logger.info(
            "PixelForge restart scheduled",
            extra={"service_name": service_name, "delay_seconds": delay_seconds, "scheduler": "systemd-run"},
        )
        return {
            "scheduled": True,
            "service_name": service_name,
            "delay_seconds": delay_seconds,
            "restart_command": restart_command,
            "scheduler": "systemd-run",
            "scheduler_command": command,
            "stdout": completed.stdout.strip(),
        }

    process = subprocess.Popen(restart_command)
    logger.info(
        "PixelForge restart scheduled",
        extra={"service_name": service_name, "delay_seconds": 0, "scheduler": "systemctl"},
    )
    return {
        "scheduled": True,
        "service_name": service_name,
        "delay_seconds": 0,
        "restart_command": restart_command,
        "scheduler": "systemctl",
        "scheduler_pid": process.pid,
    }
