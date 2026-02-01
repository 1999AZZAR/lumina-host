"""Media service: upload and delete orchestration."""

from __future__ import annotations

import io
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from PIL import Image, ImageOps

import database
import wordpress_api

logger = logging.getLogger(__name__)

UPLOAD_MAX_WORKERS = 10
DELETE_MAX_WORKERS = 10


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


def optimize_image(file_bytes: bytes, filename: str, mimetype: str) -> bytes:
    """
    Optimize image for web: resize large images, strip metadata, and compress.
    Returns original bytes if optimization fails or is not an image.
    """
    if not mimetype.startswith('image/') or 'svg' in mimetype:
        return file_bytes

    try:
        img = Image.open(io.BytesIO(file_bytes))

        # Auto-rotate based on EXIF (then strip it by creating new image or saving)
        img = ImageOps.exif_transpose(img)

        # Resize if too large (max 2560px)
        max_size = 2560
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.BICUBIC)

        # Determine output format
        orig_format = (img.format or '').upper()
        # Convert BMP/TIFF/ICO to PNG for web compatibility
        if orig_format in ('BMP', 'TIFF', 'ICO', 'DIB'):
            output_format = 'PNG'
        elif mimetype == 'image/jpeg' or orig_format == 'JPEG':
            output_format = 'JPEG'
        elif mimetype == 'image/webp' or orig_format == 'WEBP':
            output_format = 'WEBP'
        else:
            # Default to PNG for transparency support (GIF, PNG, etc)
            output_format = 'PNG'

        # Convert to RGB if saving as JPEG (handled automatically for others usually, but safety first)
        if output_format == 'JPEG' and img.mode != 'RGB':
            img = img.convert('RGB')
        
        buffer = io.BytesIO()
        # Optimize and save
        save_args = {'optimize': True}
        if output_format == 'JPEG':
            save_args['quality'] = 85
        
        # WebP optimization
        if output_format == 'WEBP':
            save_args['quality'] = 85

        img.save(buffer, format=output_format, **save_args)
        return buffer.getvalue()
    except Exception as e:
        logger.warning("Image optimization failed for %s: %s", filename, e)
        return file_bytes


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
            filename, raw_data, mimetype = item
            
            # Optimize in this thread (parallel CPU task)
            optimized_data = optimize_image(raw_data, filename, mimetype)
            
            wrapper = _BytesFileWrapper(optimized_data, filename, mimetype)
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
        remote_deleted = 0
        
        if not wp_ids:
            return (0, 0)
        
        # Delete from WordPress in parallel
        with ThreadPoolExecutor(max_workers=min(DELETE_MAX_WORKERS, len(wp_ids))) as executor:
            futures = {executor.submit(wordpress_api.delete_media, wp_id): wp_id for wp_id in wp_ids}
            for future in as_completed(futures):
                try:
                    if future.result():
                        remote_deleted += 1
                except Exception as e:
                    logger.error("Failed to delete WP asset: %s", e)
                    
        return (len(wp_ids), remote_deleted)
