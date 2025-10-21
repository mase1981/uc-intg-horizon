"""
Media Player entity for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any

from ucapi import EntityTypes, MediaPlayer, StatusCodes
from ucapi.media_player import Attributes, Commands, Features, States

from uc_intg_horizon.client import HorizonClient

_LOG = logging.getLogger(__name__)


class HorizonMediaPlayer(MediaPlayer):
    """Horizon Media Player entity implementation."""

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
            Features.MEDIA_IMAGE_URL,
        ]

        attributes = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.MEDIA_TITLE: "",
            Attributes.MEDIA_IMAGE_URL: "",
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

    async def _load_sources(self):
        try:
            sources = await self._client.get_sources(self._device_id)
            source_list = [source["name"] for source in sources]
            self.attributes[Attributes.SOURCE_LIST] = source_list
            _LOG.info(f"Loaded {len(source_list)} sources for {self._device_id}")
        except Exception as e:
            _LOG.error(f"Failed to load sources: {e}")

    async def _handle_command(self, entity, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        _LOG.info("Media Player command: %s (params=%s)", cmd_id, params)

        try:
            if cmd_id == Commands.ON:
                _LOG.info("Media Player: Powering on")
                await self._client.power_on(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                
            elif cmd_id == Commands.OFF:
                _LOG.info("Media Player: Powering off")
                await self._client.power_off(self._device_id)
                self.attributes[Attributes.STATE] = States.STANDBY
                
            elif cmd_id == Commands.TOGGLE:
                _LOG.info("Media Player: Toggling power")
                await self._client.power_toggle(self._device_id)
                current_state = self.attributes.get(Attributes.STATE)
                if current_state in [States.ON, States.PLAYING, States.PAUSED]:
                    self.attributes[Attributes.STATE] = States.STANDBY
                else:
                    self.attributes[Attributes.STATE] = States.ON

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
                
            elif cmd_id == Commands.PREVIOUS:
                _LOG.info("Media Player: Previous channel")
                await self._client.previous_channel(self._device_id)
                
            elif cmd_id == Commands.FAST_FORWARD:
                _LOG.info("Media Player: Fast forward")
                await self._client.fast_forward(self._device_id)
                
            elif cmd_id == Commands.REWIND:
                _LOG.info("Media Player: Rewind")
                await self._client.rewind(self._device_id)
                
            elif cmd_id == Commands.RECORD:
                _LOG.info("Media Player: Record")
                await self._client.record(self._device_id)

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
                
            elif cmd_id == Commands.CHANNEL_DOWN:
                _LOG.info("Media Player: Channel down")
                await self._client.previous_channel(self._device_id)
                
            elif cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    source = params["source"]
                    _LOG.info(f"Media Player: Select source: {source}")
                    
                    if source.startswith("HDMI"):
                        await self._client.send_key(self._device_id, "Settings")
                        _LOG.info("Opened settings for HDMI input selection")
                    elif source in ["Netflix", "BBC iPlayer", "ITVX", "All 4", "My5", "Prime Video", "YouTube", "Disney+"]:
                        await self._client.send_key(self._device_id, "Menu")
                        _LOG.info(f"Opened menu to navigate to {source}")
                    else:
                        await self._client.set_channel(self._device_id, source)
                    
                    self.attributes[Attributes.SOURCE] = source
                else:
                    _LOG.warning("SELECT_SOURCE called without source parameter")
                    return StatusCodes.BAD_REQUEST

            else:
                _LOG.warning("Unsupported command: %s", cmd_id)
                return StatusCodes.NOT_IMPLEMENTED

            await self.push_update()
            return StatusCodes.OK

        except Exception as e:
            _LOG.error("Error handling command %s: %s", cmd_id, e, exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def push_update(self) -> None:
        if self._api and self._api.configured_entities.contains(self.id):
            device_state = await self._client.get_device_state(self._device_id)
            horizon_state = device_state.get("state", "unavailable")
            
            if horizon_state == "ONLINE_RUNNING":
                self.attributes[Attributes.STATE] = States.PLAYING
            elif horizon_state == "ONLINE_STANDBY":
                self.attributes[Attributes.STATE] = States.STANDBY
            elif horizon_state == "OFFLINE":
                self.attributes[Attributes.STATE] = States.OFF
            else:
                self.attributes[Attributes.STATE] = States.UNAVAILABLE
            
            if device_state.get("channel"):
                channel_name = device_state.get("channel", "")
                program_title = device_state.get("media_title", "")
                
                if program_title:
                    self.attributes[Attributes.MEDIA_TITLE] = f"{channel_name} - {program_title}"
                else:
                    self.attributes[Attributes.MEDIA_TITLE] = channel_name
            
            if device_state.get("media_image"):
                self.attributes[Attributes.MEDIA_IMAGE_URL] = device_state["media_image"]
            
            self._api.configured_entities.update_attributes(self.id, self.attributes)
            _LOG.debug("Pushed update for %s: %s", self.id, self.attributes[Attributes.STATE])