"""
Horizon device wrapper using lghorizon API with ucapi-framework.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
from datetime import datetime
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
from uc_intg_horizon.const import (
    CONNECT_RETRIES,
    CONNECT_RETRY_DELAY,
    DIGIT_ENTER_DELAY,
    DIGIT_KEY_DELAY,
    PROVIDER_TO_COUNTRY,
    RECONNECT_DELAY,
    WATCHDOG_INTERVAL,
)

_LOG = logging.getLogger(__name__)


class HorizonDevice(ExternalClientDevice):
    """Wrapper for lghorizon API using ucapi-framework ExternalClientDevice."""

    def __init__(self, device_config: HorizonConfig, **kwargs) -> None:
        super().__init__(
            device_config=device_config,
            enable_watchdog=True,
            watchdog_interval=WATCHDOG_INTERVAL,
            reconnect_delay=RECONNECT_DELAY,
            max_reconnect_attempts=0,
            **kwargs,
        )

        self._session: aiohttp.ClientSession | None = None
        self._auth: LGHorizonAuth | None = None
        self._api: LGHorizonApi | None = None
        self._lg_devices: dict[str, LGDevice] = {}
        self._token_needs_save: bool = False
        self._channels_loaded: bool = False

        os.environ["SSL_CERT_FILE"] = certifi.where()
        os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

        self._country_code = PROVIDER_TO_COUNTRY.get(device_config.provider, "nl")
        _LOG.info(
            "HorizonDevice initialized: provider=%s, country=%s",
            device_config.provider, self._country_code,
        )

    @property
    def identifier(self) -> str:
        return self._device_config.identifier

    @property
    def name(self) -> str:
        return self._device_config.name

    @property
    def address(self) -> str | None:
        return None

    @property
    def log_id(self) -> str:
        return f"Horizon-{self._device_config.provider}"

    @property
    def devices(self) -> dict[str, LGDevice]:
        return self._lg_devices

    @property
    def config(self) -> HorizonConfig:
        return self._device_config

    @property
    def token_needs_save(self) -> bool:
        return self._token_needs_save

    @property
    def channels_loaded(self) -> bool:
        return self._channels_loaded

    def mark_token_saved(self) -> None:
        self._token_needs_save = False

    def get_refreshed_token(self) -> str | None:
        if self._auth:
            return getattr(self._auth, "refresh_token", None)
        return None

    # -- ExternalClientDevice interface ----------------------------------------

    async def create_client(self) -> LGHorizonApi:
        if self._country_code not in COUNTRY_SETTINGS:
            raise ValueError(f"Unsupported country code: {self._country_code}")

        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self._session = aiohttp.ClientSession(connector=connector)

        token = self._device_config.password
        _LOG.info(
            "Using refresh token auth for %s (token: %s...)",
            self._country_code.upper(),
            token[:20] if token and len(token) > 20 else token,
        )
        self._auth = LGHorizonAuth(
            websession=self._session,
            country_code=self._country_code,
            username=self._device_config.username,
            password="",
            refresh_token=self._device_config.password,
            token_refresh_callback=self._on_token_refreshed,
        )
        self._auth._use_refresh_token = True

        self._api = LGHorizonApi(auth=self._auth, profile_id="")
        return self._api

    async def connect_client(self) -> None:
        if not self._api:
            raise RuntimeError("API not initialized")

        last_err: Exception | None = None
        original_refresh_channels = self._api._refresh_channels

        for attempt in range(CONNECT_RETRIES):
            try:
                async def _deferred_channels():
                    pass

                self._api._refresh_channels = _deferred_channels
                _LOG.info("Starting lightweight initialization (channels deferred)...")

                await self._api.initialize()
                self._lg_devices = await self._api.get_devices()

                for device_id, device in self._lg_devices.items():
                    await device.set_callback(self._on_device_state_change)

                _LOG.info(
                    "Connected to Horizon API. Devices: %d. Loading channels in background...",
                    len(self._lg_devices),
                )

                asyncio.create_task(
                    self._load_channels_background(original_refresh_channels)
                )
                return

            except Exception as err:
                last_err = err
                if attempt < CONNECT_RETRIES - 1:
                    _LOG.warning(
                        "[%s] Connection attempt %d/%d failed: %s, retrying in %ds",
                        self.log_id, attempt + 1, CONNECT_RETRIES, err, CONNECT_RETRY_DELAY,
                    )
                    await asyncio.sleep(CONNECT_RETRY_DELAY)

        _LOG.error("[%s] All connection attempts failed", self.log_id)
        await self.disconnect_client()
        raise last_err  # type: ignore[misc]

    async def disconnect_client(self) -> None:
        if self._api:
            try:
                await self._api.disconnect()
            except Exception as err:
                _LOG.debug("Error disconnecting API: %s", err)
            self._api = None

        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

        self._lg_devices = {}
        self._auth = None
        self._channels_loaded = False

    def check_client_connected(self) -> bool:
        return (
            self._api is not None
            and self._session is not None
            and not self._session.closed
            and bool(self._lg_devices)
        )

    # -- Token management ------------------------------------------------------

    def _on_token_refreshed(self, new_token: str) -> None:
        old_token = self._device_config.password
        if new_token and new_token != old_token:
            _LOG.info(
                "Token refreshed by API (old: %s... new: %s...)",
                old_token[:20] if old_token and len(old_token) > 20 else old_token,
                new_token[:20] if len(new_token) > 20 else new_token,
            )
            self._device_config.password = new_token
            self._token_needs_save = True

    # -- Background tasks ------------------------------------------------------

    async def _load_channels_background(self, refresh_channels_func) -> None:
        try:
            _LOG.debug("Background channel loading started...")
            await refresh_channels_func()
            self._channels_loaded = True
            _LOG.info("Background channel loading completed")
        except Exception as err:
            _LOG.warning("Background channel loading failed: %s", err)

    # -- State callbacks -------------------------------------------------------

    async def _on_device_state_change(self, device_id: str) -> None:
        _LOG.debug("Device state changed: %s", device_id)
        state = self.get_device_state(device_id)
        horizon_state = state.get("state", "unavailable")
        if horizon_state == "ONLINE_RUNNING":
            uc_state = "PAUSED" if state.get("paused") else "PLAYING"
        elif horizon_state == "ONLINE_STANDBY":
            uc_state = "STANDBY"
        elif horizon_state == "OFFLINE":
            uc_state = "OFF"
        else:
            uc_state = "UNAVAILABLE"
        self.events.emit(DeviceEvents.UPDATE, device_id, {"state": uc_state})

    # -- Device state ----------------------------------------------------------

    async def get_device(self, device_id: str) -> LGDevice | None:
        return self._lg_devices.get(device_id)

    def get_device_state(self, device_id: str) -> dict[str, Any]:
        device = self._lg_devices.get(device_id)
        if not device:
            return {"state": "unavailable"}

        try:
            state = device.device_state
            running_state = state.state if state else None

            result: dict[str, Any] = {
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
                result["media_title"] = (
                    getattr(state, "show_title", None) or getattr(state, "title", None)
                )
                result["media_image"] = getattr(state, "image", None)
                result["start_time"] = getattr(state, "start_time", None)
                result["end_time"] = getattr(state, "end_time", None)
                result["position"] = getattr(state, "position", None)
                result["duration"] = getattr(state, "duration", None)
                result["paused"] = getattr(state, "paused", False)

            return result

        except Exception as err:
            _LOG.error("Failed to get state for %s: %s", device_id, err)
            return {"state": "unavailable"}

    @staticmethod
    def _running_state_to_string(state: LGHorizonRunningState | None) -> str:
        if state is None:
            return "unavailable"
        if state == LGHorizonRunningState.ONLINE_RUNNING:
            return "ONLINE_RUNNING"
        if state == LGHorizonRunningState.ONLINE_STANDBY:
            return "ONLINE_STANDBY"
        if state == LGHorizonRunningState.OFFLINE:
            return "OFFLINE"
        return "unavailable"

    # -- Commands --------------------------------------------------------------

    async def power_on(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.turn_on()
            return True
        except Exception as err:
            _LOG.error("Power ON failed for %s: %s", device_id, err)
            return False

    async def power_off(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.turn_off()
            return True
        except Exception as err:
            _LOG.error("Power OFF failed for %s: %s", device_id, err)
            return False

    async def power_toggle(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.send_key_to_box("Power")
            return True
        except Exception as err:
            _LOG.error("Power toggle failed for %s: %s", device_id, err)
            return False

    async def play(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.play()
            return True
        except Exception as err:
            _LOG.error("Play failed for %s: %s", device_id, err)
            return False

    async def pause(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.pause()
            return True
        except Exception as err:
            _LOG.error("Pause failed for %s: %s", device_id, err)
            return False

    async def stop(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.stop()
            return True
        except Exception as err:
            _LOG.error("Stop failed for %s: %s", device_id, err)
            return False

    async def next_channel(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.next_channel()
            return True
        except Exception as err:
            _LOG.error("Next channel failed for %s: %s", device_id, err)
            return False

    async def previous_channel(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.previous_channel()
            return True
        except Exception as err:
            _LOG.error("Previous channel failed for %s: %s", device_id, err)
            return False

    async def fast_forward(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.fast_forward()
            return True
        except Exception as err:
            _LOG.error("Fast forward failed for %s: %s", device_id, err)
            return False

    async def rewind(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.rewind()
            return True
        except Exception as err:
            _LOG.error("Rewind failed for %s: %s", device_id, err)
            return False

    async def record(self, device_id: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.record()
            return True
        except Exception as err:
            _LOG.error("Record failed for %s: %s", device_id, err)
            return False

    async def seek(self, device_id: str, position_seconds: int) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.set_player_position(position_seconds)
            return True
        except Exception as err:
            _LOG.error("Seek failed for %s: %s", device_id, err)
            return False

    async def send_key(self, device_id: str, key: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.send_key_to_box(key)
            return True
        except Exception as err:
            _LOG.error("Send key '%s' failed for %s: %s", key, device_id, err)
            return False

    async def set_channel(self, device_id: str, channel_name: str) -> bool:
        device = await self.get_device(device_id)
        if not device:
            return False
        try:
            await device.set_channel(channel_name)
            return True
        except Exception as err:
            _LOG.error("Set channel failed for %s: %s", device_id, err)
            return False

    async def set_channel_by_number(self, device_id: str, channel_number: str) -> bool:
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
                await asyncio.sleep(DIGIT_KEY_DELAY)

            await asyncio.sleep(DIGIT_ENTER_DELAY)
            await device.send_key_to_box("Enter")
            return True

        except Exception as err:
            _LOG.error("Set channel %s failed for %s: %s", channel_number, device_id, err)
            return False

    async def get_channels(self) -> list[dict[str, str]]:
        if not self._api:
            return []
        try:
            channels = await self._api.get_profile_channels()
            return [{"id": ch.id, "name": ch.title} for ch in channels.values()]
        except Exception as err:
            _LOG.error("Failed to get channels: %s", err)
            return []

    # -- Position/duration calculation -----------------------------------------

    @staticmethod
    def calculate_position_duration(
        start_time: Any, end_time: Any, position: int | None = None
    ) -> tuple[int, int]:
        try:
            def _to_datetime(val: Any) -> datetime:
                if isinstance(val, (int, float)):
                    return datetime.fromtimestamp(val)
                return datetime.fromisoformat(str(val))

            if start_time and end_time:
                start_dt = _to_datetime(start_time)
                end_dt = _to_datetime(end_time)
                duration = int((end_dt - start_dt).total_seconds())

                if position is not None:
                    return (int(position), duration)

                now = datetime.now()
                pos = max(0, min(int((now - start_dt).total_seconds()), duration))
                return (pos, duration)

        except Exception:
            pass

        return (0, 0)
