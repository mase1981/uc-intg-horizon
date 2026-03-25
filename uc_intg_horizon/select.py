"""
Select entity for Horizon integration - channel selector.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from ucapi import StatusCodes
from ucapi.select import Attributes, Commands, States, Select

if TYPE_CHECKING:
    import ucapi
    from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)


class HorizonChannelSelect(Select):
    """Select entity for choosing a channel on a Horizon STB."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        horizon_device: HorizonDevice,
        api: ucapi.IntegrationAPI,
    ) -> None:
        self._device_id = device_id
        self._horizon_device = horizon_device
        self._api = api
        self._channels_populated = False

        super().__init__(
            identifier=f"{device_id}_channel_select",
            name=f"{device_name} Channel",
            attributes={
                Attributes.STATE: States.UNAVAILABLE,
                Attributes.OPTIONS: [],
                Attributes.CURRENT_OPTION: "",
            },
            cmd_handler=self._handle_command,
        )

        asyncio.create_task(self._load_channels())

    async def _load_channels(self) -> None:
        try:
            channels = await self._horizon_device.get_channels()
            if not channels:
                return
            options = [ch["name"] for ch in channels]
            self.attributes[Attributes.OPTIONS] = options
            self.attributes[Attributes.STATE] = States.ON
            self._channels_populated = True
            _LOG.info("Loaded %d channels for select %s", len(options), self._device_id)
        except Exception as err:
            _LOG.error("Failed to load channels for select: %s", err)

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        _LOG.info("[%s] Command: %s params=%s", self.id, cmd_id, params)

        if cmd_id == Commands.SELECT_OPTION:
            if not params or "option" not in params:
                return StatusCodes.BAD_REQUEST

            channel_name = params["option"]
            success = await self._horizon_device.set_channel(self._device_id, channel_name)
            if success:
                self.attributes[Attributes.CURRENT_OPTION] = channel_name
                if self._api and self._api.configured_entities.contains(self.id):
                    self._api.configured_entities.update_attributes(self.id, self.attributes)
            return StatusCodes.OK if success else StatusCodes.SERVER_ERROR

        return StatusCodes.NOT_IMPLEMENTED

    async def update_state(self, device_state: dict[str, Any]) -> None:
        horizon_state = device_state.get("state", "unavailable")
        channel = device_state.get("channel", "")

        if horizon_state in (
            "PLAYING", "PAUSED", "STANDBY", "ON",
            "ONLINE_RUNNING", "ONLINE_STANDBY",
        ):
            self.attributes[Attributes.STATE] = States.ON
        elif horizon_state in ("OFF", "OFFLINE", "UNAVAILABLE"):
            self.attributes[Attributes.STATE] = States.UNAVAILABLE
        else:
            self.attributes[Attributes.STATE] = States.UNAVAILABLE

        if channel:
            self.attributes[Attributes.CURRENT_OPTION] = channel

        if not self._channels_populated and self._horizon_device.channels_loaded:
            await self._load_channels()

        if self._api and self._api.configured_entities.contains(self.id):
            self._api.configured_entities.update_attributes(self.id, self.attributes)
