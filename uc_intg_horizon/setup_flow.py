"""
Setup flow for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging
import ssl
from typing import Any

import aiohttp
import certifi
from lghorizon import COUNTRY_SETTINGS, LGHorizonAuth
from ucapi import RequestUserInput, SetupAction
from ucapi_framework import BaseSetupFlow

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.const import PROVIDER_TO_COUNTRY

_LOG = logging.getLogger(__name__)


class HorizonSetupFlow(BaseSetupFlow[HorizonConfig]):
    """Setup flow for Horizon integration."""

    async def get_pre_discovery_screen(self) -> RequestUserInput | None:
        return self.get_manual_entry_form()

    async def _handle_discovery(self) -> SetupAction:
        if self._pre_discovery_data:
            provider = self._pre_discovery_data.get("provider")
            username = self._pre_discovery_data.get("username")
            password = self._pre_discovery_data.get("password")

            if not all([provider, username, password]):
                return self.get_manual_entry_form()

            try:
                result = await self.query_device(self._pre_discovery_data)
                if hasattr(result, "identifier"):
                    return await self._finalize_device_setup(result, self._pre_discovery_data)
                return result
            except Exception as err:
                _LOG.error("Discovery failed: %s", err)
                return self.get_manual_entry_form()

        return await self._handle_manual_entry()

    def get_manual_entry_form(self) -> RequestUserInput:
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
        provider = input_values.get("provider")
        username = input_values.get("username")
        password = input_values.get("password")

        if not all([provider, username, password]):
            return self.get_manual_entry_form()

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

        _LOG.info("Validating credentials for %s...", provider)

        session = None
        try:
            country_code = PROVIDER_TO_COUNTRY.get(provider, "nl")
            use_refresh_token = COUNTRY_SETTINGS.get(country_code, {}).get(
                "use_refreshtoken", False
            )

            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            session = aiohttp.ClientSession(connector=connector)

            if use_refresh_token:
                auth = LGHorizonAuth(
                    websession=session,
                    country_code=country_code,
                    username=username,
                    password="",
                    refresh_token=password,
                )
            else:
                auth = LGHorizonAuth(
                    websession=session,
                    country_code=country_code,
                    username=username,
                    password=password,
                )

            service_config = await auth.get_service_config()
            service_url = await service_config.get_service_url("personalizationService")
            customer_data = await auth.request(
                service_url,
                f"/v1/customer/{auth.household_id}?with=profiles%2Cdevices",
            )

            assigned_devices = customer_data.get("assignedDevices", [])
            if not assigned_devices:
                raise ValueError(
                    "No devices found in your account\n"
                    "Please verify your account has active set-top boxes"
                )

            _LOG.info("Found %d device(s) in account", len(assigned_devices))

            for device in assigned_devices:
                device_id = device.get("deviceId", "")
                settings = device.get("settings", {})
                device_name = settings.get(
                    "deviceFriendlyName", f"Horizon Box ({device_id[-6:]})"
                )
                config.add_device(device_id, device_name)

            if hasattr(auth, "refresh_token") and auth.refresh_token:
                new_token = auth.refresh_token
                if new_token != password:
                    config.password = new_token

            return config

        except Exception as err:
            _LOG.error("Setup validation failed: %s", err)
            raise ValueError(f"Setup failed: {err}") from err

        finally:
            if session and not session.closed:
                await session.close()
