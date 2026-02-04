"""
Sensor entities for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import logging
from typing import Any

from ucapi import Sensor
from ucapi.sensor import Attributes, DeviceClasses, States

from uc_intg_horizon.client import HorizonClient

_LOG = logging.getLogger(__name__)


class HorizonDeviceStateSensor(Sensor):
    """Sensor entity for device connection state."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        client: HorizonClient,
        api,
    ):
        self._device_id = device_id
        self._client = client
        self._api = api

        entity_id = f"{device_id}_state"

        attributes = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.VALUE: "Unknown",
        }

        super().__init__(
            identifier=entity_id,
            name=f"{device_name} State",
            features=[],
            attributes=attributes,
            device_class=DeviceClasses.CUSTOM,
        )

        _LOG.info("Initialized Horizon Device State Sensor: %s (%s)", device_name, entity_id)

    async def update_state(self, device_state: dict[str, Any]) -> None:
        """Update sensor state from device state."""
        try:
            horizon_state = device_state.get("state", "unavailable")

            if horizon_state in ["ONLINE_RUNNING", "ONLINE_STANDBY", "OFFLINE", "OFFLINE_NETWORK_STANDBY"]:
                self.attributes[Attributes.STATE] = States.ON
                self.attributes[Attributes.VALUE] = horizon_state
            else:
                self.attributes[Attributes.STATE] = States.UNAVAILABLE
                self.attributes[Attributes.VALUE] = "Unknown"

            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
                _LOG.debug("Updated device state sensor: %s", horizon_state)

        except Exception as e:
            _LOG.error("Failed to update device state sensor: %s", e)


class HorizonChannelSensor(Sensor):
    """Sensor entity for current channel."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        client: HorizonClient,
        api,
    ):
        self._device_id = device_id
        self._client = client
        self._api = api

        entity_id = f"{device_id}_channel"

        attributes = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.VALUE: "",
        }

        super().__init__(
            identifier=entity_id,
            name=f"{device_name} Channel",
            features=[],
            attributes=attributes,
            device_class=DeviceClasses.CUSTOM,
        )

        _LOG.info("Initialized Horizon Channel Sensor: %s (%s)", device_name, entity_id)

    async def update_state(self, device_state: dict[str, Any]) -> None:
        """Update sensor state from device state."""
        try:
            channel_name = device_state.get("channel", "")

            if channel_name:
                self.attributes[Attributes.STATE] = States.ON
                self.attributes[Attributes.VALUE] = channel_name
            else:
                self.attributes[Attributes.STATE] = States.ON
                self.attributes[Attributes.VALUE] = "No Channel"

            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
                _LOG.debug("Updated channel sensor: %s", channel_name or "No Channel")

        except Exception as e:
            _LOG.error("Failed to update channel sensor: %s", e)


class HorizonProgramSensor(Sensor):
    """Sensor entity for current program."""

    def __init__(
        self,
        device_id: str,
        device_name: str,
        client: HorizonClient,
        api,
    ):
        self._device_id = device_id
        self._client = client
        self._api = api

        entity_id = f"{device_id}_program"

        attributes = {
            Attributes.STATE: States.UNAVAILABLE,
            Attributes.VALUE: "",
        }

        super().__init__(
            identifier=entity_id,
            name=f"{device_name} Program",
            features=[],
            attributes=attributes,
            device_class=DeviceClasses.CUSTOM,
        )

        _LOG.info("Initialized Horizon Program Sensor: %s (%s)", device_name, entity_id)

    async def update_state(self, device_state: dict[str, Any]) -> None:
        """Update sensor state from device state."""
        try:
            program_title = device_state.get("media_title", "")

            if program_title:
                self.attributes[Attributes.STATE] = States.ON
                self.attributes[Attributes.VALUE] = program_title
            else:
                self.attributes[Attributes.STATE] = States.ON
                self.attributes[Attributes.VALUE] = "No Program"

            if self._api and self._api.configured_entities.contains(self.id):
                self._api.configured_entities.update_attributes(self.id, self.attributes)
                _LOG.debug("Updated program sensor: %s", program_title or "No Program")

        except Exception as e:
            _LOG.error("Failed to update program sensor: %s", e)
