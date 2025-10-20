"""
Horizon API client for device communication.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os
from typing import Any, Optional

import certifi
from lghorizon import LGHorizonApi, LGHorizonBox

_LOG = logging.getLogger(__name__)

PROVIDER_TO_COUNTRY = {
    "Ziggo": "nl",
    "VirginMedia": "gb",
    "Telenet": "be",
    "UPC": "ch",
    "Sunrise": "ch",
    "Magenta": "at",
}


class HorizonClient:
    """Client for communicating with Horizon set-top boxes via lghorizon library."""

    def __init__(self, provider: str, username: str, password: str):
        """
        Initialize Horizon client.

        :param provider: Provider name (Ziggo, VirginMedia, etc.)
        :param username: Account username/email
        :param password: Account password or refresh token
        """
        self.provider = provider
        self.username = username
        self.password = password
        self._api: Optional[LGHorizonApi] = None
        self._connected = False
        
        self.country_code = PROVIDER_TO_COUNTRY.get(provider, "nl")
        
        # Set SSL certificate path
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        
        _LOG.info(f"Horizon client initialized: provider={provider}, country_code={self.country_code}")
        _LOG.info(f"SSL certificate bundle: {certifi.where()}")

    async def connect(self) -> bool:
        """
        Connect to Horizon API and authenticate.
        
        CRITICAL: This includes waiting for MQTT connection to be fully established.

        :return: True if connection successful, False otherwise
        """
        try:
            _LOG.info("Connecting to Horizon API: provider=%s, username=%s", 
                     self.provider, self.username)
            
            country = self.country_code[0:2]
            if country in ("gb", "ch", "be"):
                _LOG.info("Using refresh token authentication for %s", country.upper())
                self._api = LGHorizonApi(
                    username=self.username,
                    password="",
                    country_code=self.country_code,
                    refresh_token=self.password,
                )
            else:
                self._api = LGHorizonApi(
                    username=self.username,
                    password=self.password,
                    country_code=self.country_code,
                )
            
            # Connect to API (this starts MQTT connection in background)
            _LOG.info("Connecting to Horizon API and MQTT broker...")
            await asyncio.to_thread(self._api.connect)
            
            # CRITICAL: Wait for MQTT connection and device registration to complete
            # This is what the Home Assistant PRs fixed!
            _LOG.info("Waiting for MQTT connection and device registration...")
            await self._wait_for_mqtt_ready()
            
            self._connected = True
            device_count = len(self._api.settop_boxes)
            _LOG.info("✓ Connected to Horizon API successfully. Devices found: %d", device_count)
            
            # Log token info for debugging
            if hasattr(self._api, 'refresh_token') and self._api.refresh_token:
                _LOG.debug("Current refresh token: %s...", self._api.refresh_token[:20])
            
            return True
            
        except Exception as e:
            _LOG.error("Failed to connect to Horizon API: %s", e, exc_info=True)
            self._connected = False
            return False

    async def _wait_for_mqtt_ready(self, timeout: int = 30, check_interval: float = 0.5):
        """
        Wait for MQTT connection to be established and devices to be registered.
        
        Based on Home Assistant PR #137 - this is critical for reboot survival.
        
        :param timeout: Maximum time to wait in seconds
        :param check_interval: Time between checks in seconds
        """
        if not self._api:
            return
        
        elapsed = 0
        max_wait = timeout
        
        _LOG.debug("Waiting for devices to register on MQTT...")
        
        while elapsed < max_wait:
            # Check if we have devices and they're registered
            if hasattr(self._api, 'settop_boxes') and len(self._api.settop_boxes) > 0:
                # Check if devices are actually usable (not just discovered)
                all_ready = True
                for device_id, box in self._api.settop_boxes.items():
                    # Check if device has a valid state (indicates MQTT is working)
                    if not hasattr(box, 'state') or box.state is None:
                        all_ready = False
                        _LOG.debug(f"Device {device_id} not ready yet (no state)")
                        break
                
                if all_ready:
                    _LOG.info(f"✓ All {len(self._api.settop_boxes)} devices registered and ready")
                    return
            
            # Wait a bit before checking again
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # Log progress every 5 seconds
            if int(elapsed) % 5 == 0:
                device_count = len(self._api.settop_boxes) if hasattr(self._api, 'settop_boxes') else 0
                _LOG.debug(f"Still waiting for MQTT ready... ({elapsed}s elapsed, {device_count} devices found)")
        
        # Timeout reached
        device_count = len(self._api.settop_boxes) if hasattr(self._api, 'settop_boxes') else 0
        if device_count > 0:
            _LOG.warning(f"MQTT ready timeout after {timeout}s, but found {device_count} devices - proceeding anyway")
        else:
            _LOG.error(f"MQTT ready timeout after {timeout}s with no devices found")
            raise TimeoutError(f"MQTT connection not ready after {timeout}s")

    async def disconnect(self) -> None:
        """Disconnect from Horizon API."""
        try:
            if self._api:
                await asyncio.to_thread(self._api.disconnect)
            self._connected = False
            _LOG.info("Disconnected from Horizon API")
        except Exception as e:
            _LOG.error("Error during disconnect: %s", e)

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get list of devices from Horizon account."""
        if not self._connected or not self._api:
            _LOG.warning("Not connected to Horizon API")
            return []
        
        devices = []
        box: LGHorizonBox
        for device_id, box in self._api.settop_boxes.items():
            try:
                device_name = getattr(box, "device_friendly_name", device_id)
                
                devices.append({
                    "device_id": device_id,
                    "name": device_name,
                    "model": getattr(box, "model", "Unknown"),
                    "state": box.state,
                    "manufacturer": getattr(box, "manufacturer", "LG"),
                })
            except Exception as e:
                _LOG.error("Error processing device: %s", e)
        
        return devices

    async def get_device_by_id(self, device_id: str) -> Optional[LGHorizonBox]:
        """Get device object by ID."""
        if not self._api:
            return None
            
        return self._api.settop_boxes.get(device_id)

    async def send_key(self, device_id: str, key: str) -> bool:
        """Send key press to device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                _LOG.warning(f"Device not found: {device_id}")
                return False
            
            await asyncio.to_thread(box.send_key_to_box, key)
            _LOG.debug("Sent key to %s: %s", device_id, key)
            return True
            
        except Exception as e:
            _LOG.error("Failed to send key %s to %s: %s", key, device_id, e)
            return False

    async def set_channel(self, device_id: str, channel_number: str) -> bool:
        """Set channel on device using digit key sequence."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                _LOG.warning(f"Device not found: {device_id}")
                return False
            
            channel_str = str(channel_number).strip()
            
            if not channel_str.isdigit():
                _LOG.error(f"Invalid channel number: {channel_number}")
                return False
            
            _LOG.info(f"Setting channel to {channel_str} on {device_id}")
            
            for digit in channel_str:
                await asyncio.to_thread(box.send_key_to_box, f"Digit{digit}")
                await asyncio.sleep(0.3)
            
            await asyncio.sleep(0.5)
            await asyncio.to_thread(box.send_key_to_box, "Select")
            
            _LOG.info(f"Successfully set channel to {channel_str} on {device_id}")
            return True
            
        except Exception as e:
            _LOG.error("Failed to set channel %s on %s: %s", channel_number, device_id, e)
            return False

    async def power_on(self, device_id: str) -> bool:
        """Power on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.turn_on)
            _LOG.info("Powered on device: %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to power on %s: %s", device_id, e)
            return False

    async def power_off(self, device_id: str) -> bool:
        """Power off device (standby mode)."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.turn_off)
            _LOG.info("Powered off device (standby): %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to power off %s: %s", device_id, e)
            return False

    async def play(self, device_id: str) -> bool:
        """Play on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.play)
            _LOG.debug("Play command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to play on %s: %s", device_id, e)
            return False

    async def pause(self, device_id: str) -> bool:
        """Pause on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.pause)
            _LOG.debug("Pause command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to pause on %s: %s", device_id, e)
            return False

    async def stop(self, device_id: str) -> bool:
        """Stop on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.stop)
            _LOG.debug("Stop command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to stop on %s: %s", device_id, e)
            return False

    async def fast_forward(self, device_id: str) -> bool:
        """Fast forward on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.fast_forward)
            _LOG.debug("Fast forward command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to fast forward on %s: %s", device_id, e)
            return False

    async def rewind(self, device_id: str) -> bool:
        """Rewind on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.rewind)
            _LOG.debug("Rewind command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to rewind on %s: %s", device_id, e)
            return False

    async def record(self, device_id: str) -> bool:
        """Start recording on device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.record)
            _LOG.debug("Record command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to record on %s: %s", device_id, e)
            return False

    async def next_channel(self, device_id: str) -> bool:
        """Go to next channel."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.next_channel)
            _LOG.debug("Next channel command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to go to next channel on %s: %s", device_id, e)
            return False

    async def previous_channel(self, device_id: str) -> bool:
        """Go to previous channel."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.previous_channel)
            _LOG.debug("Previous channel command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to go to previous channel on %s: %s", device_id, e)
            return False

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        """Get current state of device."""
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return {"state": "unavailable"}
            
            state = {
                "state": box.state,
                "channel": None,
                "media_title": None,
                "media_image": None,
            }
            
            if hasattr(box, "playing_info") and box.playing_info:
                playing_info = box.playing_info
                state["channel"] = getattr(playing_info, "channel_title", None)
                state["media_title"] = getattr(playing_info, "title", None)
                state["media_image"] = getattr(playing_info, "image", None)
            
            return state
            
        except Exception as e:
            _LOG.error("Failed to get state for %s: %s", device_id, e)
            return {"state": "unavailable"}

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected