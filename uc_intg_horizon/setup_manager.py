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
            
            online_devices = []
            offline_devices = []
            
            for device in devices:
                device_id = device["device_id"]
                device_name = device["name"]
                device_state = device.get("state")
                
                if device_state == "OFFLINE":
                    offline_devices.append(device)
                    _LOG.warning(f"  ⚠️  OFFLINE: {device_name} ({device_id}) - {device_state}")
                else:
                    online_devices.append(device)
                    _LOG.info(f"  ✅ AVAILABLE: {device_name} ({device_id}) - State: {device_state}")
            
            if offline_devices:
                _LOG.warning("=" * 70)
                _LOG.warning(f"⚠️  Found {len(offline_devices)} OFFLINE device(s)")
                _LOG.warning("These devices will NOT be added to the integration:")
                for d in offline_devices:
                    _LOG.warning(f"   - {d['name']} (ID: {d['device_id']})")
                _LOG.warning("")
                _LOG.warning("💡 To add these devices:")
                _LOG.warning("   1. Power on the offline box(es)")
                _LOG.warning("   2. Wait for them to fully boot and connect")
                _LOG.warning("   3. Reconfigure this integration")
                _LOG.warning("=" * 70)
            
            if not online_devices:
                _LOG.error("No AVAILABLE devices found - cannot proceed")
                _LOG.error("All devices are explicitly OFFLINE")
                _LOG.error("Please power on at least one Horizon box and try again")
                return SetupError(IntegrationSetupError.NOT_FOUND)
            
            self.config.devices = []
            
            for device in online_devices:
                device_id = device["device_id"]
                device_name = device["name"]
                
                self.config.add_device(
                    device_id=device_id,
                    name=device_name,
                )
                _LOG.info(f"✅ Added available device: {device_name} (ID: {device_id})")
            
            if not self.config.save_config():
                _LOG.error("Failed to save configuration")
                return SetupError(IntegrationSetupError.OTHER)
            
            _LOG.info("=" * 70)
            _LOG.info(f"✅ Setup completed successfully")
            _LOG.info(f"📝 Saved {len(online_devices)} available device(s) to configuration")
            if offline_devices:
                _LOG.info(f"⚠️  Ignored {len(offline_devices)} offline device(s)")
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