"""
Remote Control entity for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

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

from uc_intg_horizon.const import (
    CHANNEL_UPDATE_DELAY,
    KEY_MAP,
    POWER_COMMAND_DELAY,
    SIMPLE_COMMANDS,
)

if TYPE_CHECKING:
    import ucapi
    from uc_intg_horizon.device import HorizonDevice
    from uc_intg_horizon.media_player import HorizonMediaPlayer

_LOG = logging.getLogger(__name__)

_SPECIAL_COMMANDS = ("POWER_ON", "POWER_OFF", "POWER_TOGGLE", "PLAYPAUSE", "RECORD", "DVR")

BUTTON_MAPPING = [
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


def _create_main_page() -> UiPage:
    page = UiPage("main", "Main Control", grid=Size(3, 6))
    page.add(create_ui_icon("uc:ballot", 0, 0, cmd="GUIDE"))
    page.add(create_ui_icon("uc:house-blank", 1, 0, cmd="HOME"))
    page.add(create_ui_icon("uc:power-off", 2, 0, cmd="POWER_TOGGLE"))
    page.add(create_ui_icon("uc:cassette-vhs", 0, 1, cmd="DVR"))
    page.add(create_ui_icon("uc:tv", 2, 1, cmd="TV"))
    page.add(create_ui_icon("uc:chevron-up", 1, 2, cmd="UP"))
    page.add(create_ui_icon("uc:chevron-left", 0, 3, cmd="LEFT"))
    page.add(create_ui_icon("uc:circle-check", 1, 3, cmd="SELECT"))
    page.add(create_ui_icon("uc:chevron-right", 2, 3, cmd="RIGHT"))
    page.add(create_ui_icon("uc:chevron-down", 1, 4, cmd="DOWN"))
    page.add(create_ui_icon("uc:reply", 0, 5, cmd="BACK"))
    page.add(create_ui_icon("uc:ellipsis", 2, 5, cmd="MENU"))
    return page


def _create_numbers_page() -> UiPage:
    page = UiPage("numbers", "Channel Numbers", grid=Size(4, 4))
    page.add(create_ui_icon("uc:1", 0, 0, cmd="1"))
    page.add(create_ui_icon("uc:2", 1, 0, cmd="2"))
    page.add(create_ui_icon("uc:3", 2, 0, cmd="3"))
    page.add(create_ui_icon("uc:4", 0, 1, cmd="4"))
    page.add(create_ui_icon("uc:5", 1, 1, cmd="5"))
    page.add(create_ui_icon("uc:6", 2, 1, cmd="6"))
    page.add(create_ui_icon("uc:7", 0, 2, cmd="7"))
    page.add(create_ui_icon("uc:8", 1, 2, cmd="8"))
    page.add(create_ui_icon("uc:9", 2, 2, cmd="9"))
    page.add(create_ui_icon("uc:0", 1, 3, cmd="0"))
    page.add(create_ui_icon("uc:arrow-up-long", 3, 0, cmd="CHANNEL_UP"))
    page.add(create_ui_icon("uc:arrow-down-long", 3, 1, cmd="CHANNEL_DOWN"))
    page.add(create_ui_icon("uc:circle-check", 3, 3, cmd="SELECT"))
    return page


def _create_playback_page() -> UiPage:
    page = UiPage("playback", "Playback", grid=Size(4, 4))
    page.add(create_ui_icon("uc:backward", 0, 0, cmd="REWIND"))
    page.add(create_ui_icon("uc:square-small", 1, 0, cmd="STOP"))
    page.add(create_ui_icon("uc:play-pause", 2, 0, cmd="PLAYPAUSE"))
    page.add(create_ui_icon("uc:forward", 3, 0, cmd="FASTFORWARD"))
    page.add(create_ui_icon("uc:volume-xmark", 0, 1, cmd="MUTE"))
    page.add(create_ui_icon("uc:volume-low", 1, 1, cmd="VOLUME_DOWN"))
    page.add(create_ui_icon("uc:volume-high", 2, 1, cmd="VOLUME_UP"))
    page.add(create_ui_icon("uc:circle-dot", 3, 1, cmd="RECORD"))
    page.add(create_ui_icon("uc:circle-check", 0, 2, cmd="SELECT"))
    page.add(create_ui_icon("uc:arrow-right-to-bracket", 3, 2, cmd="SOURCE"))
    page.add(create_ui_icon("uc:circle-r", 0, 3, cmd="RED"))
    page.add(create_ui_icon("uc:circle-g", 1, 3, cmd="GREEN"))
    page.add(create_ui_icon("uc:circle-y", 2, 3, cmd="YELLOW"))
    page.add(create_ui_icon("uc:circle-b", 3, 3, cmd="BLUE"))
    return page


def _create_power_page() -> UiPage:
    page = UiPage("power", "Power Buttons", grid=Size(4, 4))
    page.add(create_ui_text("Power On", 0, 0, size=Size(2, 2), cmd="POWER_ON"))
    page.add(create_ui_text("Power Off", 2, 0, size=Size(2, 2), cmd="POWER_OFF"))
    return page


class HorizonRemote(Remote):
    """Remote Control entity for a Horizon set-top box."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        horizon_device: HorizonDevice,
        api: ucapi.IntegrationAPI,
        media_player: HorizonMediaPlayer | None = None,
    ) -> None:
        self._device_id = device_id
        self._horizon_device = horizon_device
        self._api = api
        self._media_player = media_player
        self._channel_update_task: asyncio.Task | None = None
        self._last_sent_state: States | None = None

        super().__init__(
            identifier=f"{device_id}_remote",
            name=f"{device_name} Remote",
            features=[Features.ON_OFF, Features.TOGGLE, Features.SEND_CMD],
            attributes={Attributes.STATE: States.UNAVAILABLE},
            simple_commands=SIMPLE_COMMANDS,
            button_mapping=BUTTON_MAPPING,
            ui_pages=[
                _create_main_page(),
                _create_numbers_page(),
                _create_playback_page(),
                _create_power_page(),
            ],
            cmd_handler=self._handle_command,
        )

        self._refresh_task: asyncio.Task | None = asyncio.create_task(
            self._periodic_refresh()
        )

    def stop(self) -> None:
        """Cancel background tasks (entity removed / replaced)."""
        for task in (self._refresh_task, self._channel_update_task):
            if task and not task.done():
                task.cancel()

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
                _LOG.error("Periodic refresh error for remote %s: %s", self._device_id, err)
                await asyncio.sleep(PERIODIC_REFRESH_INTERVAL)

    @staticmethod
    def _is_known_command(command: str) -> bool:
        return (
            command.startswith("channel_select:")
            or command in _SPECIAL_COMMANDS
            or command in KEY_MAP
        )

    @staticmethod
    def _int_param(params: dict[str, Any], key: str, default: int) -> int:
        try:
            return max(0, int(params.get(key, default) or default))
        except (TypeError, ValueError):
            return default

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        _LOG.info("[%s] Command: %s params=%s", self.id, cmd_id, params)
        params = params or {}

        if cmd_id == Commands.SEND_CMD:
            command = params.get("command")
            if not command or not self._is_known_command(command):
                _LOG.warning("[%s] Unknown command: %s", self.id, command)
                return StatusCodes.BAD_REQUEST
            commands = [command]
        elif cmd_id == Commands.SEND_CMD_SEQUENCE:
            sequence = params.get("sequence")
            if isinstance(sequence, str):
                sequence = sequence.split(",")
            commands = [str(c).strip() for c in (sequence or []) if str(c).strip()]
            unknown = [c for c in commands if not self._is_known_command(c)]
            if not commands or unknown:
                _LOG.warning("[%s] Invalid command sequence: %s", self.id, sequence)
                return StatusCodes.BAD_REQUEST
        elif cmd_id in (Commands.ON, Commands.OFF, Commands.TOGGLE):
            commands = []
        else:
            return StatusCodes.NOT_IMPLEMENTED

        if not self._horizon_device.is_ready(self._device_id):
            _LOG.warning("[%s] Not connected, command %s rejected", self.id, cmd_id)
            self._horizon_device.request_reconnect()
            return StatusCodes.SERVICE_UNAVAILABLE

        try:
            if cmd_id == Commands.ON:
                ok = await self._horizon_device.power_on(self._device_id)
                is_power, is_channel = True, False
            elif cmd_id == Commands.OFF:
                ok = await self._horizon_device.power_off(self._device_id)
                is_power, is_channel = True, False
            elif cmd_id == Commands.TOGGLE:
                ok = await self._horizon_device.power_toggle(self._device_id)
                is_power, is_channel = True, False
            else:
                repeat = max(1, self._int_param(params, "repeat", 1))
                delay = self._int_param(params, "delay", 0) / 1000
                ok, is_power, is_channel = True, False, False
                sends = [c for _ in range(repeat) for c in commands]
                for index, command in enumerate(sends):
                    if index and delay:
                        await asyncio.sleep(delay)
                    sent, power, channel = await self._dispatch_simple_command(command)
                    is_power = is_power or power
                    is_channel = is_channel or channel
                    if not sent:
                        ok = False
                        break

            if is_power:
                await asyncio.sleep(POWER_COMMAND_DELAY)
                await self.push_update()
            elif is_channel:
                self._schedule_channel_update()
                await self.push_update()
            else:
                await self.push_update()

            return StatusCodes.OK if ok else StatusCodes.SERVER_ERROR

        except Exception as err:
            _LOG.error("[%s] Command error: %s", self.id, err, exc_info=True)
            return StatusCodes.SERVER_ERROR

    async def _dispatch_simple_command(self, command: str) -> tuple[bool, bool, bool]:
        """Send one simple command. Returns (sent_ok, is_power, is_channel)."""
        dev = self._horizon_device
        if command.startswith("channel_select:"):
            channel = command.split(":", 1)[1]
            return (await dev.set_channel_by_number(self._device_id, channel), False, True)

        if command == "POWER_ON":
            return (await dev.power_on(self._device_id), True, False)
        if command == "POWER_OFF":
            return (await dev.power_off(self._device_id), True, False)
        if command == "POWER_TOGGLE":
            return (await dev.power_toggle(self._device_id), True, False)

        if command == "PLAYPAUSE":
            state = dev.get_device_state(self._device_id)
            if state.get("paused"):
                return (await dev.play(self._device_id), False, False)
            return (await dev.pause(self._device_id), False, False)

        if command == "RECORD":
            return (await dev.record(self._device_id), False, False)

        if command == "DVR":
            return (await dev.send_key(self._device_id, "DVR"), False, False)

        horizon_key = KEY_MAP.get(command)
        if not horizon_key:
            _LOG.warning("Unknown command: %s", command)
            return (False, False, False)

        sent = await dev.send_key(self._device_id, horizon_key)

        if command in ("CHANNEL_UP", "CHANNEL_DOWN"):
            return (sent, False, True)

        if command in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"):
            self._schedule_channel_update()

        return (sent, False, False)

    def _schedule_channel_update(self) -> None:
        if self._channel_update_task and not self._channel_update_task.done():
            self._channel_update_task.cancel()
        self._channel_update_task = asyncio.create_task(self._delayed_channel_update())

    async def _delayed_channel_update(self) -> None:
        try:
            await asyncio.sleep(CHANNEL_UPDATE_DELAY)
            if self._media_player:
                await self._media_player.push_update()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOG.error("Delayed channel update error: %s", err)

    async def push_update(self, force: bool = False) -> None:
        if not self._api or not self._api.configured_entities.contains(self.id):
            return

        device_state = self._horizon_device.get_device_state(self._device_id)
        horizon_state = device_state.get("state", "unavailable")

        if horizon_state == "ONLINE_RUNNING":
            self.attributes[Attributes.STATE] = States.ON
        elif horizon_state in ("ONLINE_STANDBY", "OFFLINE"):
            self.attributes[Attributes.STATE] = States.OFF
        else:
            self.attributes[Attributes.STATE] = States.UNAVAILABLE

        new_state = self.attributes[Attributes.STATE]
        if not force and new_state == self._last_sent_state:
            return

        self._last_sent_state = new_state
        self._api.configured_entities.update_attributes(self.id, self.attributes)
