"""
Configuration for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HorizonDeviceConfig:
    """Configuration for a single Horizon set-top box."""

    device_id: str
    name: str


@dataclass
class HorizonConfig:
    """Configuration for a Horizon account (supports multiple STBs)."""

    identifier: str
    name: str
    provider: str
    username: str
    password: str
    devices: list[HorizonDeviceConfig] = field(default_factory=list)

    def __post_init__(self):
        converted = []
        for device in self.devices:
            if isinstance(device, dict):
                converted.append(HorizonDeviceConfig(**device))
            else:
                converted.append(device)
        self.devices = converted

    def add_device(self, device_id: str, name: str) -> None:
        for existing in self.devices:
            if existing.device_id == device_id:
                existing.name = name
                return
        self.devices.append(HorizonDeviceConfig(device_id=device_id, name=name))

    def remove_device(self, device_id: str) -> bool:
        for i, device in enumerate(self.devices):
            if device.device_id == device_id:
                self.devices.pop(i)
                return True
        return False

    def get_device(self, device_id: str) -> HorizonDeviceConfig | None:
        for device in self.devices:
            if device.device_id == device_id:
                return device
        return None
