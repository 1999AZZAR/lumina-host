"""Album service: CRUD operations for albums."""

from __future__ import annotations

from typing import Any

import database


class AlbumService:
    """Manage albums and perform permission checks."""

    @staticmethod
    def create_album(
        name: str,
        description: str | None,
        user_id: int | None,
        tenant_id: int | None,
    ) -> dict[str, Any]:
        """Create a new album."""
        album_id = database.create_album(name, description, user_id, tenant_id)
        if not album_id:
            raise ValueError("Failed to create album")
        return database.get_album(album_id) or {}

    @staticmethod
    def get_albums(
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """List albums for a specific user/tenant. If None, lists all (admin view typically)."""
        return database.get_albums(tenant_id=tenant_id, user_id=user_id)

    @staticmethod
    def get_album(
        album_id: int,
        tenant_id: int | None = None,
        user_id: int | None = None,
        is_admin: bool = False,
    ) -> dict[str, Any] | None:
        """Get album by ID. Checks permissions."""
        album = database.get_album(album_id)
        if not album:
            return None
        
        if is_admin:
            return album
            
        # Check ownership
        # If user is in the same tenant, they might see it depending on rules.
        # Current rule: Users see their own albums + tenant albums? 
        # Actually, `database.get_albums` filters strictly. 
        # Let's enforce strict ownership or tenant membership.
        
        # If tenant_id is provided, album must belong to it.
        if tenant_id and album['tenant_id'] != tenant_id:
            return None
            
        # If user_id is provided, logic depends.
        # If we want shared tenant albums, maybe looser? 
        # For now, let's match `delete_assets` logic: typically user owns resources.
        # But if we want shared albums, we might relax user_id check.
        # Let's stick to strict user_id check if provided, unless we define "shared albums".
        # Assuming private user albums for now.
        if user_id and album['user_id'] != user_id:
            return None
            
        return album

    @staticmethod
    def update_album(
        album_id: int,
        name: str,
        description: str | None,
        tenant_id: int | None,
        user_id: int | None,
        is_admin: bool = False,
    ) -> bool:
        """Update album. Checks permissions."""
        album = AlbumService.get_album(album_id, tenant_id, user_id, is_admin)
        if not album:
            return False
        return database.update_album(album_id, name, description)

    @staticmethod
    def delete_album(
        album_id: int,
        tenant_id: int | None,
        user_id: int | None,
        is_admin: bool = False,
    ) -> bool:
        """Delete album. Checks permissions."""
        album = AlbumService.get_album(album_id, tenant_id, user_id, is_admin)
        if not album:
            return False
        return database.delete_album(album_id)
