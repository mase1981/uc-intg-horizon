"""
Remote Control entity for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any

from ucapi import Remote, StatusCodes
from ucapi.remote import Attributes, Commands, Features, States
from ucapi.ui import (
    Buttons,
    Size,
    UiPage,
    create_btn_mapping,
    create_ui_icon,
    create_ui_text,
)

from uc_intg_horizon.client import HorizonClient

_LOG = logging.getLogger(__name__)


class HorizonRemote(Remote):

    def __init__(
        self,
        device_id: str,
        device_name: str,
        client: HorizonClient,
        api,
        media_player=None,
    ):
        self._device_id = device_id
        self._client = client
        self._api = api
        self._media_player = media_player
        self._digit_update_task = None

        simple_commands = [
            "POWER_ON", "POWER_OFF", "POWER_TOGGLE",
            "UP", "DOWN", "LEFT", "RIGHT", "SELECT", "BACK",
            "PLAYPAUSE", "STOP", "RECORD", "REWIND", "FASTFORWARD",
            "VOLUME_UP", "VOLUME_DOWN", "MUTE",
            "CHANNEL_UP", "CHANNEL_DOWN", "GUIDE",
            "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
            "RED", "GREEN", "YELLOW", "BLUE",
            "HOME", "TV", "MENU", "SOURCE", "DVR",
        ]

        button_mapping = [
            create_btn_mapping(Buttons.HOME, short="HOME"),
            create_btn_mapping(Buttons.BACK, short="BACK"),
            create_btn_mapping(Buttons.DPAD_UP, short="UP"),
            create_btn_mapping(Buttons.DPAD_DOWN, short="DOWN"),
            create_btn_mapping(Buttons.DPAD_LEFT, short="LEFT"),
            create_btn_mapping(Buttons.DPAD_RIGHT, short="RIGHT"),
            create_btn_mapping(Buttons.DPAD_MIDDLE, short="SELECT"),
            create_btn_mapping(Buttons.VOLUME_UP, short="VOLUME_UP"),
            create_btn_mapping(Buttons.VOLUME_DOWN, short="VOLUME_DOWN"),
            create_btn_mapping(Buttons.MUTE, short="MUTE"),
            create_btn_mapping(Buttons.CHANNEL_UP, short="CHANNEL_UP"),
            create_btn_mapping(Buttons.CHANNEL_DOWN, short="CHANNEL_DOWN"),
            create_btn_mapping(Buttons.PLAY, short="PLAYPAUSE"),
            create_btn_mapping(Buttons.STOP, short="STOP"),
            create_btn_mapping(Buttons.RECORD, short="RECORD"),
            create_btn_mapping(Buttons.PREV, short="REWIND"),
            create_btn_mapping(Buttons.NEXT, short="FASTFORWARD"),
            create_btn_mapping(Buttons.RED, short="RED"),
            create_btn_mapping(Buttons.GREEN, short="GREEN"),
            create_btn_mapping(Buttons.YELLOW, short="YELLOW"),
            create_btn_mapping(Buttons.BLUE, short="BLUE"),
        ]

        ui_pages = [
            self._create_main_page(),
            self._create_numbers_page(),
            self._create_playback_page(),
            self._create_colors_page(),
        ]

        features = [Features.ON_OFF, Features.TOGGLE, Features.SEND_CMD]
        attributes = {Attributes.STATE: States.UNAVAILABLE}

        super().__init__(
            identifier=f"{device_id}_remote",
            name=f"{device_name} Remote",
            features=features,
            attributes=attributes,
            simple_commands=simple_commands,
            button_mapping=button_mapping,
            ui_pages=ui_pages,
            cmd_handler=self._handle_command,
        )

        _LOG.info("Initialized Horizon Remote: %s (%s)", device_name, device_id)
        
        asyncio.create_task(self._start_periodic_refresh())

    async def _start_periodic_refresh(self):
        _LOG.info(f"Starting 15-second periodic refresh for remote {self._device_id}")
        
        await asyncio.sleep(5)
        
        while True:
            try:
                if self._api and self._api.configured_entities.contains(self.id):
                    _LOG.debug(f"Periodic refresh triggered for remote {self._device_id}")
                    await self.push_update()
                
                await asyncio.sleep(15)
                
            except asyncio.CancelledError:
                _LOG.info(f"Periodic refresh stopped for remote {self._device_id}")
                break
            except Exception as e:
                _LOG.error(f"Error in periodic refresh for remote {self._device_id}: {e}")
                await asyncio.sleep(15)

    def _create_main_page(self) -> UiPage:
        page = UiPage("main", "Main Control", grid=Size(4, 6))
        
        page.add(create_ui_text("ON", 0, 0, cmd="POWER_ON"))
        page.add(create_ui_text("OFF", 1, 0, cmd="POWER_OFF"))
        page.add(create_ui_text("TV", 2, 0, cmd="TV"))
        page.add(create_ui_text("SRC", 3, 0, cmd="SOURCE"))
        
        page.add(create_ui_icon("uc:up-arrow", 1, 1, cmd="UP"))
        page.add(create_ui_icon("uc:left-arrow", 0, 2, cmd="LEFT"))
        page.add(create_ui_text("OK", 1, 2, size=Size(2, 1), cmd="SELECT"))
        page.add(create_ui_icon("uc:right-arrow", 3, 2, cmd="RIGHT"))
        page.add(create_ui_icon("uc:down-arrow", 1, 3, cmd="DOWN"))
        
        page.add(create_ui_text("P/P", 0, 4, size=Size(2, 1), cmd="PLAYPAUSE"))
        page.add(create_ui_icon("uc:stop", 2, 4, cmd="STOP"))
        page.add(create_ui_text("REC", 3, 4, cmd="RECORD"))
        
        page.add(create_ui_icon("uc:home", 0, 5, cmd="HOME"))
        page.add(create_ui_icon("uc:back", 1, 5, cmd="BACK"))
        page.add(create_ui_icon("uc:menu", 2, 5, cmd="MENU"))
        page.add(create_ui_icon("uc:guide", 3, 5, cmd="GUIDE"))
        
        return page

    def _create_numbers_page(self) -> UiPage:
        page = UiPage("numbers", "Channel Numbers", grid=Size(4, 6))
        
        page.add(create_ui_text("1", 0, 1, cmd="1"))
        page.add(create_ui_text("2", 1, 1, cmd="2"))
        page.add(create_ui_text("3", 2, 1, cmd="3"))
        page.add(create_ui_text("4", 0, 2, cmd="4"))
        page.add(create_ui_text("5", 1, 2, cmd="5"))
        page.add(create_ui_text("6", 2, 2, cmd="6"))
        page.add(create_ui_text("7", 0, 3, cmd="7"))
        page.add(create_ui_text("8", 1, 3, cmd="8"))
        page.add(create_ui_text("9", 2, 3, cmd="9"))
        page.add(create_ui_text("0", 1, 4, cmd="0"))
        
        page.add(create_ui_icon("uc:up-arrow", 3, 1, cmd="CHANNEL_UP"))
        page.add(create_ui_icon("uc:down-arrow", 3, 2, cmd="CHANNEL_DOWN"))
        page.add(create_ui_text("OK", 0, 5, size=Size(2, 1), cmd="SELECT"))
        
        return page

    def _create_playback_page(self) -> UiPage:
        page = UiPage("playback", "Playback", grid=Size(4, 6))
        
        page.add(create_ui_icon("uc:prev", 0, 1, size=Size(2, 2), cmd="REWIND"))
        page.add(create_ui_icon("uc:next", 2, 1, size=Size(2, 2), cmd="FASTFORWARD"))
        
        page.add(create_ui_text("P/P", 0, 3, size=Size(2, 2), cmd="PLAYPAUSE"))
        page.add(create_ui_icon("uc:stop", 2, 3, cmd="STOP"))
        page.add(create_ui_text("REC", 3, 3, cmd="RECORD"))
        
        page.add(create_ui_text("VOL+", 0, 5, cmd="VOLUME_UP"))
        page.add(create_ui_text("VOL-", 1, 5, cmd="VOLUME_DOWN"))
        page.add(create_ui_text("MUTE", 2, 5, size=Size(2, 1), cmd="MUTE"))
        
        return page

    def _create_colors_page(self) -> UiPage:
        page = UiPage("colors", "Color Buttons", grid=Size(4, 6))
        
        page.add(create_ui_text("RED", 0, 1, size=Size(2, 2), cmd="RED"))
        page.add(create_ui_text("GREEN", 2, 1, size=Size(2, 2), cmd="GREEN"))
        page.add(create_ui_text("YELLOW", 0, 3, size=Size(2, 2), cmd="YELLOW"))
        page.add(create_ui_text("BLUE", 2, 3, size=Size(2, 2), cmd="BLUE"))
        page.add(create_ui_icon("uc:guide", 1, 5, size=Size(2, 1), cmd="GUIDE"))
        
        return page

    async def _handle_command(self, entity, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        _LOG.info("Remote command: %s (params=%s)", cmd_id, params)

        is_power_command = False

        try:
            if cmd_id == Commands.ON:
                await self._client.power_on(self._device_id)
                self.attributes[Attributes.STATE] = States.ON
                is_power_command = True
                
            elif cmd_id == Commands.OFF:
                await self._client.power_off(self._device_id)
                self.attributes[Attributes.STATE] = States.OFF
                is_power_command = True
                
            elif cmd_id == Commands.TOGGLE:
                await self._client.power_toggle(self._device_id)
                current_state = self.attributes.get(Attributes.STATE)
                if current_state == States.ON:
                    self.attributes[Attributes.STATE] = States.OFF
                else:
                    self.attributes[Attributes.STATE] = States.ON
                is_power_command = True
                    
            elif cmd_id == Commands.SEND_CMD:
                command = params.get("command") if params else None
                if command:
                    _LOG.info(f"SEND_CMD received: {command}")
                    is_power_command = await self._send_simple_command(command)
                else:
                    _LOG.warning("SEND_CMD without command parameter")
                    return StatusCodes.BAD_REQUEST
                    
            else:
                _LOG.warning("Unsupported command: %s", cmd_id)
                return StatusCodes.NOT_IMPLEMENTED

            # CRITICAL FIX: Only delay for power commands
            if is_power_command:
                _LOG.debug("Power command - waiting 3s for MQTT state update...")
                await asyncio.sleep(3.0)
            # NO DELAY for channel changes - periodic refresh handles updates
            
            await self.push_update()
            return StatusCodes.OK

        except Exception as e:
            _LOG.error("Error handling command %s: %s", cmd_id, e, exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _send_simple_command(self, command: str) -> bool:
        """
        Send a simple command and return True if it's a power command.
        
        Returns:
            bool: True if power command, False otherwise
        """
        _LOG.info(f"Processing simple command: {command}")
        
        is_power_command = False
        
        if command.startswith("channel_select:"):
            channel = command.split(":", 1)[1]
            _LOG.info(f"Channel select command: {channel}")
            await self._client.set_channel(self._device_id, channel)
            return False
        
        if command == "POWER_ON":
            _LOG.info("Calling power_on()")
            await self._client.power_on(self._device_id)
            return True
            
        elif command == "POWER_OFF":
            _LOG.info("Calling power_off()")
            await self._client.power_off(self._device_id)
            return True
            
        elif command == "POWER_TOGGLE":
            _LOG.info("Calling power_toggle()")
            await self._client.power_toggle(self._device_id)
            return True
            
        elif command == "PLAYPAUSE":
            _LOG.info("Calling play_pause_toggle()")
            await self._client.play_pause_toggle(self._device_id)
            return False
        
        elif command == "RECORD":
            _LOG.info("Sending MediaRecord key")
            await self._client.send_key(self._device_id, "MediaRecord")
            return False
        
        elif command == "DVR":
            _LOG.info("Sending DVR key")
            await self._client.send_key(self._device_id, "DVR")
            return False
        
        command_map = {
            "UP": "ArrowUp",
            "DOWN": "ArrowDown",
            "LEFT": "ArrowLeft",
            "RIGHT": "ArrowRight",
            "SELECT": "Enter",
            "BACK": "Escape",
            "STOP": "MediaStop",
            "REWIND": "MediaRewind",
            "FASTFORWARD": "MediaFastForward",
            "VOLUME_UP": "VolumeUp",
            "VOLUME_DOWN": "VolumeDown",
            "MUTE": "VolumeMute",
            "CHANNEL_UP": "ChannelUp",
            "CHANNEL_DOWN": "ChannelDown",
            "GUIDE": "Guide",
            "RED": "Red",
            "GREEN": "Green",
            "YELLOW": "Yellow",
            "BLUE": "Blue",
            "HOME": "MediaTopMenu",
            "TV": "TV",
            "MENU": "ContextMenu",
            "SOURCE": "Settings",
            "DVR": "DVR",
        }
        
        for i in range(10):
            command_map[str(i)] = str(i)
        
        horizon_key = command_map.get(command)
        
        if not horizon_key:
            _LOG.warning(f"Unknown command: {command}")
            return False
        
        _LOG.info(f"Sending: {command} -> {horizon_key}")
        await self._client.send_key(self._device_id, horizon_key)
        
        # Digit entry still uses delayed media player update
        if command in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            if self._digit_update_task and not self._digit_update_task.done():
                self._digit_update_task.cancel()
            
            self._digit_update_task = asyncio.create_task(self._delayed_digit_update())
        
        return False

    async def _delayed_digit_update(self):
        """Wait 2 seconds after last digit press, then update media player."""
        try:
            await asyncio.sleep(2.0)
            _LOG.info("Digit entry complete (2s timeout) - updating media player")
            if self._media_player:
                await self._media_player.push_update()
        except asyncio.CancelledError:
            _LOG.debug("Digit update cancelled - new digit pressed")
            raise

    async def push_update(self) -> None:
        if self._api and self._api.configured_entities.contains(self.id):
            device_state = await self._client.get_device_state(self._device_id)
            horizon_state = device_state.get("state", "unavailable")
            
            _LOG.debug(f"Remote device state for {self._device_id}: {horizon_state}")
            
            if horizon_state == "ONLINE_RUNNING":
                self.attributes[Attributes.STATE] = States.ON
            elif horizon_state == "ONLINE_STANDBY":
                self.attributes[Attributes.STATE] = States.OFF
            elif horizon_state in ["OFFLINE", "OFFLINE_NETWORK_STANDBY"]:
                self.attributes[Attributes.STATE] = States.OFF
                _LOG.debug(f"{self.id} - Device is OFF (state: {horizon_state})")
            else:
                self.attributes[Attributes.STATE] = States.UNAVAILABLE
                _LOG.warning(f"{self.id} - Device is UNAVAILABLE (no MQTT communication)")
            
            self._api.configured_entities.update_attributes(self.id, self.attributes)
            _LOG.debug("Pushed update for %s: %s", self.id, self.attributes[Attributes.STATE])