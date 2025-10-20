"""
Media Player entity for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

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
        """
        Initialize Horizon Media Player entity.

        :param device_id: Unique device identifier
        :param device_name: Device display name
        :param client: Horizon API client
        :param api: Integration API instance
        """
        self._device_id = device_id
        self._client = client
        self._api = api

        # Media player features - all using Commands enum (no Buttons here)
        features = [
            Features.ON_OFF,
            Features.TOGGLE,
            Features.VOLUME_UP_DOWN,
            Features.MUTE_TOGGLE,
            Features.PLAY_PAUSE,  # This is a Features constant - OK
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
        }

        super().__init__(
            identifier=device_id,
            name=device_name,
            features=features,
            attributes=attributes,
            cmd_handler=self._handle_command,
        )

        _LOG.info("Initialized Horizon Media Player: %s (%s)", device_name, device_id)

    async def _handle_command(self, entity, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        """
        Handle media player commands.

        :param entity: Entity instance
        :param cmd_id: Command identifier
        :param params: Command parameters
        :return: Status code
        """
        _LOG.info("Media Player command: %s (params=%s)", cmd_id, params)

        try:
            if cmd_id == Commands.ON:
                await self._client.power_on(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                
            elif cmd_id == Commands.OFF:
                await self._client.power_off(self._device_id)
                self.attributes[Attributes.STATE] = States.STANDBY
                
            elif cmd_id == Commands.TOGGLE:
                current_state = self.attributes.get(Attributes.STATE)
                if current_state in [States.ON, States.PLAYING, States.PAUSED]:
                    await self._client.power_off(self._device_id)
                    self.attributes[Attributes.STATE] = States.STANDBY
                else:
                    await self._client.power_on(self._device_id)
                    self.attributes[Attributes.STATE] = States.ON

            elif cmd_id == Commands.PLAY_PAUSE:  # Commands.PLAY_PAUSE exists - OK
                current_state = self.attributes.get(Attributes.STATE)
                if current_state == States.PLAYING:
                    await self._client.pause(self._device_id)
                    self.attributes[Attributes.STATE] = States.PAUSED
                else:
                    await self._client.play(self._device_id)
                    self.attributes[Attributes.STATE] = States.PLAYING
                
            elif cmd_id == Commands.STOP:
                await self._client.stop(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                
            elif cmd_id == Commands.NEXT:
                await self._client.next_channel(self._device_id)
                
            elif cmd_id == Commands.PREVIOUS:
                await self._client.previous_channel(self._device_id)
                
            elif cmd_id == Commands.FAST_FORWARD:
                await self._client.fast_forward(self._device_id)
                
            elif cmd_id == Commands.REWIND:
                await self._client.rewind(self._device_id)
                
            elif cmd_id == Commands.RECORD:
                await self._client.record(self._device_id)

            elif cmd_id == Commands.VOLUME_UP:
                await self._client.send_key(self._device_id, "VolumeUp")
                
            elif cmd_id == Commands.VOLUME_DOWN:
                await self._client.send_key(self._device_id, "VolumeDown")
                
            elif cmd_id == Commands.MUTE_TOGGLE:
                await self._client.send_key(self._device_id, "Mute")
                muted = self.attributes.get(Attributes.MUTED, False)
                self.attributes[Attributes.MUTED] = not muted

            elif cmd_id == Commands.CURSOR_UP:
                await self._client.send_key(self._device_id, "Up")
                
            elif cmd_id == Commands.CURSOR_DOWN:
                await self._client.send_key(self._device_id, "Down")
                
            elif cmd_id == Commands.CURSOR_LEFT:
                await self._client.send_key(self._device_id, "Left")
                
            elif cmd_id == Commands.CURSOR_RIGHT:
                await self._client.send_key(self._device_id, "Right")
                
            elif cmd_id == Commands.CURSOR_ENTER:
                await self._client.send_key(self._device_id, "Select")

            elif cmd_id == Commands.HOME:
                await self._client.send_key(self._device_id, "Home")
                
            elif cmd_id == Commands.MENU:
                await self._client.send_key(self._device_id, "Menu")
                
            elif cmd_id == Commands.CONTEXT_MENU:
                await self._client.send_key(self._device_id, "Options")
                
            elif cmd_id == Commands.GUIDE:
                await self._client.send_key(self._device_id, "Guide")
                
            elif cmd_id == Commands.INFO:
                await self._client.send_key(self._device_id, "Info")
                
            elif cmd_id == Commands.BACK:
                await self._client.send_key(self._device_id, "Back")

            elif cmd_id == Commands.CHANNEL_UP:
                await self._client.next_channel(self._device_id)
                
            elif cmd_id == Commands.CHANNEL_DOWN:
                await self._client.previous_channel(self._device_id)
                
            elif cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    channel = params["source"]
                    await self._client.set_channel(self._device_id, channel)
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
        """Push entity state update to Remote."""
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
            
            self._api.configured_entities.update_attributes(
                self.id,
                self.attributes
            )
            _LOG.debug("Pushed update for %s: state=%s", self.id, self.attributes[Attributes.STATE])