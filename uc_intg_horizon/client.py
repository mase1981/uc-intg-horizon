"""
Horizon API client for device communication.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging
import os
from typing import Any, Callable, Optional

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

COMMON_INPUTS = [
    {"id": "hdmi1", "name": "HDMI 1"},
    {"id": "hdmi2", "name": "HDMI 2"},
    {"id": "hdmi3", "name": "HDMI 3"},
    {"id": "hdmi4", "name": "HDMI 4"},
    {"id": "av", "name": "AV Input"},
]

COMMON_APPS = [
    {"id": "netflix", "name": "Netflix"},
    {"id": "iplayer", "name": "BBC iPlayer"},
    {"id": "itv", "name": "ITVX"},
    {"id": "all4", "name": "All 4"},
    {"id": "my5", "name": "My5"},
    {"id": "prime", "name": "Prime Video"},
    {"id": "youtube", "name": "YouTube"},
    {"id": "disney", "name": "Disney+"},
]


class HorizonClient:

    def __init__(self, provider: str, username: str, password: str):
        self.provider = provider
        self.username = username
        self.password = password
        self._api: Optional[LGHorizonApi] = None
        self._connected = False
        
        self.country_code = PROVIDER_TO_COUNTRY.get(provider, "nl")
        
        os.environ['SSL_CERT_FILE'] = certifi.where()
        os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
        
        _LOG.info(f"Horizon client initialized: provider={provider}, country_code={self.country_code}")
        _LOG.info(f"SSL certificate bundle: {certifi.where()}")

    async def connect(self, token_save_callback: Optional[Callable] = None) -> bool:
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
            
            await asyncio.to_thread(self._api.connect)
            
            if token_save_callback:
                _LOG.debug("ðŸ”„ Invoking token save callback immediately after API connection")
                try:
                    await token_save_callback(self._api)
                except Exception as e:
                    _LOG.error("Token save callback failed: %s", e, exc_info=True)
                    _LOG.warning("Continuing despite callback failure - fallback saves will handle it")
            
            await self._wait_for_mqtt_ready()
            
            self._connected = True
            device_count = len(self._api.settop_boxes)
            _LOG.info("Connected to Horizon API successfully. Devices found: %d", device_count)
            
            if hasattr(self._api, 'refresh_token') and self._api.refresh_token:
                _LOG.debug("Current refresh token: %s...", self._api.refresh_token[:20])
            
            return True
            
        except Exception as e:
            _LOG.error("Failed to connect to Horizon API: %s", e, exc_info=True)
            self._connected = False
            return False


    async def _wait_for_mqtt_ready(self, timeout: int = 15, check_interval: float = 0.5):
        if not self._api:
            return
        
        elapsed = 0
        _LOG.debug("Waiting for devices to register on MQTT...")
        
        while elapsed < timeout:
            if hasattr(self._api, 'settop_boxes') and len(self._api.settop_boxes) > 0:
                total_devices = len(self._api.settop_boxes)
                ready_devices = 0
                online_devices = 0
                offline_devices = 0
                pending_devices = []
                
                for device_id, box in self._api.settop_boxes.items():
                    if hasattr(box, 'state') and box.state is not None:
                        ready_devices += 1
                        if box.state == 'OFFLINE':
                            offline_devices += 1
                            _LOG.debug(f"Device {device_id} is OFFLINE")
                        else:
                            online_devices += 1
                            _LOG.debug(f"Device {device_id} is {box.state}")
                    else:
                        pending_devices.append(device_id)
                        _LOG.debug(f"Device {device_id} not ready yet (no state)")
                
                if ready_devices > 0:
                    _LOG.info(
                        f"âœ“ MQTT ready: {ready_devices}/{total_devices} devices reported state "
                        f"({online_devices} online, {offline_devices} offline)"
                    )
                    if pending_devices:
                        _LOG.info(f"Proceeding with {len(pending_devices)} devices still pending: {pending_devices}")
                    return
            
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            if int(elapsed) % 5 == 0:
                device_count = len(self._api.settop_boxes) if hasattr(self._api, 'settop_boxes') else 0
                _LOG.debug(f"Still waiting for MQTT ready... ({elapsed:.1f}s elapsed, {device_count} devices found)")
        
        device_count = len(self._api.settop_boxes) if hasattr(self._api, 'settop_boxes') else 0
        if device_count > 0:
            ready_count = sum(
                1 for box in self._api.settop_boxes.values() 
                if hasattr(box, 'state') and box.state is not None
            )
            _LOG.warning(
                f"MQTT ready timeout after {timeout}s with {ready_count}/{device_count} "
                f"devices ready - proceeding anyway (some devices may be offline/slow)"
            )
        else:
            _LOG.error(f"âœ— MQTT ready timeout after {timeout}s with NO devices found")
            raise TimeoutError(f"MQTT connection not ready after {timeout}s - no devices discovered")

    async def disconnect(self) -> None:
        try:
            if self._api:
                await asyncio.to_thread(self._api.disconnect)
            self._connected = False
            _LOG.info("Disconnected from Horizon API")
        except Exception as e:
            _LOG.error("Error during disconnect: %s", e)

    async def get_devices(self) -> list[dict[str, Any]]:
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
        if not self._api:
            return None
            
        return self._api.settop_boxes.get(device_id)

    async def get_sources(self, device_id: str) -> list[dict[str, str]]:
        sources = []
        
        sources.extend(COMMON_INPUTS)
        
        sources.extend(COMMON_APPS)
        
        _LOG.info(f"Returning {len(sources)} sources for {device_id}")
        return sources

    async def send_key(self, device_id: str, key: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                _LOG.warning(f"Device not found: {device_id}")
                return False
            
            _LOG.info(f"Sending key: {key} to {device_id}")
            await asyncio.to_thread(box.send_key_to_box, key)
            _LOG.debug("Sent key to %s: %s", device_id, key)
            return True
            
        except Exception as e:
            _LOG.error("Failed to send key %s to %s: %s", key, device_id, e)
            return False

    async def set_channel(self, device_id: str, channel_number: str) -> bool:
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
                await asyncio.to_thread(box.send_key_to_box, digit)
                await asyncio.sleep(0.3)
            
            await asyncio.sleep(0.5)
            await asyncio.to_thread(box.send_key_to_box, "Ok")
            
            _LOG.info(f"Successfully set channel to {channel_str} on {device_id}")
            return True
            
        except Exception as e:
            _LOG.error("Failed to set channel %s on %s: %s", channel_number, device_id, e)
            return False

    async def power_on(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Powering on device: {device_id}")
            await asyncio.to_thread(box.turn_on)
            _LOG.info("Powered on device: %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to power on %s: %s", device_id, e)
            return False

    async def power_off(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Powering off device: {device_id}")
            await asyncio.to_thread(box.turn_off)
            _LOG.info("Powered off device (standby): %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to power off %s: %s", device_id, e)
            return False

    async def power_toggle(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Toggling power on device: {device_id}")
            await asyncio.to_thread(box.send_key_to_box, "Power")
            _LOG.info("Toggled power on device: %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to toggle power %s: %s", device_id, e)
            return False

    async def play(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Playing on device: {device_id}")
            await asyncio.to_thread(box.play)
            _LOG.debug("Play command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to play on %s: %s", device_id, e)
            return False

    async def pause(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Pausing on device: {device_id}")
            await asyncio.to_thread(box.pause)
            _LOG.debug("Pause command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to pause on %s: %s", device_id, e)
            return False

    async def play_pause_toggle(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Toggling play/pause on device: {device_id}")
            await asyncio.to_thread(box.send_key_to_box, "MediaPlayPause")
            _LOG.debug("Play/Pause toggle sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to toggle play/pause on %s: %s", device_id, e)
            return False

    async def stop(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Stopping on device: {device_id}")
            await asyncio.to_thread(box.stop)
            _LOG.debug("Stop command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to stop on %s: %s", device_id, e)
            return False

    async def fast_forward(self, device_id: str) -> bool:
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
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.send_key_to_box, "ChannelUp")
            _LOG.debug("Channel up command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to go to next channel on %s: %s", device_id, e)
            return False

    async def previous_channel(self, device_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            await asyncio.to_thread(box.send_key_to_box, "ChannelDown")
            _LOG.debug("Channel down command sent to %s", device_id)
            return True
        except Exception as e:
            _LOG.error("Failed to go to previous channel on %s: %s", device_id, e)
            return False

    async def play_media(self, device_id: str, media_type: str, media_id: str) -> bool:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return False
            
            _LOG.info(f"Playing media: type={media_type}, id={media_id} on {device_id}")
            
            if media_type == "app":
                _LOG.warning(f"Direct app launch not supported yet - opening home menu for {media_id}")
                _LOG.info("User must manually select app from menu")
                await asyncio.to_thread(box.send_key_to_box, "MediaTopMenu")
                _LOG.info(f"Opened home menu for app selection: {media_id}")
                return True
            else:
                _LOG.warning(f"Unsupported media type: {media_type}")
                return False
                
        except Exception as e:
            _LOG.error("Failed to play media on %s: %s", device_id, e)
            return False

    async def get_device_state(self, device_id: str) -> dict[str, Any]:
        try:
            box = await self.get_device_by_id(device_id)
            if not box:
                return {"state": "unavailable"}
            
            state = {
                "state": box.state,
                "channel": None,
                "media_title": None,
                "media_image": None,
                "start_time": None,
                "end_time": None,
                "position": None,
            }
            
            if hasattr(box, "playing_info") and box.playing_info:
                playing_info = box.playing_info
                state["channel"] = getattr(playing_info, "channel_title", None)
                state["media_title"] = getattr(playing_info, "title", None)
                state["media_image"] = getattr(playing_info, "image", None)
                state["start_time"] = getattr(playing_info, "startTime", None) or getattr(playing_info, "start_time", None)
                state["end_time"] = getattr(playing_info, "endTime", None) or getattr(playing_info, "end_time", None)
                state["position"] = getattr(playing_info, "position", None)
            
            return state
            
        except Exception as e:
            _LOG.error("Failed to get state for %s: %s", device_id, e)
            return {"state": "unavailable"}

    @property
    def is_connected(self) -> bool:
        return self._connected