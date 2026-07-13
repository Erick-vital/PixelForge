from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.schemas.admin import ServiceRestartResponse
from app.services.systemd_control import schedule_user_service_restart

router = APIRouter(prefix="/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)
SERVICE_NAME = "pixelforge.service"


@router.post("/service/restart", response_model=ServiceRestartResponse, status_code=status.HTTP_202_ACCEPTED)
def restart_pixelforge_service() -> ServiceRestartResponse:
    """Schedule PixelForge's own restart after this response is returned."""
    logger.info("PixelForge restart endpoint requested", extra={"service_name": SERVICE_NAME})
    try:
        result = schedule_user_service_restart(service_name=SERVICE_NAME, delay_seconds=1)
    except RuntimeError as exc:
        logger.warning("PixelForge restart could not be scheduled", extra={"service_name": SERVICE_NAME})
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ServiceRestartResponse(**result)
