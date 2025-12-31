"""
Media Player entity for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from ucapi import EntityTypes, MediaPlayer, StatusCodes
from ucapi.media_player import Attributes, Commands, Features, States

from uc_intg_horizon.client import HorizonClient

_LOG = logging.getLogger(__name__)


class HorizonMediaPlayer(MediaPlayer):

    def __init__(
        self,
        device_id: str,
        device_name: str,
        client: HorizonClient,
        api,
    ):
        self._device_id = device_id
        self._client = client
        self._api = api
        self._refresh_task = None

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

    async def _load_sources(self):
        try:
            sources = await self._client.get_sources(self._device_id)
            source_list = [source["name"] for source in sources]
            self.attributes[Attributes.SOURCE_LIST] = source_list
            _LOG.info(f"Loaded {len(source_list)} sources for {self._device_id}")
        except Exception as e:
            _LOG.error(f"Failed to load sources: {e}")

    async def _start_periodic_refresh(self):
        _LOG.info(f"Starting 15-second periodic refresh for {self._device_id}")
        
        await asyncio.sleep(15)
        
        while True:
            try:
                if self._api and self._api.configured_entities.contains(self.id):
                    _LOG.debug(f"Periodic refresh triggered for {self._device_id}")
                    await self.push_update()
                
                await asyncio.sleep(15)
                
            except asyncio.CancelledError:
                _LOG.info(f"Periodic refresh stopped for {self._device_id}")
                break
            except Exception as e:
                _LOG.error(f"Error in periodic refresh for {self._device_id}: {e}")
                await asyncio.sleep(15)

    async def _handle_command(self, entity, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        _LOG.info("Media Player command: %s (params=%s)", cmd_id, params)

        is_power_command = False
        is_channel_command = False

        try:
            if cmd_id == Commands.ON:
                _LOG.info("Media Player: Powering on")
                await self._client.power_on(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                is_power_command = True
                
            elif cmd_id == Commands.OFF:
                _LOG.info("Media Player: Powering off")
                await self._client.power_off(self._device_id)
                self.attributes[Attributes.STATE] = States.STANDBY
                is_power_command = True
                
            elif cmd_id == Commands.TOGGLE:
                _LOG.info("Media Player: Toggling power")
                await self._client.power_toggle(self._device_id)
                current_state = self.attributes.get(Attributes.STATE)
                if current_state in [States.ON, States.PLAYING, States.PAUSED]:
                    self.attributes[Attributes.STATE] = States.STANDBY
                else:
                    self.attributes[Attributes.STATE] = States.ON
                is_power_command = True

            elif cmd_id == Commands.PLAY_PAUSE:
                _LOG.info("Media Player: Play/Pause toggle")
                await self._client.play_pause_toggle(self._device_id)
                current_state = self.attributes.get(Attributes.STATE)
                if current_state == States.PLAYING:
                    self.attributes[Attributes.STATE] = States.PAUSED
                else:
                    self.attributes[Attributes.STATE] = States.PLAYING
                
            elif cmd_id == Commands.STOP:
                _LOG.info("Media Player: Stop")
                await self._client.stop(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                
            elif cmd_id == Commands.NEXT:
                _LOG.info("Media Player: Next channel")
                await self._client.next_channel(self._device_id)
                is_channel_command = True
                
            elif cmd_id == Commands.PREVIOUS:
                _LOG.info("Media Player: Previous channel")
                await self._client.previous_channel(self._device_id)
                is_channel_command = True
                
            elif cmd_id == Commands.FAST_FORWARD:
                _LOG.info("Media Player: Fast forward")
                await self._client.fast_forward(self._device_id)
                
            elif cmd_id == Commands.REWIND:
                _LOG.info("Media Player: Rewind")
                await self._client.rewind(self._device_id)
                
            elif cmd_id == Commands.RECORD:
                _LOG.info("Media Player: Record -> MediaRecord")
                await self._client.send_key(self._device_id, "MediaRecord")

            elif cmd_id == Commands.VOLUME_UP:
                _LOG.info("Media Player: Volume up -> VolumeUp")
                await self._client.send_key(self._device_id, "VolumeUp")
                
            elif cmd_id == Commands.VOLUME_DOWN:
                _LOG.info("Media Player: Volume down -> VolumeDown")
                await self._client.send_key(self._device_id, "VolumeDown")
                
            elif cmd_id == Commands.MUTE_TOGGLE:
                _LOG.info("Media Player: Mute toggle -> VolumeMute")
                await self._client.send_key(self._device_id, "VolumeMute")
                muted = self.attributes.get(Attributes.MUTED, False)
                self.attributes[Attributes.MUTED] = not muted

            elif cmd_id == Commands.CURSOR_UP:
                _LOG.info("Media Player: Cursor up -> ArrowUp")
                await self._client.send_key(self._device_id, "ArrowUp")
                
            elif cmd_id == Commands.CURSOR_DOWN:
                _LOG.info("Media Player: Cursor down -> ArrowDown")
                await self._client.send_key(self._device_id, "ArrowDown")
                
            elif cmd_id == Commands.CURSOR_LEFT:
                _LOG.info("Media Player: Cursor left -> ArrowLeft")
                await self._client.send_key(self._device_id, "ArrowLeft")
                
            elif cmd_id == Commands.CURSOR_RIGHT:
                _LOG.info("Media Player: Cursor right -> ArrowRight")
                await self._client.send_key(self._device_id, "ArrowRight")
                
            elif cmd_id == Commands.CURSOR_ENTER:
                _LOG.info("Media Player: Cursor enter -> Enter")
                await self._client.send_key(self._device_id, "Enter")

            elif cmd_id == Commands.HOME:
                _LOG.info("Media Player: Home -> MediaTopMenu")
                await self._client.send_key(self._device_id, "MediaTopMenu")
                
            elif cmd_id == Commands.MENU:
                _LOG.info("Media Player: Menu -> Info")
                await self._client.send_key(self._device_id, "Info")
                
            elif cmd_id == Commands.CONTEXT_MENU:
                _LOG.info("Media Player: Context menu -> Options")
                await self._client.send_key(self._device_id, "Options")
                
            elif cmd_id == Commands.GUIDE:
                _LOG.info("Media Player: Guide -> Guide")
                await self._client.send_key(self._device_id, "Guide")
                
            elif cmd_id == Commands.INFO:
                _LOG.info("Media Player: Info -> Info")
                await self._client.send_key(self._device_id, "Info")
                
            elif cmd_id == Commands.BACK:
                _LOG.info("Media Player: Back -> Escape")
                await self._client.send_key(self._device_id, "Escape")

            elif cmd_id == Commands.CHANNEL_UP:
                _LOG.info("Media Player: Channel up")
                await self._client.next_channel(self._device_id)
                is_channel_command = True
                
            elif cmd_id == Commands.CHANNEL_DOWN:
                _LOG.info("Media Player: Channel down")
                await self._client.previous_channel(self._device_id)
                is_channel_command = True
                
            elif cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    source = params["source"]
                    _LOG.info(f"Media Player: Select source: {source}")
                    
                    if source.startswith("HDMI") or source == "AV Input":
                        await self._client.send_key(self._device_id, "Settings")
                        _LOG.info("Opened settings for input selection")
                    elif source in ["Netflix", "BBC iPlayer", "ITVX", "All 4", "My5", "Prime Video", "YouTube", "Disney+"]:
                        await self._client.play_media(self._device_id, "app", source)
                        _LOG.info(f"Launched app: {source}")
                    else:
                        await self._client.set_channel(self._device_id, source)
                        is_channel_command = True
                    
                    self.attributes[Attributes.SOURCE] = source
                else:
                    _LOG.warning("SELECT_SOURCE called without source parameter")
                    return StatusCodes.BAD_REQUEST

            elif cmd_id == "my_recordings":
                _LOG.info("Media Player: My Recordings -> Recordings")
                await self._client.send_key(self._device_id, "Recordings")

            elif cmd_id.startswith("channel_select:"):
                channel = cmd_id.split(":", 1)[1]
                _LOG.info(f"Media Player: Channel select -> {channel}")
                await self._client.set_channel(self._device_id, channel)
                is_channel_command = True

            else:
                _LOG.warning("Unsupported command: %s", cmd_id)
                return StatusCodes.NOT_IMPLEMENTED

            if is_power_command:
                _LOG.debug("Power command - waiting 3s for MQTT state update...")
                await asyncio.sleep(3.0)
            elif is_channel_command:
                _LOG.debug("Channel command - waiting 2.5s for MQTT state update...")
                await asyncio.sleep(2.5)
            
            await self.push_update()
            return StatusCodes.OK

        except Exception as e:
            _LOG.error("Error handling command %s: %s", cmd_id, e, exc_info=True)
            return StatusCodes.SERVER_ERROR

    def _calculate_position_duration(self, start_time, end_time, position=None):
        try:
            if position is not None:
                if start_time and end_time:
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
                
                _LOG.debug(
                    "Calculated position: %d/%d seconds (%.1f%%)",
                    position_seconds,
                    duration_seconds,
                    (position_seconds / duration_seconds * 100) if duration_seconds > 0 else 0
                )
                
                return (position_seconds, duration_seconds)
                
        except Exception as e:
            _LOG.debug("Could not calculate position/duration: %s", e)
        
        return (0, 0)

    def _make_unique_image_url(self, base_url: str) -> str:
        """
        Add unique query parameter to image URL to force refresh in R3 firmware.
        
        R3 firmware requires unique URLs for artwork to refresh properly.
        We append a timestamp-based dummy parameter to make each URL unique.
        
        :param base_url: Original image URL
        :return: URL with unique query parameter
        """
        if not base_url:
            return base_url
            
        separator = "&" if "?" in base_url else "?"
        timestamp = int(time.time() * 1000)
        unique_url = f"{base_url}{separator}_t={timestamp}"
        
        _LOG.debug("Artwork URL: %s -> %s", base_url[:50], unique_url[:70])
        return unique_url

    async def push_update(self) -> None:
        if self._api and self._api.configured_entities.contains(self.id):
            device_state = await self._client.get_device_state(self._device_id)
            horizon_state = device_state.get("state", "unavailable")
            
            if horizon_state == "ONLINE_RUNNING":
                self.attributes[Attributes.STATE] = States.PLAYING
            elif horizon_state == "ONLINE_STANDBY":
                self.attributes[Attributes.STATE] = States.STANDBY
            elif horizon_state in ["OFFLINE", "OFFLINE_NETWORK_STANDBY"]:
                self.attributes[Attributes.STATE] = States.OFF
            else:
                self.attributes[Attributes.STATE] = States.UNAVAILABLE
            
            channel_name = device_state.get("channel", "")
            program_title = device_state.get("media_title", "")
            
            if program_title:
                self.attributes[Attributes.MEDIA_TITLE] = program_title
                self.attributes[Attributes.MEDIA_ARTIST] = channel_name
                
                _LOG.debug(
                    "Media display - Line 1: '%s', Line 2: '%s'",
                    program_title,
                    channel_name
                )
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
                
                _LOG.debug(
                    "Seek bar - Position: %d/%d seconds (%.1f%%)",
                    pos,
                    dur,
                    (pos / dur * 100) if dur > 0 else 0
                )
            else:
                self.attributes[Attributes.MEDIA_POSITION] = 0
                self.attributes[Attributes.MEDIA_DURATION] = 0
            
            self._api.configured_entities.update_attributes(self.id, self.attributes)
            _LOG.debug("Pushed update for %s: %s", self.id, self.attributes[Attributes.STATE])