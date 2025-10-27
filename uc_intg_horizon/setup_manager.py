"""
Setup flow manager for Horizon integration.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

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
        """
        Initialize setup manager.

        :param config: Configuration instance
        """
        self.config = config
        self._setup_step = "init"

    async def handle_setup(self, msg: SetupAction) -> SetupAction:
        """
        Handle setup messages from Remote.

        :param msg: Setup message
        :return: Setup action response
        """
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
        Handle initial driver setup request.

        :param msg: Driver setup request
        :return: Setup action
        """
        _LOG.info("Starting driver setup (reconfigure=%s)", msg.reconfigure)
        
        try:
            # Extract setup data
            setup_data = msg.setup_data
            provider = setup_data.get("provider")
            username = setup_data.get("username")
            password = setup_data.get("password")
            
            if not all([provider, username, password]):
                _LOG.error("Missing required setup fields")
                return SetupError(IntegrationSetupError.OTHER)
            
            # Save to configuration
            self.config.update_setup_data(provider, username, password)
            
            # Test connection
            _LOG.info("Testing connection to Horizon API...")
            client = HorizonClient(provider, username, password)
            
            if not await client.connect():
                _LOG.error("Failed to connect to Horizon API")
                return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
            
            # Get devices from API
            devices = await client.get_devices()
            _LOG.info("Found %d total devices from API", len(devices))
            
            if not devices:
                _LOG.warning("No devices found in account")
                return SetupError(IntegrationSetupError.NOT_FOUND)
            
            # CRITICAL: Filter to only ONLINE/AVAILABLE devices
            online_devices = []
            offline_devices = []
            
            for device in devices:
                device_id = device["device_id"]
                device_name = device["name"]
                device_state = device.get("state", "unknown")
                
                # Consider only ONLINE_RUNNING and ONLINE_STANDBY as "online"
                if device_state in ["ONLINE_RUNNING", "ONLINE_STANDBY"]:
                    online_devices.append(device)
                    _LOG.info(f"  ✅ ONLINE: {device_name} ({device_id}) - {device_state}")
                else:
                    offline_devices.append(device)
                    _LOG.warning(f"  ⚠️  OFFLINE: {device_name} ({device_id}) - {device_state}")
            
            # Warn about offline devices
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
            
            # Check if we have any online devices
            if not online_devices:
                _LOG.error("No ONLINE devices found - cannot proceed")
                _LOG.error("Please power on at least one Horizon box and try again")
                return SetupError(IntegrationSetupError.NOT_FOUND)
            
            # Clear existing device configuration
            self.config.devices = []
            
            # Add ONLY online devices to configuration with their device_id as key
            for device in online_devices:
                device_id = device["device_id"]
                device_name = device["name"]
                
                self.config.add_device(
                    device_id=device_id,
                    name=device_name,
                )
                _LOG.info(f"✅ Added online device: {device_name} (ID: {device_id})")
            
            # Save configuration
            if not self.config.save_config():
                _LOG.error("Failed to save configuration")
                return SetupError(IntegrationSetupError.OTHER)
            
            _LOG.info("=" * 70)
            _LOG.info(f"✅ Setup completed successfully")
            _LOG.info(f"📝 Saved {len(online_devices)} online device(s) to configuration")
            if offline_devices:
                _LOG.info(f"⚠️  Ignored {len(offline_devices)} offline device(s)")
            _LOG.info("=" * 70)
            
            # Disconnect test client
            await client.disconnect()
            
            return SetupComplete()
            
        except Exception as e:
            _LOG.error("Setup error: %s", e, exc_info=True)
            return SetupError(IntegrationSetupError.OTHER)

    async def _handle_user_data(self, msg: UserDataResponse) -> SetupAction:
        """
        Handle user data input.

        :param msg: User data response
        :return: Setup action
        """
        _LOG.info("Received user data: %s", msg.input_values.keys())
        
        # Process based on current step
        # (Future: can add multi-step setup flow here)
        
        return SetupComplete()

    async def _handle_abort(self, msg: AbortDriverSetup) -> SetupAction:
        """
        Handle setup abort.

        :param msg: Abort message
        :return: Setup action
        """
        _LOG.warning("Setup aborted: %s", msg.error)
        self._setup_step = "init"
        return SetupError(msg.error)