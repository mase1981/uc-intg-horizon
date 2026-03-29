"""
Media Player entity for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, TYPE_CHECKING

from ucapi import MediaPlayer, StatusCodes
from ucapi.media_player import Attributes, Commands, Features, States
from ucapi.api_definitions import BrowseOptions, BrowseResults, SearchOptions, SearchResults

from uc_intg_horizon import browser
from uc_intg_horizon.const import CHANNEL_UPDATE_DELAY, POWER_COMMAND_DELAY, STREAMING_APPS

if TYPE_CHECKING:
    import ucapi
    from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)

FEATURES = [
    Features.ON_OFF,
    Features.TOGGLE,
    Features.VOLUME_UP_DOWN,
    Features.MUTE_TOGGLE,
    Features.PLAY_PAUSE,
    Features.STOP,
    Features.NEXT,
    Features.PREVIOUS,
    Features.FAST_FORWARD,
    Features.REWIND,
    Features.RECORD,
    Features.CHANNEL_SWITCHER,
    Features.SELECT_SOURCE,
    Features.DPAD,
    Features.HOME,
    Features.MENU,
    Features.CONTEXT_MENU,
    Features.GUIDE,
    Features.INFO,
    Features.MEDIA_TITLE,
    Features.MEDIA_ARTIST,
    Features.MEDIA_IMAGE_URL,
    Features.MEDIA_POSITION,
    Features.SEEK,
    Features.PLAY_MEDIA,
    Features.BROWSE_MEDIA,
    Features.SEARCH_MEDIA,
]


class HorizonMediaPlayer(MediaPlayer):
    """Media Player entity for a Horizon set-top box."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        horizon_device: HorizonDevice,
        api: ucapi.IntegrationAPI,
        sensors: list | None = None,
    ) -> None:
        self._device_id = device_id
        self._horizon_device = horizon_device
        self._api = api
        self._sensors = sensors or []
        self._channel_update_task: asyncio.Task | None = None
        self._last_good_metadata: dict[str, Any] = {}
        self._pending_channel: str = ""

        attributes = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.MEDIA_TITLE: "",
            Attributes.MEDIA_ARTIST: "",
            Attributes.MEDIA_IMAGE_URL: "",
            Attributes.MEDIA_POSITION: 0,
            Attributes.MEDIA_DURATION: 0,
            Attributes.MUTED: False,
            Attributes.SOURCE: "",
            Attributes.SOURCE_LIST: [],
        }

        super().__init__(
            identifier=device_id,
            name=device_name,
            features=FEATURES,
            attributes=attributes,
            cmd_handler=self._handle_command,
        )

        self._sources_loaded = False
        asyncio.create_task(self._load_sources())
        asyncio.create_task(self._periodic_refresh())

    async def _load_sources(self) -> None:
        try:
            channels = await self._horizon_device.get_channels()
            if not channels:
                return
            source_list = [ch["name"] for ch in channels]
            self.attributes[Attributes.SOURCE_LIST] = source_list
            self._sources_loaded = True
            _LOG.info("Loaded %d sources for %s", len(source_list), self._device_id)
        except Exception as err:
            _LOG.error("Failed to load sources: %s", err)

    async def _periodic_refresh(self) -> None:
        from uc_intg_horizon.const import PERIODIC_REFRESH_INTERVAL
        await asyncio.sleep(PERIODIC_REFRESH_INTERVAL)

        while True:
            try:
                if self._api and self._api.configured_entities.contains(self.id):
                    await self.push_update()
                await asyncio.sleep(PERIODIC_REFRESH_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOG.error("Periodic refresh error for %s: %s", self._device_id, err)
                await asyncio.sleep(PERIODIC_REFRESH_INTERVAL)

    async def browse(self, options: BrowseOptions) -> BrowseResults | StatusCodes:
        return await browser.browse(self._horizon_device, self._device_id, options)

    async def search(self, options: SearchOptions) -> SearchResults | StatusCodes:
        return await browser.search(self._horizon_device, self._device_id, options)

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        _LOG.info("[%s] Command: %s params=%s", self.id, cmd_id, params)

        is_power = False
        is_channel = False

        try:
            if cmd_id == Commands.ON:
                await self._horizon_device.power_on(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                is_power = True

            elif cmd_id == Commands.OFF:
                await self._horizon_device.power_off(self._device_id)
                self.attributes[Attributes.STATE] = States.STANDBY
                is_power = True

            elif cmd_id == Commands.TOGGLE:
                await self._horizon_device.power_toggle(self._device_id)
                current = self.attributes.get(Attributes.STATE)
                if current in [States.ON, States.PLAYING, States.PAUSED]:
                    self.attributes[Attributes.STATE] = States.STANDBY
                else:
                    self.attributes[Attributes.STATE] = States.ON
                is_power = True

            elif cmd_id == Commands.PLAY_PAUSE:
                state = self._horizon_device.get_device_state(self._device_id)
                if state.get("paused"):
                    await self._horizon_device.play(self._device_id)
                    self.attributes[Attributes.STATE] = States.PLAYING
                else:
                    await self._horizon_device.pause(self._device_id)
                    self.attributes[Attributes.STATE] = States.PAUSED

            elif cmd_id == Commands.STOP:
                await self._horizon_device.stop(self._device_id)
                self.attributes[Attributes.STATE] = States.ON

            elif cmd_id == Commands.NEXT:
                await self._horizon_device.next_channel(self._device_id)
                is_channel = True

            elif cmd_id == Commands.PREVIOUS:
                await self._horizon_device.previous_channel(self._device_id)
                is_channel = True

            elif cmd_id == Commands.FAST_FORWARD:
                await self._horizon_device.fast_forward(self._device_id)

            elif cmd_id == Commands.REWIND:
                await self._horizon_device.rewind(self._device_id)

            elif cmd_id == Commands.RECORD:
                await self._horizon_device.record(self._device_id)

            elif cmd_id == Commands.SEEK:
                if params and "media_position" in params:
                    position = int(params["media_position"])
                    success = await self._horizon_device.seek(self._device_id, position)
                    if success:
                        self.attributes[Attributes.MEDIA_POSITION] = position
                    return StatusCodes.OK if success else StatusCodes.SERVER_ERROR
                return StatusCodes.BAD_REQUEST

            elif cmd_id == Commands.VOLUME_UP:
                await self._horizon_device.send_key(self._device_id, "VolumeUp")

            elif cmd_id == Commands.VOLUME_DOWN:
                await self._horizon_device.send_key(self._device_id, "VolumeDown")

            elif cmd_id == Commands.MUTE_TOGGLE:
                await self._horizon_device.send_key(self._device_id, "VolumeMute")
                self.attributes[Attributes.MUTED] = not self.attributes.get(
                    Attributes.MUTED, False
                )

            elif cmd_id == Commands.CURSOR_UP:
                await self._horizon_device.send_key(self._device_id, "ArrowUp")
            elif cmd_id == Commands.CURSOR_DOWN:
                await self._horizon_device.send_key(self._device_id, "ArrowDown")
            elif cmd_id == Commands.CURSOR_LEFT:
                await self._horizon_device.send_key(self._device_id, "ArrowLeft")
            elif cmd_id == Commands.CURSOR_RIGHT:
                await self._horizon_device.send_key(self._device_id, "ArrowRight")
            elif cmd_id == Commands.CURSOR_ENTER:
                await self._horizon_device.send_key(self._device_id, "Enter")

            elif cmd_id == Commands.HOME:
                await self._horizon_device.send_key(self._device_id, "MediaTopMenu")
            elif cmd_id == Commands.MENU:
                await self._horizon_device.send_key(self._device_id, "Info")
            elif cmd_id == Commands.CONTEXT_MENU:
                await self._horizon_device.send_key(self._device_id, "Options")
            elif cmd_id == Commands.GUIDE:
                await self._horizon_device.send_key(self._device_id, "Guide")
            elif cmd_id == Commands.INFO:
                await self._horizon_device.send_key(self._device_id, "Info")
            elif cmd_id == Commands.BACK:
                await self._horizon_device.send_key(self._device_id, "Escape")

            elif cmd_id == Commands.CHANNEL_UP:
                await self._horizon_device.next_channel(self._device_id)
                is_channel = True
            elif cmd_id == Commands.CHANNEL_DOWN:
                await self._horizon_device.previous_channel(self._device_id)
                is_channel = True

            elif cmd_id == Commands.SELECT_SOURCE:
                return await self._handle_select_source(params)

            elif cmd_id == Commands.PLAY_MEDIA:
                return await self._handle_play_media(params)

            elif cmd_id == "my_recordings":
                await self._horizon_device.send_key(self._device_id, "Recordings")

            elif cmd_id.startswith("channel_select:"):
                channel = cmd_id.split(":", 1)[1]
                await self._horizon_device.set_channel_by_number(self._device_id, channel)
                is_channel = True

            else:
                _LOG.warning("[%s] Unhandled command: %s", self.id, cmd_id)
                return StatusCodes.NOT_IMPLEMENTED

            if is_power:
                await asyncio.sleep(POWER_COMMAND_DELAY)
                await self.push_update()
            elif is_channel:
                self._schedule_channel_update()

            return StatusCodes.OK

        except Exception as err:
            _LOG.error("[%s] Command error: %s", self.id, err, exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _handle_select_source(self, params: dict[str, Any] | None) -> StatusCodes:
        if not params or "source" not in params:
            return StatusCodes.BAD_REQUEST

        source = params["source"]
        if source.startswith("HDMI") or source == "AV Input":
            await self._horizon_device.send_key(self._device_id, "Settings")
        elif source in STREAMING_APPS:
            await self._horizon_device.send_key(self._device_id, "MediaTopMenu")
        else:
            self._pending_channel = source
            await self._horizon_device.set_channel(self._device_id, source)
            self._schedule_channel_update()

        self.attributes[Attributes.SOURCE] = source
        return StatusCodes.OK

    async def _handle_play_media(self, params: dict[str, Any] | None) -> StatusCodes:
        if not params:
            return StatusCodes.BAD_REQUEST
        media_id = params.get("media_id", "")
        if not media_id:
            return StatusCodes.BAD_REQUEST

        if media_id.startswith("channel_"):
            channel_name = media_id[8:]
            self._pending_channel = channel_name
            await self._horizon_device.set_channel(self._device_id, channel_name)
            self._schedule_channel_update()
            return StatusCodes.OK

        _LOG.warning("[%s] Unknown media_id: %s", self.id, media_id)
        return StatusCodes.BAD_REQUEST

    def _schedule_channel_update(self) -> None:
        if self._channel_update_task and not self._channel_update_task.done():
            self._channel_update_task.cancel()
        self._channel_update_task = asyncio.create_task(self._delayed_channel_update())

    async def _delayed_channel_update(self) -> None:
        try:
            await asyncio.sleep(CHANNEL_UPDATE_DELAY)
            await self.push_update()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOG.error("Delayed channel update error: %s", err)

    # -- Metadata degradation handling -----------------------------------------

    def _is_degraded_metadata(self, device_state: dict[str, Any]) -> bool:
        channel = (device_state.get("channel") or "").strip()
        title = (device_state.get("media_title") or "").strip()
        image = (device_state.get("media_image") or "").lower()

        if not channel or channel == "No Channel":
            return True
        if not title or title == "No Program" or "launcher" in title.lower():
            return True
        if "appstore" in image:
            return True
        if not device_state.get("start_time") and not device_state.get("end_time"):
            return True
        return False

    def _get_effective_metadata(self, device_state: dict[str, Any]) -> dict[str, Any]:
        current_channel = (device_state.get("channel") or "").strip()

        if self._is_degraded_metadata(device_state):
            if self._pending_channel:
                return {
                    **device_state,
                    "channel": self._pending_channel,
                    "media_title": "",
                    "media_image": "",
                    "start_time": None,
                    "end_time": None,
                }
            if self._last_good_metadata:
                cached_channel = self._last_good_metadata.get("channel", "")
                if not current_channel or current_channel == "No Channel":
                    return {**device_state, **self._last_good_metadata}
                if current_channel == cached_channel:
                    return {**device_state, **self._last_good_metadata}
            return device_state

        self._pending_channel = ""
        self._last_good_metadata = {
            k: device_state.get(k)
            for k in ("channel", "media_title", "media_image", "start_time", "end_time")
        }
        return device_state

    @staticmethod
    def _make_unique_image_url(base_url: str) -> str:
        if not base_url:
            return base_url
        sep = "&" if "?" in base_url else "?"
        return f"{base_url}{sep}_t={int(time.time() * 1000)}"

    # -- Push update -----------------------------------------------------------

    async def push_update(self) -> None:
        if not self._api or not self._api.configured_entities.contains(self.id):
            return

        device_state = self._horizon_device.get_device_state(self._device_id)
        horizon_state = device_state.get("state", "unavailable")

        if horizon_state == "ONLINE_RUNNING":
            if device_state.get("paused"):
                self.attributes[Attributes.STATE] = States.PAUSED
            else:
                self.attributes[Attributes.STATE] = States.PLAYING
            effective = self._get_effective_metadata(device_state)
        elif horizon_state == "ONLINE_STANDBY":
            self.attributes[Attributes.STATE] = States.STANDBY
            self._last_good_metadata = {}
            effective = device_state
        elif horizon_state == "OFFLINE":
            self.attributes[Attributes.STATE] = States.OFF
            self._last_good_metadata = {}
            effective = device_state
        else:
            self.attributes[Attributes.STATE] = States.UNAVAILABLE
            effective = device_state

        channel_name = effective.get("channel", "")
        program_title = effective.get("media_title", "")

        if program_title:
            self.attributes[Attributes.MEDIA_TITLE] = program_title
            self.attributes[Attributes.MEDIA_ARTIST] = channel_name
        elif channel_name:
            self.attributes[Attributes.MEDIA_TITLE] = channel_name
            self.attributes[Attributes.MEDIA_ARTIST] = ""
        else:
            self.attributes[Attributes.MEDIA_TITLE] = ""
            self.attributes[Attributes.MEDIA_ARTIST] = ""

        media_image = effective.get("media_image", "")
        if media_image:
            self.attributes[Attributes.MEDIA_IMAGE_URL] = self._make_unique_image_url(
                media_image
            )
        elif self._pending_channel:
            self.attributes[Attributes.MEDIA_IMAGE_URL] = ""

        self.attributes[Attributes.SOURCE] = channel_name

        start_time = effective.get("start_time")
        end_time = effective.get("end_time")

        if start_time and end_time:
            pos, dur = self._horizon_device.calculate_position_duration(
                start_time, end_time
            )
            self.attributes[Attributes.MEDIA_POSITION] = pos
            self.attributes[Attributes.MEDIA_DURATION] = dur
        else:
            self.attributes[Attributes.MEDIA_POSITION] = 0
            self.attributes[Attributes.MEDIA_DURATION] = 0

        if not self._sources_loaded and self._horizon_device.channels_loaded:
            await self._load_sources()

        self._api.configured_entities.update_attributes(self.id, self.attributes)

        sensor_state = {
            "state": horizon_state,
            "channel": channel_name,
            "media_title": program_title,
        }
        for sensor in self._sensors:
            await sensor.update_state(sensor_state)
