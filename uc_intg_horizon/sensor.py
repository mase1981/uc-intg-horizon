"""
Sensor entities for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from ucapi import Sensor
from ucapi.sensor import Attributes, DeviceClasses, States

if TYPE_CHECKING:
    import ucapi
    from uc_intg_horizon.device import HorizonDevice

_LOG = logging.getLogger(__name__)


class _BaseSensor(Sensor):
    """Base sensor with common update pattern."""

    def __init__(
        self,
        entity_id: str,
        name: str,
        horizon_device: HorizonDevice,
        device_id: str,
        api: ucapi.IntegrationAPI,
    ) -> None:
        self._device_id = device_id
        self._horizon_device = horizon_device
        self._api = api

        super().__init__(
            identifier=entity_id,
            name=name,
            features=[],
            attributes={Attributes.STATE: States.UNAVAILABLE, Attributes.VALUE: ""},
            device_class=DeviceClasses.CUSTOM,
        )

    def _push_if_configured(self) -> None:
        if self._api and self._api.configured_entities.contains(self.id):
            self._api.configured_entities.update_attributes(self.id, self.attributes)

    async def update_state(self, device_state: dict[str, Any]) -> None:
        raise NotImplementedError

    async def push_update(self) -> None:
        state = self._horizon_device.get_device_state(self._device_id)
        await self.update_state(state)


class HorizonDeviceStateSensor(_BaseSensor):
    """Sensor entity for device connection state."""

    def __init__(
        self, device_id: str, device_name: str, horizon_device: HorizonDevice,
        api: ucapi.IntegrationAPI,
    ) -> None:
        super().__init__(
            f"{device_id}_state", f"{device_name} State",
            horizon_device, device_id, api,
        )

    async def update_state(self, device_state: dict[str, Any]) -> None:
        horizon_state = device_state.get("state", "unavailable")
        if horizon_state in ("ONLINE_RUNNING", "ONLINE_STANDBY", "OFFLINE"):
            self.attributes[Attributes.STATE] = States.ON
            self.attributes[Attributes.VALUE] = horizon_state
        else:
            self.attributes[Attributes.STATE] = States.UNAVAILABLE
            self.attributes[Attributes.VALUE] = "Unknown"
        self._push_if_configured()


class HorizonChannelSensor(_BaseSensor):
    """Sensor entity for current channel."""

    def __init__(
        self, device_id: str, device_name: str, horizon_device: HorizonDevice,
        api: ucapi.IntegrationAPI,
    ) -> None:
        super().__init__(
            f"{device_id}_channel", f"{device_name} Channel",
            horizon_device, device_id, api,
        )

    async def update_state(self, device_state: dict[str, Any]) -> None:
        channel = device_state.get("channel", "")
        self.attributes[Attributes.STATE] = States.ON
        self.attributes[Attributes.VALUE] = channel or "No Channel"
        self._push_if_configured()


class HorizonProgramSensor(_BaseSensor):
    """Sensor entity for current program."""

    def __init__(
        self, device_id: str, device_name: str, horizon_device: HorizonDevice,
        api: ucapi.IntegrationAPI,
    ) -> None:
        super().__init__(
            f"{device_id}_program", f"{device_name} Program",
            horizon_device, device_id, api,
        )

    async def update_state(self, device_state: dict[str, Any]) -> None:
        title = device_state.get("media_title", "")
        self.attributes[Attributes.STATE] = States.ON
        self.attributes[Attributes.VALUE] = title or "No Program"
        self._push_if_configured()
