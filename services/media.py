"""Media service: upload and delete orchestration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import database
import wordpress_api

UPLOAD_MAX_WORKERS = 4


class _BytesFileWrapper:
    """Wrapper to pass in-memory file data to wordpress_api.upload_media."""

    __slots__ = ('_data', '_filename', '_mimetype')

    def __init__(self, data: bytes, filename: str, mimetype: str) -> None:
        self._data = data
        self._filename = filename
        self._mimetype = mimetype

    def read(self) -> bytes:
        return self._data

    @property
    def filename(self) -> str:
        return self._filename

    @property
    def mimetype(self) -> str:
        return self._mimetype

    @property
    def content_type(self) -> str:
        return self._mimetype


class MediaService:
    """Orchestrates upload to WordPress and local DB, and bulk delete."""

    @staticmethod
    def upload_files(
        valid: list[tuple[str, bytes, str]],
        user_id: int | None = None,
        tenant_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Upload files in parallel. Returns (uploaded_assets, failed_filenames)."""
        uploaded: list[dict[str, Any]] = []
        failed: list[str] = []

        def upload_one(item: tuple[str, bytes, str]) -> tuple[str, dict[str, Any] | None]:
            filename, data, mimetype = item
            wrapper = _BytesFileWrapper(data, filename, mimetype)
            asset_data = wordpress_api.upload_media(wrapper)
            return (filename, asset_data)

        with ThreadPoolExecutor(max_workers=min(UPLOAD_MAX_WORKERS, len(valid))) as executor:
            futures = {executor.submit(upload_one, item): item[0] for item in valid}
            for future in as_completed(futures):
                filename, asset_data = future.result()
                if asset_data:
                    database.add_asset(asset_data, user_id=user_id, tenant_id=tenant_id)
                    uploaded.append(asset_data)
                else:
                    failed.append(filename)
        return (uploaded, failed)

    @staticmethod
    def delete_assets(
        ids: list[int],
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> tuple[int, int]:
        """Delete assets locally and on WordPress. Returns (local_deleted, remote_deleted)."""
        wp_ids = database.delete_assets(ids, tenant_id=tenant_id, user_id=user_id)
        remote_deleted = sum(1 for wp_id in wp_ids if wordpress_api.delete_media(wp_id))
        return (len(wp_ids), remote_deleted)
