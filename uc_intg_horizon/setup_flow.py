"""
Setup flow for Horizon integration using ucapi-framework.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ucapi import RequestUserInput
from ucapi_framework import BaseSetupFlow

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)


class HorizonSetupFlow(BaseSetupFlow[HorizonConfig]):
    """Setup flow for Horizon integration using driver.json schema."""

    def get_manual_entry_form(self) -> RequestUserInput | None:
        """Return None to use driver.json setup_data_schema."""
        return None

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> HorizonConfig | RequestUserInput:
        """
        Validate connection and discover devices.

        Called after user provides credentials via driver.json schema.
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
