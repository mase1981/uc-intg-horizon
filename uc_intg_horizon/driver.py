"""
Main integration driver for Horizon.

:copyright: (c) 2025 by Meir Miyara
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

import ucapi
from ucapi.api_definitions import DeviceStates, Events, SetupAction

from uc_intg_horizon.config import HorizonConfig, HorizonDeviceConfig
from uc_intg_horizon.device import HorizonDevice
from uc_intg_horizon.media_player import HorizonMediaPlayer
from uc_intg_horizon.remote import HorizonRemote
from uc_intg_horizon.sensor import (
    HorizonChannelSensor,
    HorizonDeviceStateSensor,
    HorizonProgramSensor,
)
from uc_intg_horizon.setup_flow import HorizonSetupFlow

_LOG = logging.getLogger(__name__)


class HorizonConfigManager:
    """Manages configuration persistence."""

    def __init__(self) -> None:
        """Initialize config manager."""
        data_dir = os.environ.get("UC_CONFIG_HOME", "/data")
        os.makedirs(data_dir, exist_ok=True)
        self._config_path = Path(data_dir) / "config.json"
        self._configs: dict[str, HorizonConfig] = {}

    def add(self, config: HorizonConfig) -> None:
        """Add or update a configuration."""
        self._configs[config.identifier] = config

    def remove(self, identifier: str) -> bool:
        """Remove a configuration."""
        if identifier in self._configs:
            del self._configs[identifier]
            return True
        return False

    def get(self, identifier: str) -> HorizonConfig | None:
        """Get a configuration by identifier."""
        return self._configs.get(identifier)

    def all(self) -> list[HorizonConfig]:
        """Get all configurations."""
        return list(self._configs.values())

    async def load(self) -> None:
        """Load configurations from disk."""
        if not self._config_path.exists():
            _LOG.debug("No configuration file found at %s", self._config_path)
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for config_data in data.get("configs", []):
                devices = [
                    HorizonDeviceConfig(**d) for d in config_data.get("devices", [])
                ]
                config = HorizonConfig(
                    identifier=config_data["identifier"],
                    name=config_data["name"],
                    provider=config_data["provider"],
                    username=config_data["username"],
                    password=config_data["password"],
                    devices=devices,
                )
                self._configs[config.identifier] = config

            _LOG.info("Loaded %d configuration(s) from disk", len(self._configs))

        except Exception as e:
            _LOG.error("Failed to load configuration: %s", e)

    async def save(self) -> None:
        """Save configurations to disk."""
        try:
            data = {
                "configs": [asdict(c) for c in self._configs.values()]
            }

            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            _LOG.info("Saved %d configuration(s) to disk", len(self._configs))

        except Exception as e:
            _LOG.error("Failed to save configuration: %s", e)


class HorizonDriver:
    """Main driver for Horizon integration."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialize the Horizon driver."""
        self._loop = loop
        self._api: ucapi.IntegrationAPI = ucapi.IntegrationAPI(loop)

        self.config_manager = HorizonConfigManager()
        self._setup_flow = HorizonSetupFlow(self)

        self._devices: dict[str, HorizonDevice] = {}
        self._media_players: dict[str, HorizonMediaPlayer] = {}
        self._remotes: dict[str, HorizonRemote] = {}
        self._sensors: dict[str, list] = {}

        self._initialized = False
        self._init_lock = asyncio.Lock()
        self._retry_task: asyncio.Task | None = None

    @property
    def api(self) -> ucapi.IntegrationAPI:
        """Return the UC API instance."""
        return self._api

    async def start(self) -> None:
        """Start the driver."""
        _LOG.info("Starting Horizon driver...")

        await self.config_manager.load()

        self._api.add_listener(Events.CONNECT, self._on_connect)
        self._api.add_listener(Events.DISCONNECT, self._on_disconnect)
        self._api.add_listener(Events.SUBSCRIBE_ENTITIES, self._on_subscribe_entities)

        await self._api.init("driver.json", self._setup_handler)

        if self.config_manager.all():
            _LOG.info("Configuration found - initializing for reboot survival")
            await self._initialize_all()

        await self._api.set_device_state(DeviceStates.DISCONNECTED)

        _LOG.info("Horizon driver started")

    async def stop(self) -> None:
        """Stop the driver."""
        _LOG.info("Stopping Horizon driver...")

        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass

        for device in self._devices.values():
            await device.disconnect()

        self._devices.clear()
        self._media_players.clear()
        self._remotes.clear()
        self._sensors.clear()

        _LOG.info("Horizon driver stopped")

    async def _setup_handler(self, msg: SetupAction) -> SetupAction:
        """Handle setup messages."""
        result = await self._setup_flow.handle_setup(msg)

        from ucapi.api_definitions import SetupComplete

        if isinstance(result, SetupComplete):
            _LOG.info("Setup complete - initializing integration")
            await self._initialize_all()

        return result

    async def _on_connect(self) -> None:
        """Handle UC Remote connect event."""
        _LOG.info("UC Remote connected")

        await self.config_manager.load()

        if not self.config_manager.all():
            _LOG.info("No configuration - awaiting setup")
            await self._api.set_device_state(DeviceStates.DISCONNECTED)
            return

        if not self._initialized:
            success = await self._initialize_all()
            if not success:
                await self._api.set_device_state(DeviceStates.ERROR)
                self._start_retry_task()
                return

        await self._api.set_device_state(DeviceStates.CONNECTED)

    async def _on_disconnect(self) -> None:
        """Handle UC Remote disconnect event."""
        _LOG.info("UC Remote disconnected - preserving connections")

    async def _on_subscribe_entities(self, entity_ids: list[str]) -> None:
        """Handle entity subscription."""
        _LOG.info("Entity subscription request: %s", entity_ids)

        if not self._initialized:
            _LOG.warning("Subscription before initialization - attempting init")
            if self.config_manager.all():
                await self._initialize_all()

        for entity_id in entity_ids:
            entity = self._find_entity(entity_id)
            if entity:
                self._api.configured_entities.add(entity)
                await entity.push_update()
                _LOG.info("Subscribed to entity: %s", entity_id)
            else:
                _LOG.warning("Entity not found: %s", entity_id)

    def _find_entity(self, entity_id: str) -> Any | None:
        """Find an entity by ID."""
        for mp in self._media_players.values():
            if mp.id == entity_id:
                return mp

        for remote in self._remotes.values():
            if remote.id == entity_id:
                return remote

        for sensors in self._sensors.values():
            for sensor in sensors:
                if sensor.id == entity_id:
                    return sensor

        return None

    async def _initialize_all(self) -> bool:
        """Initialize all configured devices."""
        async with self._init_lock:
            if self._initialized:
                return True

            _LOG.info("Initializing Horizon integration...")

            self._api.available_entities.clear()
            self._media_players.clear()
            self._remotes.clear()
            self._sensors.clear()

            success = True

            for config in self.config_manager.all():
                if not await self._initialize_config(config):
                    success = False

            if self._media_players:
                self._initialized = True
                _LOG.info(
                    "Initialization complete: %d media players, %d remotes, %d sensors",
                    len(self._media_players),
                    len(self._remotes),
                    sum(len(s) for s in self._sensors.values()),
                )
            else:
                _LOG.error("No devices initialized")
                success = False

            return success

    async def _initialize_config(self, config: HorizonConfig) -> bool:
        """Initialize devices for a configuration."""
        _LOG.info("Initializing config: %s", config.identifier)

        device = HorizonDevice(config)

        if not await device.connect():
            _LOG.error("Failed to connect: %s", config.identifier)
            return False

        self._devices[config.identifier] = device

        device.set_state_callback(self._on_device_state_change)

        refreshed_token = device.get_refreshed_token()
        if refreshed_token and refreshed_token != config.password:
            config.password = refreshed_token
            await self.config_manager.save()

        for device_config in config.devices:
            device_id = device_config.device_id
            device_name = device_config.name

            api_device = await device.get_device(device_id)
            if not api_device:
                _LOG.warning("Device not found in API: %s", device_id)
                continue

            state_sensor = HorizonDeviceStateSensor(
                device_id=device_id,
                device_name=device_name,
                horizon_device=device,
                api=self._api,
            )

            channel_sensor = HorizonChannelSensor(
                device_id=device_id,
                device_name=device_name,
                horizon_device=device,
                api=self._api,
            )

            program_sensor = HorizonProgramSensor(
                device_id=device_id,
                device_name=device_name,
                horizon_device=device,
                api=self._api,
            )

            sensors = [state_sensor, channel_sensor, program_sensor]
            self._sensors[device_id] = sensors

            media_player = HorizonMediaPlayer(
                device_id=device_id,
                device_name=device_name,
                horizon_device=device,
                api=self._api,
                sensors=sensors,
            )
            self._media_players[device_id] = media_player
            self._api.available_entities.add(media_player)

            remote = HorizonRemote(
                device_id=device_id,
                device_name=device_name,
                horizon_device=device,
                api=self._api,
                media_player=media_player,
            )
            self._remotes[device_id] = remote
            self._api.available_entities.add(remote)

            for sensor in sensors:
                self._api.available_entities.add(sensor)

            _LOG.info("Created entities for device: %s", device_name)

        return True

    async def _on_device_state_change(self, device_id: str) -> None:
        """Handle device state change from lghorizon."""
        _LOG.debug("Device state changed: %s", device_id)

        if device_id in self._media_players:
            mp = self._media_players[device_id]
            if self._api.configured_entities.contains(mp.id):
                await mp.push_update()

        if device_id in self._remotes:
            remote = self._remotes[device_id]
            if self._api.configured_entities.contains(remote.id):
                await remote.push_update()

        if device_id in self._sensors:
            for config in self.config_manager.all():
                device = self._devices.get(config.identifier)
                if device:
                    state = await device.get_device_state(device_id)
                    for sensor in self._sensors[device_id]:
                        if self._api.configured_entities.contains(sensor.id):
                            await sensor.update_state(state)
                    break

    def _start_retry_task(self) -> None:
        """Start background retry task."""
        if self._retry_task is None or self._retry_task.done():
            self._retry_task = asyncio.create_task(self._retry_initialization())

    async def _retry_initialization(self) -> None:
        """Retry initialization with backoff."""
        delays = [5, 10, 20, 30, 60, 120, 300]
        attempt = 0

        while not self._initialized and self.config_manager.all():
            delay = delays[min(attempt, len(delays) - 1)]
            _LOG.warning("Retrying in %ds (attempt #%d)...", delay, attempt + 1)
            await asyncio.sleep(delay)

            try:
                if await self._initialize_all():
                    _LOG.info("Retry successful!")
                    await self._api.set_device_state(DeviceStates.CONNECTED)
                    return
            except Exception as e:
                _LOG.error("Retry failed: %s", e)

            attempt += 1

        _LOG.error("All retry attempts exhausted")
