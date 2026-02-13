"""
Horizon device wrapper using lghorizon 0.9.11 API with ucapi-framework.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
from typing import Any

import aiohttp
import certifi

from lghorizon import (
    COUNTRY_SETTINGS,
    LGHorizonApi,
    LGHorizonAuth,
    LGHorizonDevice as LGDevice,
    LGHorizonRunningState,
)
from ucapi_framework.device import ExternalClientDevice, DeviceEvents

from uc_intg_horizon.config import HorizonConfig

_LOG = logging.getLogger(__name__)

PROVIDER_TO_COUNTRY = {
    "Ziggo": "nl",
    "VirginMedia": "gb",
    "Telenet": "be-nl",
    "UPC": "ch",
    "Sunrise": "ch",
}


class HorizonDevice(ExternalClientDevice):
    """
    Wrapper for lghorizon 0.9.11 API using ucapi-framework ExternalClientDevice.

    lghorizon manages its own MQTT connection for state updates.
    The watchdog monitors connection health and triggers reconnection if needed.
    """

    def __init__(self, device_config: HorizonConfig) -> None:
        """Initialize the Horizon device wrapper."""
        super().__init__(
            device_config=device_config,
            enable_watchdog=True,
            watchdog_interval=60,
            reconnect_delay=10,
            max_reconnect_attempts=0,
        )

        self._session: aiohttp.ClientSession | None = None
        self._auth: LGHorizonAuth | None = None
        self._api: LGHorizonApi | None = None
        self._lg_devices: dict[str, LGDevice] = {}

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

        self._country_code = PROVIDER_TO_COUNTRY.get(device_config.provider, "nl")
        _LOG.info(
            "HorizonDevice initialized: provider=%s, country_code=%s",
            device_config.provider,
            self._country_code,
        )

    @property
    def identifier(self) -> str:
        """Return the config identifier."""
        return self._device_config.identifier

    @property
    def name(self) -> str:
        """Return the config name."""
        return self._device_config.name

    @property
    def address(self) -> str | None:
        """Return the device address (not applicable for cloud API)."""
        return None

    @property
    def log_id(self) -> str:
        """Return a log identifier for the device."""
        return f"Horizon-{self._device_config.provider}"

    @property
    def devices(self) -> dict[str, LGDevice]:
        """Return discovered LG Horizon devices."""
        return self._lg_devices

    @property
    def config(self) -> HorizonConfig:
        """Return the device configuration."""
        return self._device_config

    async def create_client(self) -> LGHorizonApi:
        """Create the lghorizon API client."""
        if self._country_code not in COUNTRY_SETTINGS:
            raise ValueError(f"Unsupported country code: {self._country_code}")

        country_config = COUNTRY_SETTINGS[self._country_code]
        use_refresh_token = country_config.get("use_refreshtoken", False)

        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)

        if use_refresh_token:
            _LOG.info(
                "Using refresh token authentication for %s",
                self._country_code.upper(),
            )
            self._auth = LGHorizonAuth(
                websession=self._session,
                country_code=self._country_code,
                username=self._device_config.username,
                password="",
                refresh_token=self._device_config.password,
            )
        else:
            self._auth = LGHorizonAuth(
                websession=self._session,
                country_code=self._country_code,
                username=self._device_config.username,
                password=self._device_config.password,
            )

        self._api = LGHorizonApi(auth=self._auth, profile_id="")
        return self._api

    async def connect_client(self) -> None:
        """Connect the lghorizon client and set up callbacks."""
        if not self._api:
            raise RuntimeError("API not initialized")

        await self._api.initialize()
        self._lg_devices = await self._api.get_devices()

        for device_id, device in self._lg_devices.items():
            await device.set_callback(self._on_device_state_change)

        _LOG.info(
            "Connected to Horizon API successfully. Devices found: %d",
            len(self._lg_devices),
        )

    async def _wait_for_mqtt_ready(self, timeout: int = 10) -> None:
        """Wait for devices to register on MQTT and report their state."""
        elapsed = 0
        check_interval = 0.5

        _LOG.debug("Waiting for devices to register on MQTT...")

        while elapsed < timeout:
            devices = await self._api.get_devices()
            if devices:
                ready_count = 0
                for device_id, box in devices.items():
                    if hasattr(box, "device_state") and box.device_state is not None:
                        ready_count += 1
                        _LOG.debug(
                            "Device %s ready with state: %s",
                            device_id,
                            box.device_state.state if box.device_state else "None",
                        )

                if ready_count > 0:
                    _LOG.info(
                        "MQTT ready: %d/%d devices reported state",
                        ready_count,
                        len(devices),
                    )
                    return

            await asyncio.sleep(check_interval)
            elapsed += check_interval

            if int(elapsed) % 5 == 0 and elapsed > 0:
                _LOG.debug("Still waiting for MQTT ready... (%.1fs elapsed)", elapsed)

        _LOG.warning("MQTT ready timeout after %ds - proceeding anyway", timeout)

    async def disconnect_client(self) -> None:
        """Disconnect the lghorizon client."""
        if self._api:
            try:
                await self._api.disconnect()
            except Exception as e:
                _LOG.debug("Error disconnecting API: %s", e)
            self._api = None

        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

        self._lg_devices = {}
        self._auth = None

    def check_client_connected(self) -> bool:
        """Check if the lghorizon client is connected."""
        return self._api is not None and self._session is not None and not self._session.closed

    async def _on_device_state_change(self, device_id: str) -> None:
        """Handle device state change callback from lghorizon MQTT."""
        _LOG.debug("Device state changed: %s", device_id)
        state = await self.get_device_state(device_id)
        self.events.emit(DeviceEvents.UPDATE, device_id, state)

    async def get_device(self, device_id: str) -> LGDevice | None:
        """Get a specific device by ID."""
        return self._lg_devices.get(device_id)

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
