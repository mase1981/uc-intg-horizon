"""
Setup flow manager for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
from typing import Any

from ucapi.api_definitions import (
    AbortDriverSetup,
    DriverSetupRequest,
    IntegrationSetupError,
    SetupAction,
    SetupComplete,
    SetupError,
    UserDataResponse,
)

from uc_intg_horizon.client import HorizonClient
from uc_intg_horizon.config import HorizonConfig

_LOG = logging.getLogger(__name__)


class SetupManager:
    """Manages the integration setup flow."""

    def __init__(self, config: HorizonConfig):
        self.config = config
        self._setup_step = "init"

    async def handle_setup(self, msg: SetupAction) -> SetupAction:
        if isinstance(msg, DriverSetupRequest):
            return await self._handle_driver_setup(msg)
        elif isinstance(msg, UserDataResponse):
            return await self._handle_user_data(msg)
        elif isinstance(msg, AbortDriverSetup):
            return await self._handle_abort(msg)
        else:
            _LOG.warning("Unknown setup message type: %s", type(msg))
            return SetupError(IntegrationSetupError.OTHER)

    async def _handle_driver_setup(self, msg: DriverSetupRequest) -> SetupAction:
        """
        Handle driver setup with consistent state filtering.
        
        KEY PRINCIPLE: Any device that reports a state to MQTT (including OFFLINE)
        is available and should be added to config. Entities can exist for offline devices.
        """
        _LOG.info("Starting driver setup (reconfigure=%s)", msg.reconfigure)
        
        try:
            setup_data = msg.setup_data
            provider = setup_data.get("provider")
            username = setup_data.get("username")
            password = setup_data.get("password")
            
            if not all([provider, username, password]):
                _LOG.error("Missing required setup fields")
                return SetupError(IntegrationSetupError.OTHER)
            
            self.config.update_setup_data(provider, username, password)
            
            _LOG.info("Testing connection to Horizon API...")
            client = HorizonClient(provider, username, password)
            
            if not await client.connect():
                _LOG.error("Failed to connect to Horizon API")
                return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
            
            _LOG.info("Connection successful - waiting for all devices to report states...")
            await asyncio.sleep(5)
            
            devices = await client.get_devices()
            _LOG.info("Found %d total devices from API", len(devices))
            
            if not devices:
                _LOG.warning("No devices found in account")
                return SetupError(IntegrationSetupError.NOT_FOUND)
            
            # NEW LOGIC: Any device with a reported state is available
            available_devices = []
            unavailable_devices = []
            
            for device in devices:
                device_id = device["device_id"]
                device_name = device["name"]
                device_state = device.get("state")
                
                # If device has ANY state (including OFFLINE states), it's available
                if device_state and device_state != "unavailable":
                    available_devices.append(device)
                    _LOG.info(f"  ✓ AVAILABLE: {device_name} ({device_id}) - State: {device_state}")
                else:
                    unavailable_devices.append(device)
                    _LOG.warning(f"  ✗ UNAVAILABLE: {device_name} ({device_id}) - No MQTT state")
            
            if unavailable_devices:
                _LOG.warning("=" * 70)
                _LOG.warning(f"⚠ Found {len(unavailable_devices)} UNAVAILABLE device(s)")
                _LOG.warning("These devices are NOT reporting to MQTT:")
                for d in unavailable_devices:
                    _LOG.warning(f"   - {d['name']} (ID: {d['device_id']})")
                _LOG.warning("")
                _LOG.warning("💡 To add these devices:")
                _LOG.warning("   1. Ensure boxes are connected to power and network")
                _LOG.warning("   2. Wait for them to establish MQTT connection")
                _LOG.warning("   3. Reconfigure this integration")
                _LOG.warning("=" * 70)
            
            if not available_devices:
                _LOG.error("No AVAILABLE devices found - cannot proceed")
                _LOG.error("All devices are not reporting to MQTT")
                _LOG.error("Please ensure at least one box is powered and connected")
                return SetupError(IntegrationSetupError.NOT_FOUND)
            
            # Clear and add only available devices
            self.config.devices = []
            
            for device in available_devices:
                device_id = device["device_id"]
                device_name = device["name"]
                device_state = device.get("state")
                
                self.config.add_device(
                    device_id=device_id,
                    name=device_name,
                )
                _LOG.info(f"  ✓ Added device: {device_name} (State: {device_state})")
            
            if not self.config.save_config():
                _LOG.error("Failed to save configuration")
                return SetupError(IntegrationSetupError.OTHER)
            
            _LOG.info("=" * 70)
            _LOG.info(f"✓ Setup completed successfully")
            _LOG.info(f"📝 Saved {len(available_devices)} available device(s) to configuration")
            if unavailable_devices:
                _LOG.info(f"⚠ Ignored {len(unavailable_devices)} unavailable device(s)")
            _LOG.info("=" * 70)
            
            await client.disconnect()
            
            return SetupComplete()
            
        except Exception as e:
            _LOG.error("Setup error: %s", e, exc_info=True)
            return SetupError(IntegrationSetupError.OTHER)

    async def _handle_user_data(self, msg: UserDataResponse) -> SetupAction:
        _LOG.info("Received user data: %s", msg.input_values.keys())
        return SetupComplete()

    async def _handle_abort(self, msg: AbortDriverSetup) -> SetupAction:
        _LOG.warning("Setup aborted: %s", msg.error)
        self._setup_step = "init"
        return SetupError(msg.error)