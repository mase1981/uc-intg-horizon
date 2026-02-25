"""
Setup flow for Horizon integration using ucapi-framework.

:copyright: (c) 2025 by Meir Miyara.
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

_LOG = logging.getLogger(__name__)


class HorizonSetupFlow(BaseSetupFlow[HorizonConfig]):
    """Setup flow for Horizon integration."""

    async def get_pre_discovery_screen(self) -> RequestUserInput | None:
        """
        Show manual entry form since driver.json only has info screen.

        This ensures credentials are collected via setup_flow.py, making the
        integration resilient to backup/restore and reconfigure flows where
        the Remote may not pass setup_data.
        """
        return self.get_manual_entry_form()

    async def _handle_discovery(self) -> SetupAction:
        """
        Handle device discovery.

        Uses credentials from _pre_discovery_data (collected via get_pre_discovery_screen)
        to authenticate and discover STB devices via cloud API.
        """
        if self._pre_discovery_data:
            provider = self._pre_discovery_data.get("provider")
            username = self._pre_discovery_data.get("username")
            password = self._pre_discovery_data.get("password")

            if not all([provider, username, password]):
                _LOG.info("Missing credentials in pre_discovery_data, showing form")
                return self.get_manual_entry_form()

            _LOG.info("Discovering devices using credentials")
            try:
                result = await self.query_device(self._pre_discovery_data)
                if hasattr(result, "identifier"):
                    return await self._finalize_device_setup(
                        result, self._pre_discovery_data
                    )
                return result
            except Exception as err:
                _LOG.error("Discovery failed: %s", err)
                return self.get_manual_entry_form()

        return await self._handle_manual_entry()

    def get_manual_entry_form(self) -> RequestUserInput:
        """Return manual entry form for provider and credentials."""
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
        Validate connection and discover devices using LIGHTWEIGHT auth-only flow.

        This bypasses the full initialize() which fetches channels and connects MQTT.
        For setup, we only need to:
        1. Authenticate
        2. Get customer info with device list
        3. Return config with devices

        Full initialization happens later when integration actually runs.
        """
        provider = input_values.get("provider")
        username = input_values.get("username")
        password = input_values.get("password")

        if not all([provider, username, password]):
            _LOG.info("Missing required fields, returning manual entry form")
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

        _LOG.info("Validating credentials for %s (lightweight check)...", provider)

        session = None
        try:
            country_code = self._get_country_code(provider)
            use_refresh_token = COUNTRY_SETTINGS.get(country_code, {}).get(
                "use_refreshtoken", False
            )

            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            session = aiohttp.ClientSession(connector=connector)

            if use_refresh_token:
                _LOG.info("Using refresh token authentication for %s", country_code.upper())
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

            _LOG.info("Fetching service configuration...")
            service_config = await auth.get_service_config()

            _LOG.info("Fetching customer info with devices...")
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
                device_name = settings.get("deviceFriendlyName", f"Horizon Box ({device_id[-6:]})")
                config.add_device(device_id, device_name)
                _LOG.info("  Device: %s (%s)", device_name, device_id)

            if hasattr(auth, "refresh_token") and auth.refresh_token:
                new_token = auth.refresh_token
                if new_token != password:
                    _LOG.info(
                        "Token was refreshed - saving (token: %s...)",
                        new_token[:20] if len(new_token) > 20 else new_token,
                    )
                    config.password = new_token
                else:
                    _LOG.info(
                        "Using provided token (token: %s...)",
                        password[:20] if password and len(password) > 20 else password,
                    )

            _LOG.info("Setup validated: %d device(s) found", len(config.devices))
            return config

        except Exception as err:
            _LOG.error("Setup validation failed: %s", err)
            raise ValueError(f"Setup failed: {err}") from err

        finally:
            if session and not session.closed:
                await session.close()

    def _get_country_code(self, provider: str) -> str:
        """Map provider name to country code."""
        provider_map = {
            "Ziggo": "nl",
            "VirginMedia": "gb",
            "Telenet": "be-nl",
            "UPC": "ch",
            "Sunrise": "ch",
        }
        return provider_map.get(provider, "nl")
