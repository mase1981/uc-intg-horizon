"""
Horizon device wrapper using lghorizon 0.9.11 API.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import os
from enum import StrEnum
from typing import Any

import aiohttp
import certifi
from pyee.asyncio import AsyncIOEventEmitter

from lghorizon import (
    COUNTRY_SETTINGS,
    LGHorizonApi,
    LGHorizonAuth,
    LGHorizonDevice as LGDevice,
    LGHorizonRunningState,
)

from uc_intg_horizon.config import HorizonConfig

_LOG = logging.getLogger(__name__)

PROVIDER_TO_COUNTRY = {
    "Ziggo": "nl",
    "VirginMedia": "gb",
    "Telenet": "be-nl",
    "UPC": "ch",
    "Sunrise": "ch",
}


class DeviceEvents(StrEnum):
    """Device event types for ucapi-framework integration."""

    CONNECTING = "DEVICE_CONNECTING"
    CONNECTED = "DEVICE_CONNECTED"
    DISCONNECTED = "DEVICE_DISCONNECTED"
    ERROR = "DEVICE_ERROR"
    UPDATE = "DEVICE_UPDATE"


class HorizonDevice:
    """
    Wrapper for lghorizon 0.9.11 API with ucapi-framework event support.

    Uses ExternalClientDevice pattern - lghorizon manages its own MQTT connection.
    Emits events for state changes that entities can subscribe to.
    """

    def __init__(self, config: HorizonConfig) -> None:
        """Initialize the Horizon device wrapper."""
        self._config = config
        self._session: aiohttp.ClientSession | None = None
        self._auth: LGHorizonAuth | None = None
        self._api: LGHorizonApi | None = None
        self._devices: dict[str, LGDevice] = {}
        self._connected = False
        self._reconnect_task: asyncio.Task | None = None

        self.events = AsyncIOEventEmitter()

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

        self._country_code = PROVIDER_TO_COUNTRY.get(config.provider, "nl")
        _LOG.info(
            "HorizonDevice initialized: provider=%s, country_code=%s",
            config.provider,
            self._country_code,
        )

    @property
    def identifier(self) -> str:
        """Return the config identifier."""
        return self._config.identifier

    @property
    def name(self) -> str:
        """Return the config name."""
        return self._config.name

    @property
    def is_connected(self) -> bool:
        """Return True if connected to Horizon API."""
        return self._connected and self._api is not None

    @property
    def devices(self) -> dict[str, LGDevice]:
        """Return discovered devices."""
        return self._devices

    @property
    def config(self) -> HorizonConfig:
        """Return the device configuration."""
        return self._config

    async def connect(self) -> bool:
        """Connect to Horizon API using lghorizon 0.9.11."""
        try:
            _LOG.info(
                "Connecting to Horizon API: provider=%s, username=%s",
                self._config.provider,
                self._config.username,
            )

            self.events.emit(DeviceEvents.CONNECTING, self.identifier)

            if self._country_code not in COUNTRY_SETTINGS:
                _LOG.error("Unsupported country code: %s", self._country_code)
                self.events.emit(DeviceEvents.ERROR, self.identifier, "Unsupported country")
                return False

            country_config = COUNTRY_SETTINGS[self._country_code]
            api_url = country_config["api_url"]
            use_refresh_token = country_config.get("use_refreshtoken", False)

            self._session = aiohttp.ClientSession()

            if use_refresh_token:
                _LOG.info(
                    "Using refresh token authentication for %s",
                    self._country_code.upper(),
                )
                self._auth = LGHorizonAuth(
                    session=self._session,
                    api_url=api_url,
                    country_code=self._country_code,
                    username=self._config.username,
                    password="",
                    refresh_token=self._config.password,
                )
            else:
                self._auth = LGHorizonAuth(
                    session=self._session,
                    api_url=api_url,
                    country_code=self._country_code,
                    username=self._config.username,
                    password=self._config.password,
                )

            await self._auth.login()

            self._api = LGHorizonApi(auth=self._auth, profile_id=None)
            await self._api.initialize()

            self._devices = await self._api.get_devices()

            for device_id, device in self._devices.items():
                await device.set_callback(self._on_device_state_change)

            self._connected = True
            self.events.emit(DeviceEvents.CONNECTED, self.identifier)
            _LOG.info(
                "Connected to Horizon API successfully. Devices found: %d",
                len(self._devices),
            )

            return True

        except Exception as e:
            _LOG.error("Failed to connect to Horizon API: %s", e, exc_info=True)
            self._connected = False
            self.events.emit(DeviceEvents.ERROR, self.identifier, str(e))
            await self._cleanup_session()
            return False

    async def disconnect(self) -> None:
        """Disconnect from Horizon API."""
        try:
            if self._reconnect_task and not self._reconnect_task.done():
                self._reconnect_task.cancel()
                try:
                    await self._reconnect_task
                except asyncio.CancelledError:
                    pass

            if self._api:
                await self._api.disconnect()
                self._api = None

            await self._cleanup_session()

            self._devices = {}
            self._connected = False
            self.events.emit(DeviceEvents.DISCONNECTED, self.identifier)
            _LOG.info("Disconnected from Horizon API")

        except Exception as e:
            _LOG.error("Error during disconnect: %s", e)

    async def _cleanup_session(self) -> None:
        """Clean up aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _on_device_state_change(self, device_id: str) -> None:
        """Handle device state change callback from lghorizon MQTT."""
        _LOG.debug("Device state changed: %s", device_id)
        state = await self.get_device_state(device_id)
        self.events.emit(DeviceEvents.UPDATE, device_id, state)

    async def get_device(self, device_id: str) -> LGDevice | None:
        """Get a specific device by ID."""
        return self._devices.get(device_id)

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Get current state of a device."""
        device = await self.get_device(device_id)
        if not device:
            return {"state": "unavailable"}

        try:
            state = device.device_state
            running_state = state.state if state else None

            result = {
                "state": self._running_state_to_string(running_state),
                "channel": None,
                "media_title": None,
                "media_image": None,
                "start_time": None,
                "end_time": None,
                "position": None,
                "duration": None,
                "paused": False,
            }

            if state:
                result["channel"] = getattr(state, "channel_name", None)
                result["media_title"] = getattr(state, "show_title", None) or getattr(
                    state, "title", None
                )
                result["media_image"] = getattr(state, "image", None)
                result["start_time"] = getattr(state, "start_time", None)
                result["end_time"] = getattr(state, "end_time", None)
                result["position"] = getattr(state, "position", None)
                result["duration"] = getattr(state, "duration", None)
                result["paused"] = getattr(state, "paused", False)

            return result

        except Exception as e:
            _LOG.error("Failed to get state for %s: %s", device_id, e)
            return {"state": "unavailable"}

    def _running_state_to_string(self, state: LGHorizonRunningState | None) -> str:
        """Convert LGHorizonRunningState enum to string."""
        if state is None:
            return "unavailable"
        if state == LGHorizonRunningState.ONLINE_RUNNING:
            return "ONLINE_RUNNING"
        if state == LGHorizonRunningState.ONLINE_STANDBY:
            return "ONLINE_STANDBY"
        if state == LGHorizonRunningState.OFFLINE:
            return "OFFLINE"
        return "unavailable"

    async def power_on(self, device_id: str) -> bool:
        """Turn on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.turn_on()
            _LOG.info("Power ON sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to power on %s: %s", device_id, e)
            return False

    async def power_off(self, device_id: str) -> bool:
        """Turn off a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.turn_off()
            _LOG.info("Power OFF sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to power off %s: %s", device_id, e)
            return False

    async def power_toggle(self, device_id: str) -> bool:
        """Toggle power on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.send_key_to_box("Power")
            _LOG.info("Power TOGGLE sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to toggle power %s: %s", device_id, e)
            return False

    async def play(self, device_id: str) -> bool:
        """Play on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.play()
            return True
        except Exception as e:
            _LOG.error("Failed to play on %s: %s", device_id, e)
            return False

    async def pause(self, device_id: str) -> bool:
        """Pause on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.pause()
            return True
        except Exception as e:
            _LOG.error("Failed to pause on %s: %s", device_id, e)
            return False

    async def stop(self, device_id: str) -> bool:
        """Stop on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.stop()
            return True
        except Exception as e:
            _LOG.error("Failed to stop on %s: %s", device_id, e)
            return False

    async def next_channel(self, device_id: str) -> bool:
        """Go to next channel."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.next_channel()
            return True
        except Exception as e:
            _LOG.error("Failed to go to next channel on %s: %s", device_id, e)
            return False

    async def previous_channel(self, device_id: str) -> bool:
        """Go to previous channel."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.previous_channel()
            return True
        except Exception as e:
            _LOG.error("Failed to go to previous channel on %s: %s", device_id, e)
            return False

    async def fast_forward(self, device_id: str) -> bool:
        """Fast forward on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.fast_forward()
            return True
        except Exception as e:
            _LOG.error("Failed to fast forward on %s: %s", device_id, e)
            return False

    async def rewind(self, device_id: str) -> bool:
        """Rewind on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.rewind()
            return True
        except Exception as e:
            _LOG.error("Failed to rewind on %s: %s", device_id, e)
            return False

    async def record(self, device_id: str) -> bool:
        """Record on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.record()
            return True
        except Exception as e:
            _LOG.error("Failed to record on %s: %s", device_id, e)
            return False

    async def seek(self, device_id: str, position_seconds: int) -> bool:
        """Seek to position on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.set_player_position(position_seconds)
            _LOG.info("Seek to %ds sent to %s", position_seconds, device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to seek on %s: %s", device_id, e)
            return False

    async def send_key(self, device_id: str, key: str) -> bool:
        """Send a key press to a device."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.send_key_to_box(key)
            _LOG.debug("Sent key %s to %s", key, device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to send key %s to %s: %s", key, device_id, e)
            return False

    async def set_channel(self, device_id: str, channel_name: str) -> bool:
        """Set channel by name."""
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.set_channel(channel_name)
            _LOG.info("Set channel to %s on %s", channel_name, device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to set channel on %s: %s", device_id, e)
            return False

    async def set_channel_by_number(self, device_id: str, channel_number: str) -> bool:
        """Set channel by sending digit keys."""
        device = await self.get_device(device_id)
        if not device:
            return False

        try:
            channel_str = str(channel_number).strip()
            if not channel_str.isdigit():
                _LOG.error("Invalid channel number: %s", channel_number)
                return False

            for digit in channel_str:
                await device.send_key_to_box(digit)
                await asyncio.sleep(0.3)

            await asyncio.sleep(0.5)
            await device.send_key_to_box("Enter")

            _LOG.info("Set channel to %s on %s", channel_str, device_id)
            return True

        except Exception as e:
            _LOG.error("Failed to set channel %s on %s: %s", channel_number, device_id, e)
            return False

    async def get_channels(self) -> list[dict[str, str]]:
        """Get available channels."""
        if not self._api:
            return []

        try:
            channels = await self._api.get_profile_channels()
            return [{"id": ch.id, "name": ch.title} for ch in channels.values()]
        except Exception as e:
            _LOG.error("Failed to get channels: %s", e)
            return []

    def get_refreshed_token(self) -> str | None:
        """Get the current refresh token (may have been refreshed)."""
        if self._auth:
            return getattr(self._auth, "refresh_token", None)
        return None
