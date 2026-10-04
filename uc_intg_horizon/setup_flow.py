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
from lghorizon.exceptions import LGHorizonApiUnauthorizedError
from ucapi import RequestUserInput
from ucapi_framework import BaseSetupFlow

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.const import PROVIDER_TO_COUNTRY

_LOG = logging.getLogger(__name__)

_PROVIDERS = [
    {"id": "Ziggo", "label": {"en": "Ziggo (Netherlands)"}},
    {"id": "VirginMedia", "label": {"en": "Virgin Media (UK/Ireland)"}},
    {"id": "Telenet", "label": {"en": "Telenet (Belgium)"}},
    {"id": "UPC", "label": {"en": "UPC (Switzerland)"}},
    {"id": "Sunrise", "label": {"en": "Sunrise (Switzerland)"}},
]


class HorizonSetupFlow(BaseSetupFlow[HorizonConfig]):
    """Setup flow for Horizon integration.

    No pre-discovery screen and no discovery: the framework goes straight to the
    manual entry form and routes every submit of it to query_device(), so
    returning the form again (with an error) lets the user correct and resubmit.
    """

    def get_manual_entry_form(
        self,
        error: str | None = None,
        provider: str | None = None,
        username: str | None = None,
    ) -> RequestUserInput:
        # On setup "Update" prefill the saved provider/username (never the secret)
        saved = self.selected_config_entry
        if saved is not None:
            provider = provider or saved.provider
            username = username or saved.username

        fields: list[dict[str, Any]] = []
        if error:
            fields.append(
                {
                    "id": "error",
                    "label": {"en": "Error"},
                    "field": {"label": {"value": {"en": error}}},
                }
            )
        fields.extend(
            [
                {
                    "id": "provider",
                    "label": {"en": "Provider"},
                    "field": {
                        "dropdown": {
                            "value": provider or _PROVIDERS[0]["id"],
                            "items": _PROVIDERS,
                        }
                    },
                },
                {
                    "id": "username",
                    "label": {"en": "Username / Email"},
                    "field": {
                        "text": {
                            "value": username or "",
                            "placeholder": "your.email@example.com",
                        }
                    },
                },
                {
                    "id": "password",
                    "label": {"en": "Password (or Refresh Token)"},
                    "field": {"password": {}},
                },
            ]
        )
        return RequestUserInput({"en": "LG Horizon Setup"}, fields)

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> HorizonConfig | RequestUserInput:
        provider = (input_values.get("provider") or "").strip()
        username = (input_values.get("username") or "").strip()
        password = (input_values.get("password") or "").strip()

        if not all([provider, username, password]):
            return self.get_manual_entry_form(
                "Please fill in provider, username and password (or refresh token).",
                provider, username,
            )

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
            service_url = service_config.get_service_url("personalizationService")
            customer_data = await auth.request(
                service_url,
                f"/v1/customer/{auth.household_id}?with=profiles%2Cdevices",
            )

            assigned_devices = customer_data.get("assignedDevices", [])
            if not assigned_devices:
                return self.get_manual_entry_form(
                    "No set-top boxes found in this account. "
                    "Please verify your account has active set-top boxes.",
                    provider, username,
                )

            _LOG.info("Found %d device(s) in account", len(assigned_devices))

            for device in assigned_devices:
                device_id = device.get("deviceId", "")
                settings = device.get("settings", {})
                device_name = settings.get(
                    "deviceFriendlyName", f"Horizon Box ({device_id[-6:]})"
                )
                config.add_device(device_id, device_name)

            if getattr(auth, "refresh_token", None):
                new_token = auth.refresh_token
                if new_token != password:
                    config.password = new_token

            return config

        except LGHorizonApiUnauthorizedError as err:
            _LOG.error("Setup validation failed: credentials rejected (%s)", err)
            return self.get_manual_entry_form(
                "Login rejected by the provider. Check your username and "
                "password (or paste a fresh refresh token) and try again.",
                provider, username,
            )
        except Exception as err:  # pylint: disable=broad-except
            _LOG.error("Setup validation failed: %s", err)
            return self.get_manual_entry_form(
                f"Could not validate the account: {err}", provider, username
            )

        finally:
            if session and not session.closed:
                await session.close()
