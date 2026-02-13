"""
Setup flow for Horizon integration using ucapi-framework.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ucapi import DriverSetupRequest, RequestUserInput, SetupAction
from ucapi_framework import BaseSetupFlow

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)


class HorizonSetupFlow(BaseSetupFlow[HorizonConfig]):
    """Setup flow for Horizon integration using driver.json schema."""

    def __init__(self, *args, **kwargs):
        """Initialize with storage for initial setup_data."""
        super().__init__(*args, **kwargs)
        self._initial_setup_data: dict[str, Any] = {}

    async def _handle_driver_setup_request(
        self, msg: DriverSetupRequest
    ) -> SetupAction:
        """
        Handle initial setup request and store setup_data.

        The Remote sends credentials via driver.json setup_data_schema in msg.setup_data.
        We store this so we can use it after the restore prompt.
        """
        if msg.setup_data:
            self._initial_setup_data = dict(msg.setup_data)
            _LOG.info(
                "Stored initial setup_data: provider=%s, username=%s",
                self._initial_setup_data.get("provider"),
                self._initial_setup_data.get("username"),
            )

        return await super()._handle_driver_setup_request(msg)

    async def get_pre_discovery_screen(self) -> RequestUserInput | None:
        """
        Skip pre-discovery screen if we have setup_data from driver.json.

        The credentials were already provided via the driver.json setup_data_schema.
        Store them in _pre_discovery_data so they're available during discovery.
        """
        if self._initial_setup_data:
            self._pre_discovery_data = dict(self._initial_setup_data)
            _LOG.info("Using stored setup_data for discovery")
            return None
        return None

    async def _handle_discovery(self) -> SetupAction:
        """
        Handle device discovery.

        For Horizon, we use the credentials from driver.json (stored in _pre_discovery_data)
        to authenticate and discover STB devices via cloud API.
        This skips manual entry since credentials are already provided.
        """
        if self._pre_discovery_data:
            _LOG.info("Discovering devices using pre-stored credentials")
            try:
                result = await self.query_device(self._pre_discovery_data)
                if hasattr(result, "identifier"):
                    return await self._finalize_device_setup(
                        result, self._pre_discovery_data
                    )
                return result
            except Exception as err:
                _LOG.error("Discovery failed: %s", err)
                from ucapi import IntegrationSetupError, SetupError
                return SetupError(error_type=IntegrationSetupError.NOT_FOUND)

        return await self._handle_manual_entry()

    def get_manual_entry_form(self) -> RequestUserInput:
        """
        Return manual entry form for credentials.

        This is only shown if setup_data wasn't provided via driver.json.
        """
        return RequestUserInput(
            {"en": "LG Horizon Setup"},
            [
                {
                    "id": "provider",
                    "label": {"en": "Provider"},
                    "field": {
                        "dropdown": {
                            "items": [
                                {"id": "Ziggo", "label": {"en": "Ziggo (Netherlands)"}},
                                {"id": "VirginMedia", "label": {"en": "Virgin Media (UK/Ireland)"}},
                                {"id": "Telenet", "label": {"en": "Telenet (Belgium)"}},
                                {"id": "UPC", "label": {"en": "UPC (Switzerland)"}},
                                {"id": "Sunrise", "label": {"en": "Sunrise (Switzerland)"}},
                            ]
                        }
                    },
                },
                {
                    "id": "username",
                    "label": {"en": "Username / Email"},
                    "field": {"text": {"placeholder": "your.email@example.com"}},
                },
                {
                    "id": "password",
                    "label": {"en": "Password (or Refresh Token)"},
                    "field": {"password": {}},
                },
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> HorizonConfig | RequestUserInput:
        """
        Validate connection and discover devices.

        Called after user provides credentials via driver.json schema or manual entry.
        """
        provider = input_values.get("provider")
        username = input_values.get("username")
        password = input_values.get("password")

        if not all([provider, username, password]):
            raise ValueError("Missing required fields: provider, username, password")

        config_id = (
            f"{provider}_{username}".lower().replace("@", "_").replace(".", "_")
        )

        config = HorizonConfig(
            identifier=config_id,
            name=f"Horizon ({provider})",
            provider=provider,
            username=username,
            password=password,
        )

        _LOG.info("Testing connection to Horizon API (provider=%s)...", provider)

        test_device = HorizonDevice(config)

        try:
            if not await test_device.connect():
                raise ValueError(
                    f"Failed to connect to Horizon API\n"
                    f"Please verify your credentials for {provider}"
                )

            _LOG.info("Connection successful - waiting for device states...")
            await asyncio.sleep(5)

            api_devices = test_device.devices
            if not api_devices:
                await test_device.disconnect()
                raise ValueError(
                    "No devices found in your account\n"
                    "Please verify your account has active set-top boxes"
                )

            _LOG.info("Found %d devices from API", len(api_devices))

            available_count = 0
            unavailable_count = 0

            for device_id, device in api_devices.items():
                device_name = device.device_friendly_name
                state = device.device_state
                running_state = state.state if state else None

                if running_state is not None:
                    config.add_device(device_id, device_name)
                    available_count += 1
                    _LOG.info(
                        "  AVAILABLE: %s (%s) - State: %s",
                        device_name,
                        device_id,
                        running_state,
                    )
                else:
                    unavailable_count += 1
                    _LOG.warning(
                        "  UNAVAILABLE: %s (%s) - No MQTT state (device may be offline)",
                        device_name,
                        device_id,
                    )

            if unavailable_count > 0:
                _LOG.warning(
                    "%d device(s) unavailable (not reporting to MQTT)",
                    unavailable_count,
                )

            if not config.devices:
                await test_device.disconnect()
                raise ValueError(
                    "No available devices found\n"
                    "All devices appear to be offline or not connected to MQTT"
                )

            refreshed_token = test_device.get_refreshed_token()
            if refreshed_token and refreshed_token != password:
                _LOG.info("Token was refreshed during connection - updating config")
                config.password = refreshed_token

            await test_device.disconnect()

            _LOG.info(
                "Setup validated: %d device(s) available",
                len(config.devices),
            )

            return config

        except Exception as err:
            try:
                await test_device.disconnect()
            except Exception:
                pass
            raise ValueError(f"Setup failed: {err}") from err
