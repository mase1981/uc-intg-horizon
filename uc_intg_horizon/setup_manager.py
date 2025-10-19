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
            
            # Get devices
            devices = await client.get_devices()
            _LOG.info("Found %d devices", len(devices))
            
            if not devices:
                _LOG.warning("No devices found in account")
                return SetupError(IntegrationSetupError.NOT_FOUND)
            
            # Add devices to configuration
            for device in devices:
                self.config.add_device(
                    device_id=device["device_id"],
                    name=device["name"],
                )
            
            # Save configuration
            self.config.save_config()
            
            # Disconnect test client
            await client.disconnect()
            
            _LOG.info("Setup completed successfully")
            return SetupComplete()
            
        except Exception as e:
            _LOG.error("Setup error: %s", e)
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