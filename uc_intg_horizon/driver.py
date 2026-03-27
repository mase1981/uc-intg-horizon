"""
Main integration driver for Horizon using ucapi-framework.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ucapi import DeviceStates, Events
from ucapi_framework import BaseIntegrationDriver
from ucapi_framework.device import DeviceEvents

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.device import HorizonDevice
from uc_intg_horizon.media_player import HorizonMediaPlayer
from uc_intg_horizon.remote import HorizonRemote
from uc_intg_horizon.sensor import (
    HorizonChannelSensor,
    HorizonDeviceStateSensor,
    HorizonProgramSensor,
)

_LOG = logging.getLogger(__name__)

_ENTITY_SUFFIXES = ("_remote", "_state", "_channel", "_program")
_RETRY_DELAYS = [5, 10, 20, 30, 60, 120, 300]


class HorizonDriver(BaseIntegrationDriver[HorizonDevice, HorizonConfig]):
    """Horizon integration driver. Handles 1 account = N STBs pattern."""

    def __init__(self):
        super().__init__(
            device_class=HorizonDevice,
            entity_classes=[],
            driver_id="horizon",
        )
        self._media_players: dict[str, HorizonMediaPlayer] = {}
        self._remotes: dict[str, HorizonRemote] = {}
        self._sensors: dict[str, list] = {}
        self._retry_task: asyncio.Task | None = None
        self._stb_to_config: dict[str, str] = {}

        self.api.add_listener(Events.SUBSCRIBE_ENTITIES, self._on_subscribe_entities)

    def device_from_entity_id(self, entity_id: str) -> str | None:
        if not entity_id:
            return None
        stb_id = entity_id
        for suffix in _ENTITY_SUFFIXES:
            if entity_id.endswith(suffix):
                stb_id = entity_id[: -len(suffix)]
                break
        return self._stb_to_config.get(stb_id)

    def entity_type_from_entity_id(self, entity_id: str) -> str | None:
        if not entity_id:
            return None
        if entity_id.endswith("_remote"):
            return "remote"
        if entity_id.endswith(("_state", "_channel", "_program")):
            return "sensor"
        return "media_player"

    def sub_device_from_entity_id(self, entity_id: str) -> str | None:
        return None

    def register_available_entities(
        self, device_config: HorizonConfig, device: HorizonDevice
    ) -> None:
        _LOG.info(
            "Registering entities for %s (%d STBs)",
            device_config.identifier, len(device_config.devices),
        )

        device.events.on(DeviceEvents.UPDATE, self._on_device_state_change)

        for dev_cfg in device_config.devices:
            device_id = dev_cfg.device_id
            device_name = dev_cfg.name
            self._stb_to_config[device_id] = device_config.identifier

            sensors = [
                HorizonDeviceStateSensor(device_id, device_name, device, self.api),
                HorizonChannelSensor(device_id, device_name, device, self.api),
                HorizonProgramSensor(device_id, device_name, device, self.api),
            ]
            self._sensors[device_id] = sensors

            mp = HorizonMediaPlayer(device_id, device_name, device, self.api, sensors)
            self._media_players[device_id] = mp
            self.api.available_entities.add(mp)

            remote = HorizonRemote(device_id, device_name, device, self.api, mp)
            self._remotes[device_id] = remote
            self.api.available_entities.add(remote)

            for sensor in sensors:
                self.api.available_entities.add(sensor)

            _LOG.info("Created entities for STB: %s (%s)", device_name, device_id)

    def on_device_removed(self, device_or_config: HorizonDevice | HorizonConfig | None) -> None:
        if device_or_config is None:
            self._media_players.clear()
            self._remotes.clear()
            self._sensors.clear()
            self._stb_to_config.clear()
            self.api.available_entities.clear()
            return

        config = (
            device_or_config
            if isinstance(device_or_config, HorizonConfig)
            else device_or_config.config
        )

        for dev_cfg in config.devices:
            device_id = dev_cfg.device_id
            self._stb_to_config.pop(device_id, None)

            for store, attr in [
                (self._media_players, "id"),
                (self._remotes, "id"),
            ]:
                entity = store.pop(device_id, None)
                if entity:
                    self.api.available_entities.remove(getattr(entity, attr))

            if device_id in self._sensors:
                for sensor in self._sensors.pop(device_id):
                    self.api.available_entities.remove(sensor.id)

    async def _on_subscribe_entities(self, entity_ids: list[str]) -> None:
        for entity_id in entity_ids:
            entity = self._find_entity(entity_id)
            if entity:
                self.api.configured_entities.add(entity)
                if hasattr(entity, "push_update"):
                    await entity.push_update()

    def _find_entity(self, entity_id: str) -> Any | None:
        for store in (self._media_players, self._remotes):
            for entity in store.values():
                if entity.id == entity_id:
                    return entity

        for sensors in self._sensors.values():
            for sensor in sensors:
                if sensor.id == entity_id:
                    return sensor

        return None

    async def _on_device_state_change(self, device_id: str, state: dict[str, Any]) -> None:
        config_id = self._stb_to_config.get(device_id)
        if config_id:
            device = self._device_instances.get(config_id)
            config = self.config_manager.get(config_id) if self.config_manager else None
            if device and config and device.token_needs_save:
                self._save_token_if_changed(device, config)

        if device_id in self._media_players:
            mp = self._media_players[device_id]
            if self.api.configured_entities.contains(mp.id):
                await mp.push_update()

        if device_id in self._remotes:
            remote = self._remotes[device_id]
            if self.api.configured_entities.contains(remote.id):
                await remote.push_update()

    async def connect_devices(self) -> bool:
        if not self.config_manager:
            return False

        configs = list(self.config_manager.all())
        if not configs:
            await self.api.set_device_state(DeviceStates.DISCONNECTED)
            return True

        success = True
        for config in configs:
            device = self._device_instances.get(config.identifier)
            if device and not device.is_connected:
                if not await device.connect():
                    _LOG.error("Failed to connect: %s", config.identifier)
                    success = False
                else:
                    self._save_token_if_changed(device, config)

        if success and self._media_players:
            await self.api.set_device_state(DeviceStates.CONNECTED)
        else:
            await self.api.set_device_state(DeviceStates.ERROR)
            self._start_retry_task()

        return success

    def _save_token_if_changed(self, device: HorizonDevice, config: HorizonConfig) -> None:
        refreshed_token = device.get_refreshed_token()
        if refreshed_token and refreshed_token != config.password:
            config.password = refreshed_token
            self.config_manager.update(config)
            device.mark_token_saved()
            _LOG.info("Token refreshed and saved for %s", config.identifier)
        elif device.token_needs_save:
            self.config_manager.update(config)
            device.mark_token_saved()

    def _start_retry_task(self) -> None:
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._retry_connection())

    async def _retry_connection(self) -> None:
        attempt = 0
        while self.config_manager and list(self.config_manager.all()):
            delay = _RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)]
            _LOG.warning("Retrying connection in %ds (attempt #%d)...", delay, attempt + 1)
            await asyncio.sleep(delay)
            try:
                if await self.connect_devices():
                    _LOG.info("Retry successful!")
                    return
            except Exception as err:
                _LOG.error("Retry failed: %s", err)
            attempt += 1
