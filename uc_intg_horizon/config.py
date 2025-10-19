"""
Configuration management for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import json
import logging
import os
from typing import Any

_LOG = logging.getLogger(__name__)


class HorizonConfig:
    """Manages Horizon integration configuration with persistence."""

    def __init__(self, config_path: str = "config.json"):
        """
        Initialize configuration manager.

        :param config_path: Path to configuration file
        """
        self.config_path = config_path
        self.provider: str | None = None
        self.username: str | None = None
        self.password: str | None = None
        self.devices: list[dict[str, Any]] = []
        
        # Load existing configuration if available
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if not os.path.exists(self.config_path):
            _LOG.debug("No configuration file found at %s", self.config_path)
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as file:
                config = json.load(file)
                self.provider = config.get("provider")
                self.username = config.get("username")
                self.password = config.get("password")
                self.devices = config.get("devices", [])
                _LOG.info(
                    "Configuration loaded: provider=%s, username=%s, devices=%d",
                    self.provider,
                    self.username,
                    len(self.devices),
                )
        except Exception as e:
            _LOG.error("Failed to load configuration: %s", e)

    def save_config(self) -> bool:
        """
        Save configuration to file.

        :return: True if successful, False otherwise
        """
        try:
            config = {
                "provider": self.provider,
                "username": self.username,
                "password": self.password,
                "devices": self.devices,
            }
            
            with open(self.config_path, "w", encoding="utf-8") as file:
                json.dump(config, file, indent=2)
                
            _LOG.info("Configuration saved successfully")
            return True
        except Exception as e:
            _LOG.error("Failed to save configuration: %s", e)
            return False

    def reload_from_disk(self) -> None:
        """Reload configuration from disk (for reboot survival)."""
        _LOG.info("Reloading configuration from disk...")
        self._load_config()

    def update_setup_data(self, provider: str, username: str, password: str) -> None:
        """
        Update setup data.

        :param provider: Provider name (Ziggo, VirginMedia, etc.)
        :param username: Account username/email
        :param password: Account password or refresh token
        """
        self.provider = provider
        self.username = username
        self.password = password
        _LOG.info("Setup data updated: provider=%s, username=%s", provider, username)

    def add_device(self, device_id: str, name: str, ip_address: str | None = None) -> None:
        """
        Add a device to configuration.

        :param device_id: Unique device identifier
        :param name: Device name
        :param ip_address: Optional IP address for direct connection
        """
        device = {
            "device_id": device_id,
            "name": name,
            "ip_address": ip_address,
        }
        
        # Check if device already exists
        for i, existing_device in enumerate(self.devices):
            if existing_device.get("device_id") == device_id:
                self.devices[i] = device
                _LOG.info("Device updated: %s (%s)", name, device_id)
                return
        
        self.devices.append(device)
        _LOG.info("Device added: %s (%s)", name, device_id)

    def remove_device(self, device_id: str) -> bool:
        """
        Remove a device from configuration.

        :param device_id: Device identifier to remove
        :return: True if device was removed, False if not found
        """
        for i, device in enumerate(self.devices):
            if device.get("device_id") == device_id:
                removed = self.devices.pop(i)
                _LOG.info("Device removed: %s", removed.get("name"))
                return True
        
        _LOG.warning("Device not found for removal: %s", device_id)
        return False

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """
        Get device by ID.

        :param device_id: Device identifier
        :return: Device dict or None if not found
        """
        for device in self.devices:
            if device.get("device_id") == device_id:
                return device
        return None

    def is_configured(self) -> bool:
        """
        Check if integration is configured.

        :return: True if configured with at least provider and username
        """
        return bool(self.provider and self.username)

    def clear_config(self) -> None:
        """Clear all configuration data."""
        self.provider = None
        self.username = None
        self.password = None
        self.devices = []
        _LOG.info("Configuration cleared")

    def __repr__(self) -> str:
        """String representation of configuration."""
        return (
            f"HorizonConfig(provider={self.provider}, "
            f"username={self.username}, "
            f"devices={len(self.devices)})"
        )