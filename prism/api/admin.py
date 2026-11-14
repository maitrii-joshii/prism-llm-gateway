"""Admin API endpoints for Prism Gateway operations."""

import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


async def verify_admin_token(request: Request) -> None:
    """Validate the separate Prism admin bearer token."""

    # Prefer token stored in app.state (set at startup from Settings).
    # Fall back to os.getenv for contexts where app.state is unavailable
    # (e.g. lightweight test fixtures that don't boot the full app).
    configured_token = getattr(
        request.app.state, "admin_token", None
    ) or os.getenv("PRISM_ADMIN_TOKEN")
    authorization = request.headers.get("Authorization", "")

    if not configured_token:
        raise HTTPException(
            status_code=401,
            detail="Admin authentication is not configured.",
        )

    scheme, separator, supplied_token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not supplied_token
        or not secrets.compare_digest(
            supplied_token,
            configured_token,
        )
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing admin token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/usage")
async def get_admin_usage(
    request: Request,
    month: str | None = Query(
        default=None,
        description="Usage month in YYYY-MM format. Defaults to the current month.",
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
    ),
):
    """Return monthly usage grouped by virtual API key."""

    await verify_admin_token(request)

    selected_month = month or datetime.now(
        timezone.utc
    ).strftime("%Y-%m")

    usage_records = request.app.state.usage_repository.get_all_usage(
        selected_month
    )

    return {
        "month": selected_month,
        "total_keys": len(usage_records),
        "usage": [
            record.model_dump(mode="json")
            for record in usage_records
        ],
    }


@router.get("/logs")
async def get_admin_logs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    key_hash: str | None = Query(default=None),
):
    """Return recent request logs with pagination and key filtering."""

    await verify_admin_token(request)

    logs = request.app.state.log_repository.get_logs(
        limit=limit,
        offset=offset,
        key_hash=key_hash,
    )

    return {
        "limit": limit,
        "offset": offset,
        "key_hash": key_hash,
        "count": len(logs),
        "logs": [
            log.model_dump(mode="json")
            for log in logs
        ],
    }


@router.get("/cache/stats")
async def get_admin_cache_stats(request: Request):
    """Return aggregate semantic cache statistics."""

    await verify_admin_token(request)

    stats = request.app.state.cache_repository.get_stats()

    # Compute accurate hit rate from usage records (cache_hits / total_requests).
    # The cache entry table only tracks stored prompts, not total lookups, so
    # using total_entries in the denominator would yield a misleading metric.
    selected_month = datetime.now(timezone.utc).strftime("%Y-%m")
    usage_records = request.app.state.usage_repository.get_all_usage(
        selected_month
    )
    total_requests = sum(r.total_requests for r in usage_records)
    total_cache_hits = sum(r.cache_hits for r in usage_records)

    cache_hit_rate = (
        total_cache_hits / total_requests
        if total_requests > 0
        else 0.0
    )

    return {
        **stats.model_dump(mode="json"),
        "cache_hit_rate": round(cache_hit_rate, 4),
        "cache_hits_this_month": total_cache_hits,
        "total_requests_this_month": total_requests,
    }


__all__ = ["router"]
