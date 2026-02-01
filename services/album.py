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
        parent_id: int | None = None,
        is_public: bool = True,
    ) -> dict[str, Any]:
        """Create a new album."""
        # Verify parent exists and belongs to same context
        if parent_id:
            parent = AlbumService.get_album(parent_id, tenant_id, user_id, is_admin=False)
            if not parent:
                raise ValueError("Invalid parent album")
                
        album_id = database.create_album(name, description, user_id, tenant_id, parent_id, is_public)
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
            
        if tenant_id and album['tenant_id'] != tenant_id:
            return None
            
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
        parent_id: int | None = None,
        is_public: bool | None = None,
    ) -> bool:
        """Update album. Checks permissions."""
        album = AlbumService.get_album(album_id, tenant_id, user_id, is_admin)
        if not album:
            return False
            
        if parent_id:
            if parent_id == album_id:
                raise ValueError("Album cannot be its own parent")
            parent = AlbumService.get_album(parent_id, tenant_id, user_id, is_admin)
            if not parent:
                raise ValueError("Invalid parent album")
                
        return database.update_album(album_id, name, description, parent_id, is_public)

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
