"""Asset service: query operations."""

from __future__ import annotations

from typing import Any

import database


class AssetService:
    """Query assets with pagination and search."""

    @staticmethod
    def get_assets(
        page: int = 1,
        per_page: int = 20,
        search_query: str | None = None,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """Return {'assets': list, 'has_more': bool}."""
        return database.get_assets(
            page=page,
            per_page=per_page,
            search_query=search_query,
            tenant_id=tenant_id,
            user_id=user_id,
        )
