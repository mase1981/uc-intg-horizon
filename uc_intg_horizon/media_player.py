"""
Media Player entity for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, TYPE_CHECKING

from ucapi import MediaPlayer, StatusCodes
from ucapi.media_player import Attributes, Commands, Features, States

if TYPE_CHECKING:
    import ucapi
    from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)


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
        """Initialize the media player entity."""
        self._device_id = device_id
        self._horizon_device = horizon_device
        self._api = api
        self._sensors = sensors or []
        self._refresh_task: asyncio.Task | None = None
        self._channel_update_task: asyncio.Task | None = None

        features = [
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
        ]

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
            features=features,
            attributes=attributes,
            cmd_handler=self._handle_command,
        )

        _LOG.info("Initialized Horizon Media Player: %s (%s)", device_name, device_id)

        asyncio.create_task(self._load_sources())
        asyncio.create_task(self._start_periodic_refresh())

    async def _load_sources(self) -> None:
        """Load available sources (channels)."""
        try:
            channels = await self._horizon_device.get_channels()
            source_list = [ch["name"] for ch in channels]
            self.attributes[Attributes.SOURCE_LIST] = source_list
            _LOG.info("Loaded %d sources for %s", len(source_list), self._device_id)
        except Exception as e:
            _LOG.error("Failed to load sources: %s", e)

    async def _start_periodic_refresh(self) -> None:
        """Start periodic state refresh."""
        _LOG.info("Starting 15-second periodic refresh for %s", self._device_id)

        await asyncio.sleep(15)

        while True:
            try:
                if self._api and self._api.configured_entities.contains(self.id):
                    _LOG.debug("Periodic refresh for %s", self._device_id)
                    await self.push_update()

                await asyncio.sleep(15)

            except asyncio.CancelledError:
                _LOG.info("Periodic refresh stopped for %s", self._device_id)
                break
            except Exception as e:
                _LOG.error("Error in periodic refresh for %s: %s", self._device_id, e)
                await asyncio.sleep(15)

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle media player commands."""
        _LOG.info("Media Player command: %s (params=%s)", cmd_id, params)

        is_power_command = False
        is_channel_command = False

        try:
            if cmd_id == Commands.ON:
                await self._horizon_device.power_on(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                is_power_command = True

            elif cmd_id == Commands.OFF:
                await self._horizon_device.power_off(self._device_id)
                self.attributes[Attributes.STATE] = States.STANDBY
                is_power_command = True

            elif cmd_id == Commands.TOGGLE:
                await self._horizon_device.power_toggle(self._device_id)
                current_state = self.attributes.get(Attributes.STATE)
                if current_state in [States.ON, States.PLAYING, States.PAUSED]:
                    self.attributes[Attributes.STATE] = States.STANDBY
                else:
                    self.attributes[Attributes.STATE] = States.ON
                is_power_command = True

            elif cmd_id == Commands.PLAY_PAUSE:
                state = await self._horizon_device.get_device_state(self._device_id)
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
                is_channel_command = True

            elif cmd_id == Commands.PREVIOUS:
                await self._horizon_device.previous_channel(self._device_id)
                is_channel_command = True

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
                else:
                    _LOG.warning("SEEK called without media_position parameter")
                    return StatusCodes.BAD_REQUEST

            elif cmd_id == Commands.VOLUME_UP:
                await self._horizon_device.send_key(self._device_id, "VolumeUp")

            elif cmd_id == Commands.VOLUME_DOWN:
                await self._horizon_device.send_key(self._device_id, "VolumeDown")

            elif cmd_id == Commands.MUTE_TOGGLE:
                await self._horizon_device.send_key(self._device_id, "VolumeMute")
                muted = self.attributes.get(Attributes.MUTED, False)
                self.attributes[Attributes.MUTED] = not muted

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
                is_channel_command = True

            elif cmd_id == Commands.CHANNEL_DOWN:
                await self._horizon_device.previous_channel(self._device_id)
                is_channel_command = True

            elif cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    source = params["source"]
                    _LOG.info("Select source: %s", source)

                    if source.startswith("HDMI") or source == "AV Input":
                        await self._horizon_device.send_key(self._device_id, "Settings")
                    elif source in [
                        "Netflix",
                        "BBC iPlayer",
                        "ITVX",
                        "All 4",
                        "My5",
                        "Prime Video",
                        "YouTube",
                        "Disney+",
                    ]:
                        await self._horizon_device.send_key(
                            self._device_id, "MediaTopMenu"
                        )
                    else:
                        await self._horizon_device.set_channel(self._device_id, source)
                        is_channel_command = True

                    self.attributes[Attributes.SOURCE] = source
                else:
                    _LOG.warning("SELECT_SOURCE called without source parameter")
                    return StatusCodes.BAD_REQUEST

            elif cmd_id == "my_recordings":
                await self._horizon_device.send_key(self._device_id, "Recordings")

            elif cmd_id.startswith("channel_select:"):
                channel = cmd_id.split(":", 1)[1]
                await self._horizon_device.set_channel_by_number(self._device_id, channel)
                is_channel_command = True

            else:
                _LOG.warning("Unsupported command: %s", cmd_id)
                return StatusCodes.NOT_IMPLEMENTED

            if is_power_command:
                await asyncio.sleep(3.0)
                await self.push_update()
            elif is_channel_command:
                if self._channel_update_task and not self._channel_update_task.done():
                    self._channel_update_task.cancel()
                self._channel_update_task = asyncio.create_task(
                    self._delayed_channel_update()
                )

            return StatusCodes.OK

        except Exception as e:
            _LOG.error("Error handling command %s: %s", cmd_id, e, exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _delayed_channel_update(self) -> None:
        """Background task to update artwork after channel change."""
        try:
            await asyncio.sleep(2.5)
            await self.push_update()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            _LOG.error("Error in delayed channel update: %s", e)

    def _calculate_position_duration(
        self,
        start_time: Any,
        end_time: Any,
        position: int | None = None,
    ) -> tuple[int, int]:
        """Calculate media position and duration."""
        try:
            if position is not None and start_time and end_time:
                if isinstance(start_time, (int, float)):
                    start_dt = datetime.fromtimestamp(start_time)
                else:
                    start_dt = datetime.fromisoformat(str(start_time))

                if isinstance(end_time, (int, float)):
                    end_dt = datetime.fromtimestamp(end_time)
                else:
                    end_dt = datetime.fromisoformat(str(end_time))

                duration = int((end_dt - start_dt).total_seconds())
                return (int(position), duration)

            if start_time and end_time:
                now = datetime.now()

                if isinstance(start_time, (int, float)):
                    start_dt = datetime.fromtimestamp(start_time)
                else:
                    start_dt = datetime.fromisoformat(str(start_time))

                if isinstance(end_time, (int, float)):
                    end_dt = datetime.fromtimestamp(end_time)
                else:
                    end_dt = datetime.fromisoformat(str(end_time))

                position_seconds = int((now - start_dt).total_seconds())
                duration_seconds = int((end_dt - start_dt).total_seconds())
                position_seconds = max(0, min(position_seconds, duration_seconds))

                return (position_seconds, duration_seconds)

        except Exception as e:
            _LOG.debug("Could not calculate position/duration: %s", e)

        return (0, 0)

    def _make_unique_image_url(self, base_url: str) -> str:
        """Add unique query parameter to force image refresh."""
        if not base_url:
            return base_url

        separator = "&" if "?" in base_url else "?"
        timestamp = int(time.time() * 1000)
        return f"{base_url}{separator}_t={timestamp}"

    async def push_update(self) -> None:
        """Push state update to UC Remote."""
        if not self._api or not self._api.configured_entities.contains(self.id):
            return

        device_state = await self._horizon_device.get_device_state(self._device_id)
        horizon_state = device_state.get("state", "unavailable")

        if horizon_state == "ONLINE_RUNNING":
            if device_state.get("paused"):
                self.attributes[Attributes.STATE] = States.PAUSED
            else:
                self.attributes[Attributes.STATE] = States.PLAYING
        elif horizon_state == "ONLINE_STANDBY":
            self.attributes[Attributes.STATE] = States.STANDBY
        elif horizon_state == "OFFLINE":
            self.attributes[Attributes.STATE] = States.OFF
        else:
            self.attributes[Attributes.STATE] = States.UNAVAILABLE

        channel_name = device_state.get("channel", "")
        program_title = device_state.get("media_title", "")

        if program_title:
            self.attributes[Attributes.MEDIA_TITLE] = program_title
            self.attributes[Attributes.MEDIA_ARTIST] = channel_name
        elif channel_name:
            self.attributes[Attributes.MEDIA_TITLE] = channel_name
            self.attributes[Attributes.MEDIA_ARTIST] = ""
        else:
            self.attributes[Attributes.MEDIA_TITLE] = ""
            self.attributes[Attributes.MEDIA_ARTIST] = ""

        if device_state.get("media_image"):
            original_url = device_state["media_image"]
            unique_url = self._make_unique_image_url(original_url)
            self.attributes[Attributes.MEDIA_IMAGE_URL] = unique_url

        start_time = device_state.get("start_time")
        end_time = device_state.get("end_time")
        position = device_state.get("position")

        if start_time and end_time:
            pos, dur = self._calculate_position_duration(start_time, end_time, position)
            self.attributes[Attributes.MEDIA_POSITION] = pos
            self.attributes[Attributes.MEDIA_DURATION] = dur
        else:
            self.attributes[Attributes.MEDIA_POSITION] = 0
            self.attributes[Attributes.MEDIA_DURATION] = 0

        self._api.configured_entities.update_attributes(self.id, self.attributes)
        _LOG.debug("Pushed update for %s: %s", self.id, self.attributes[Attributes.STATE])

        for sensor in self._sensors:
            await sensor.update_state(device_state)
