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
    MediaClass,
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
    media_type = options.media_type or "root"
    media_id = options.media_id or ""

    if media_type == "root" or (options.media_id is None and options.media_type is None):
        return _browse_root()

    if media_type == "channels":
        paging = options.paging
        page = int((paging.page if paging and paging.page else None) or 1)
        return await _browse_channels(device, page)

    return StatusCodes.NOT_FOUND


async def search(
    device: HorizonDevice, device_id: str, options: SearchOptions
) -> SearchResults | StatusCodes:
    query = (options.query or "").strip().lower()
    if not query:
        return SearchResults(media=[], pagination=Pagination(page=1, limit=0, count=0))

    channels = await device.get_channels()
    matches = [ch for ch in channels if query in ch["name"].lower()]

    items = [
        BrowseMediaItem(
            title=ch["name"],
            media_class=MediaClass.CHANNEL,
            media_type="channel",
            media_id=f"channel_{ch['name']}",
            can_play=True,
            can_browse=False,
        )
        for ch in matches[:PAGE_SIZE]
    ]

    return SearchResults(
        media=items,
        pagination=Pagination(page=1, limit=len(items), count=len(items)),
    )


def _browse_root() -> BrowseResults:
    return BrowseResults(
        media=BrowseMediaItem(
            title="Horizon",
            media_class=MediaClass.DIRECTORY,
            media_type="root",
            media_id="root",
            can_browse=True,
            items=[
                BrowseMediaItem(
                    title="Channels",
                    media_class=MediaClass.DIRECTORY,
                    media_type="channels",
                    media_id="channels",
                    can_browse=True,
                    can_play=False,
                ),
            ],
        ),
        pagination=Pagination(page=1, limit=1, count=1),
    )


async def _browse_channels(device: HorizonDevice, page: int) -> BrowseResults:
    channels = await device.get_channels()
    total = len(channels)
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_channels = channels[start:end]

    items = [
        BrowseMediaItem(
            title=ch["name"],
            media_class=MediaClass.CHANNEL,
            media_type="channel",
            media_id=f"channel_{ch['name']}",
            can_play=True,
            can_browse=False,
        )
        for ch in page_channels
    ]

    return BrowseResults(
        media=BrowseMediaItem(
            title="Channels",
            media_class=MediaClass.DIRECTORY,
            media_type="channels",
            media_id="channels",
            can_browse=True,
            can_search=True,
            items=items,
        ),
        pagination=Pagination(page=page, limit=PAGE_SIZE, count=total),
    )
