"""
Media browser for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ucapi import StatusCodes
from ucapi.api_definitions import (
    BrowseMediaItem,
    BrowseOptions,
    BrowseResults,
    Pagination,
    SearchOptions,
    SearchResults,
)

if TYPE_CHECKING:
    from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)

PAGE_SIZE = 50


async def browse(
    device: HorizonDevice, device_id: str, options: BrowseOptions
) -> BrowseResults | StatusCodes:
    item_id = getattr(options, "item_id", None) or ""
    page = getattr(options, "page", 1) or 1

    if not item_id:
        return _browse_root()

    if item_id == "channels":
        return await _browse_channels(device, page)

    return StatusCodes.NOT_FOUND


async def search(
    device: HorizonDevice, device_id: str, options: SearchOptions
) -> SearchResults | StatusCodes:
    query = (getattr(options, "query", "") or "").strip().lower()
    if not query:
        return StatusCodes.BAD_REQUEST

    channels = await device.get_channels()
    matches = [ch for ch in channels if query in ch["name"].lower()]

    items = [
        BrowseMediaItem(
            id=f"channel_{ch['name']}",
            title=ch["name"],
            browseable=False,
            playable=True,
        )
        for ch in matches[:PAGE_SIZE]
    ]

    return SearchResults(items=items)


def _browse_root() -> BrowseResults:
    return BrowseResults(
        items=[
            BrowseMediaItem(
                id="channels",
                title="Channels",
                browseable=True,
                playable=False,
            ),
        ]
    )


async def _browse_channels(device: HorizonDevice, page: int) -> BrowseResults:
    channels = await device.get_channels()
    total = len(channels)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_channels = channels[start:end]

    items = [
        BrowseMediaItem(
            id=f"channel_{ch['name']}",
            title=ch["name"],
            browseable=False,
            playable=True,
        )
        for ch in page_channels
    ]

    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE if total > 0 else 1

    return BrowseResults(
        items=items,
        pagination=Pagination(
            page=page,
            limit=PAGE_SIZE,
            total=total,
            total_pages=total_pages,
        ),
    )
