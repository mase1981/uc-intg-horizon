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
from ucapi import DriverSetupRequest, RequestUserInput, SetupAction
from ucapi_framework import BaseSetupFlow

from uc_intg_horizon.config import HorizonConfig

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

            device_ids = customer_data.get("assignedDevices", [])
            if not device_ids:
                raise ValueError(
                    "No devices found in your account\n"
                    "Please verify your account has active set-top boxes"
                )

            _LOG.info("Found %d device(s) in account", len(device_ids))

            for device_id in device_ids:
                config.add_device(device_id, f"Horizon Box ({device_id[-6:]})")
                _LOG.info("  Device: %s", device_id)

            if hasattr(auth, "refresh_token") and auth.refresh_token:
                if auth.refresh_token != password:
                    _LOG.info("Token was refreshed - updating config")
                    config.password = auth.refresh_token

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
            "Telenet": "be",
            "UPC": "ch",
            "Sunrise": "ch",
            "Magenta": "at",
        }
        return provider_map.get(provider, "nl")
