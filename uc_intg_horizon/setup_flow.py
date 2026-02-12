"""
Setup flow for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ucapi.api_definitions import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    SetupAction,
    SetupComplete,
    SetupError,
    UserDataResponse,
)

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.device import HorizonDevice

if TYPE_CHECKING:
    from uc_intg_horizon.driver import HorizonDriver

_LOG = logging.getLogger(__name__)


class HorizonSetupFlow:
    """Setup flow handler for Horizon integration."""

    def __init__(self, driver: HorizonDriver) -> None:
        """Initialize the setup flow."""
        self._driver = driver
        self._setup_device: HorizonDevice | None = None

    async def handle_setup(self, msg: SetupAction) -> SetupAction:
        """Handle setup messages."""
        if isinstance(msg, DriverSetupRequest):
            return await self._handle_driver_setup(msg)
        elif isinstance(msg, UserDataResponse):
            return await self._handle_user_data(msg)
        elif isinstance(msg, AbortDriverSetup):
            return await self._handle_abort(msg)
        else:
            _LOG.warning("Unknown setup message type: %s", type(msg))
            return SetupError(IntegrationSetupError.OTHER)

    async def _handle_driver_setup(self, msg: DriverSetupRequest) -> SetupAction:
        """Handle driver setup request with device discovery."""
        _LOG.info("Starting driver setup (reconfigure=%s)", msg.reconfigure)

        try:
            setup_data = msg.setup_data
            provider = setup_data.get("provider")
            username = setup_data.get("username")
            password = setup_data.get("password")

            if not all([provider, username, password]):
                _LOG.error("Missing required setup fields")
                return SetupError(IntegrationSetupError.OTHER)

            config_id = f"{provider}_{username}".lower().replace("@", "_").replace(".", "_")
            config = HorizonConfig(
                identifier=config_id,
                name=f"Horizon ({provider})",
                provider=provider,
                username=username,
                password=password,
            )

            _LOG.info("Testing connection to Horizon API...")
            self._setup_device = HorizonDevice(config)

            if not await self._setup_device.connect():
                _LOG.error("Failed to connect to Horizon API")
                await self._cleanup_setup_device()
                return SetupError(IntegrationSetupError.CONNECTION_REFUSED)

            _LOG.info("Connection successful - waiting for device states...")
            await asyncio.sleep(5)

            api_devices = self._setup_device.devices

            if not api_devices:
                _LOG.warning("No devices found in account")
                await self._cleanup_setup_device()
                return SetupError(IntegrationSetupError.NOT_FOUND)

            _LOG.info("Found %d total devices from API", len(api_devices))

            available_devices = []
            unavailable_devices = []

            for device_id, device in api_devices.items():
                device_name = device.device_friendly_name
                state = device.device_state
                running_state = state.state if state else None

                if running_state is not None:
                    available_devices.append((device_id, device_name, running_state))
                    _LOG.info(
                        "  AVAILABLE: %s (%s) - State: %s",
                        device_name,
                        device_id,
                        running_state,
                    )
                else:
                    unavailable_devices.append((device_id, device_name))
                    _LOG.warning(
                        "  UNAVAILABLE: %s (%s) - No MQTT state",
                        device_name,
                        device_id,
                    )

            if unavailable_devices:
                _LOG.warning(
                    "Found %d UNAVAILABLE device(s) not reporting to MQTT",
                    len(unavailable_devices),
                )

            if not available_devices:
                _LOG.error("No AVAILABLE devices found")
                await self._cleanup_setup_device()
                return SetupError(IntegrationSetupError.NOT_FOUND)

            for device_id, device_name, _ in available_devices:
                config.add_device(device_id, device_name)
                _LOG.info("  Added device: %s (%s)", device_name, device_id)

            refreshed_token = self._setup_device.get_refreshed_token()
            if refreshed_token and refreshed_token != password:
                _LOG.info("Token was refreshed during connection, updating config")
                config.password = refreshed_token

            await self._cleanup_setup_device()

            self._driver.config_manager.add(config)
            await self._driver.config_manager.save()

            _LOG.info(
                "Setup completed: %d device(s) configured",
                len(available_devices),
            )

            return SetupComplete()

        except Exception as e:
            _LOG.error("Setup error: %s", e, exc_info=True)
            await self._cleanup_setup_device()
            return SetupError(IntegrationSetupError.OTHER)

    async def _handle_user_data(self, msg: UserDataResponse) -> SetupAction:
        """Handle user data response."""
        _LOG.info("Received user data: %s", msg.input_values.keys())
        return SetupComplete()

    async def _handle_abort(self, msg: AbortDriverSetup) -> SetupAction:
        """Handle setup abort."""
        _LOG.warning("Setup aborted: %s", msg.error)
        await self._cleanup_setup_device()
        return SetupError(msg.error)

    async def _cleanup_setup_device(self) -> None:
        """Clean up setup device connection."""
        if self._setup_device:
            await self._setup_device.disconnect()
            self._setup_device = None
