"""
Main integration driver for Horizon with reboot survival.

:copyright: (c) 2025 by Meir Miyara
:license: MPL-2.0, see LICENSE for more details.
"""

import asyncio
import logging

import ucapi
from ucapi.api_definitions import DeviceStates, Events, SetupAction, SetupComplete

from uc_intg_horizon.client import HorizonClient
from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.media_player import HorizonMediaPlayer
from uc_intg_horizon.remote import HorizonRemote
from uc_intg_horizon.setup_manager import SetupManager

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)-40s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_LOG = logging.getLogger(__name__)

api: ucapi.IntegrationAPI | None = None
_config: HorizonConfig | None = None
_client: HorizonClient | None = None
_setup_manager: SetupManager | None = None
_media_players: dict[str, HorizonMediaPlayer] = {}
_remotes: dict[str, HorizonRemote] = {}
_entities_ready: bool = False
_initialization_lock: asyncio.Lock = asyncio.Lock()


async def _save_refreshed_token():
    global _config, _client
    
    if not _client or not _config:
        return
    
    try:
        current_token = getattr(_client._api, 'refresh_token', None)
        
        if current_token and current_token != _config.password:
            _LOG.info("Token was refreshed during connection, updating storage")
            _LOG.info("Old token: %s...", _config.password[:20] if _config.password else "None")
            _LOG.info("New token: %s...", current_token[:20])
            
            _config.password = current_token
            
            if _config.save_config():
                _LOG.info("Refreshed token saved successfully")
            else:
                _LOG.error("Failed to save refreshed token!")
        else:
            _LOG.debug("Token unchanged, no save needed")
            
    except Exception as e:
        _LOG.error("Error checking/saving refreshed token: %s", e, exc_info=True)


async def _initialize_integration():
    global _config, _client, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready and _client and _client.is_connected:
            _LOG.debug("Entities already initialized and connected")
            # Update entity states
            for mp in _media_players.values():
                await mp.push_update()
            for remote in _remotes.values():
                await remote.push_update()
            return True
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return False
            
        _LOG.info("=" * 70)
        _LOG.info("=== Starting Entity Initialization (ID Matching Pattern) ===")
        _LOG.info("=" * 70)
        
        try:
            if not _client:
                _LOG.info("Creating Horizon API client")
                _client = HorizonClient(
                    provider=_config.provider,
                    username=_config.username,
                    password=_config.password,
                )
            
            if not _client.is_connected:
                _LOG.info("Connecting to Horizon API (with MQTT wait)...")
                if not await _client.connect():
                    _LOG.error("Failed to connect to Horizon API")
                    return False
                    
                await _save_refreshed_token()
                
                _LOG.info("Connected to Horizon API")
            else:
                _LOG.info("Already connected to Horizon API")
            
            _LOG.info("Querying Horizon API for current device states...")
            api_devices = await _client.get_devices()
            
            online_device_map = {}
            for device in api_devices:
                device_id = device["device_id"]
                device_state = device.get("state", "unknown")
                
                if device_state in ["ONLINE_RUNNING", "ONLINE_STANDBY"]:
                    online_device_map[device_id] = device
                    _LOG.info(f"API reports ONLINE: {device['name']} (ID: {device_id}) - {device_state}")
                else:
                    _LOG.warning(f"API reports OFFLINE: {device['name']} (ID: {device_id}) - {device_state}")
            
            _LOG.info(f"API Status: {len(online_device_map)}/{len(api_devices)} devices are online")
            
            _LOG.info(f"Matching {len(_config.devices)} configured device(s) with online devices...")
            
            devices_to_create = []
            devices_skipped = []
            
            for config_device in _config.devices:
                device_id = config_device["device_id"]
                device_name = config_device["name"]
                
                if device_id in online_device_map:
                    devices_to_create.append({
                        "device_id": device_id,
                        "name": device_name,
                        "state": online_device_map[device_id]["state"]
                    })
                    _LOG.info(f"  âœ… MATCH: {device_name} (ID: {device_id}) - Will create entities")
                else:
                    devices_skipped.append({
                        "device_id": device_id,
                        "name": device_name
                    })
                    _LOG.warning(f"NO MATCH: {device_name} (ID: {device_id}) - Device offline or not found")
            
            if devices_skipped:
                _LOG.warning("=" * 70)
                _LOG.warning(f"{len(devices_skipped)} configured device(s) are currently OFFLINE:")
                for d in devices_skipped:
                    _LOG.warning(f"   - {d['name']} (ID: {d['device_id']})")
                _LOG.warning("These devices will NOT have entities created until they come online")
                _LOG.warning("To add them: Power on the box and reconfigure the integration")
                _LOG.warning("=" * 70)
            
            if not devices_to_create:
                _LOG.error("No online devices to create entities for!")
                _LOG.error("All configured devices are currently offline")
                return False
            
            # Step 5: Additional delay to ensure MQTT is fully stable
            _LOG.info("Waiting additional 2 seconds for MQTT stability...")
            await asyncio.sleep(2)
            
            # Step 6: Clear and recreate entities ONLY for matched online devices
            _LOG.info(f"Creating entities for {len(devices_to_create)} matched online device(s)...")
            api.available_entities.clear()
            _media_players.clear()
            _remotes.clear()
            
            for device in devices_to_create:
                device_id = device["device_id"]
                device_name = device["name"]
                device_state = device["state"]
                
                _LOG.info(f"  Creating entities for: {device_name} (ID: {device_id}, State: {device_state})")
                
                media_player = HorizonMediaPlayer(
                    device_id=device_id,
                    device_name=device_name,
                    client=_client,
                    api=api,
                )
                _media_players[device_id] = media_player
                api.available_entities.add(media_player)
                _LOG.info(f"Created Media Player: {media_player.id}")
                
                remote = HorizonRemote(
                    device_id=device_id,
                    device_name=device_name,
                    client=_client,
                    api=api,
                    media_player=media_player,
                )
                _remotes[device_id] = remote
                api.available_entities.add(remote)
                _LOG.info(f"    âœ… Created Remote: {remote.id}")
            
            _entities_ready = True
            
            _LOG.info("=" * 70)
            _LOG.info("Entity initialization complete!")
            _LOG.info(f"Summary:")
            _LOG.info(f"   - Media Players created: {len(_media_players)}")
            _LOG.info(f"   - Remotes created: {len(_remotes)}")
            _LOG.info(f"   - Devices skipped (offline): {len(devices_skipped)}")
            _LOG.info("=" * 70)
            
            return True
            
        except Exception as e:
            _LOG.error("Failed to initialize entities: %s", e, exc_info=True)
            _entities_ready = False
            return False


async def on_connect() -> None:
    global _config, _entities_ready
    
    _LOG.info("=" * 70)
    _LOG.info("=== UC Remote CONNECT Event ===")
    _LOG.info("=" * 70)
    
    if not _config:
        _config = HorizonConfig()
    
    _config.reload_from_disk()
    
    if not _config.is_configured():
        _LOG.info("Integration not configured - awaiting setup")
        await api.set_device_state(DeviceStates.DISCONNECTED)
        return
    
    _LOG.info(f"Configuration loaded: {len(_config.devices)} device(s) in config")
    for device in _config.devices:
        _LOG.info(f"  - {device['name']} (ID: {device['device_id']})")
    
    success = await _initialize_integration()
    
    if not success:
        _LOG.error("Entity initialization failed")
        await api.set_device_state(DeviceStates.ERROR)
        return
    
    _LOG.info("Setting device state to CONNECTED")
    await api.set_device_state(DeviceStates.CONNECTED)


async def on_disconnect() -> None:
    _LOG.info("=" * 70)
    _LOG.info("=== UC Remote DISCONNECT Event ===")
    _LOG.info("Preserving entities and connection for reconnection")
    _LOG.info("=" * 70)


async def on_subscribe_entities(entity_ids: list[str]):
    _LOG.info("=" * 70)
    _LOG.info("=== Entity Subscription Request ===")
    _LOG.info(f"Requested entity IDs: {entity_ids}")
    
    # Race condition protection
    if not _entities_ready:
        _LOG.error("RACE CONDITION DETECTED: Subscription before entities ready!")
        _LOG.info("Attempting emergency initialization...")
        
        if _config and _config.is_configured():
            success = await _initialize_integration()
            if not success:
                _LOG.error("Emergency initialization failed")
                return
        else:
            _LOG.error("Cannot initialize - no configuration available")
            return
    
    available_ids = []
    for device_id, mp in _media_players.items():
        available_ids.append(mp.id)
    for device_id, remote in _remotes.items():
        available_ids.append(remote.id)
    
    _LOG.info(f"Available entity IDs: {available_ids}")
    
    for entity_id in entity_ids:
        matched = False
        
        for device_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                await media_player.push_update()
                _LOG.info(f"âœ… Subscribed to media player: {entity_id} (Device ID: {device_id})")
                matched = True
                break
        
        if not matched:
            for device_id, remote in _remotes.items():
                if entity_id == remote.id:
                    await remote.push_update()
                    _LOG.info(f"Subscribed to remote: {entity_id} (Device ID: {device_id})")
                    matched = True
                    break
        
        if not matched:
            _LOG.warning("Entity not found: {entity_id}")
    
    _LOG.info("=" * 70)


async def setup_handler(msg: SetupAction) -> SetupAction:
    global _setup_manager
    
    if not _setup_manager:
        _setup_manager = SetupManager(_config)
    
    action = await _setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("=" * 70)
        _LOG.info("=== Setup Complete - Initializing Integration ===")
        _LOG.info("=" * 70)
        await _initialize_integration()
    
    return action


async def main():
    global api, _config
    
    try:
        loop = asyncio.get_running_loop()
        api = ucapi.IntegrationAPI(loop)
        
        _config = HorizonConfig()
        
        if _config.is_configured():
            _LOG.info("=" * 70)
            _LOG.info("=== Pre-initialization for Reboot Survival ===")
            _LOG.info("Configuration found - initializing entities BEFORE UC Remote connects")
            _LOG.info("=" * 70)
            
            await _initialize_integration()
            
            _LOG.info("=" * 70)
            _LOG.info("âœ… Pre-initialization complete, entities ready for UC Remote")
            _LOG.info("=" * 70)
        
        # Register event handlers
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        
        await api.init("driver.json", setup_handler)
        await api.set_device_state(DeviceStates.DISCONNECTED)
        
        _LOG.info("=" * 70)
        _LOG.info("=== Horizon Integration Driver Started ===")
        _LOG.info("=" * 70)
        
        await asyncio.Future()
        
    except asyncio.CancelledError:
        _LOG.info("Driver task cancelled")
    except Exception as e:
        _LOG.error("Fatal error in main: %s", e, exc_info=True)
        raise
    finally:
        if _client:
            await _client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOG.info("Integration stopped by user")
    except Exception as e:
        _LOG.error("Fatal error: %s", e, exc_info=True)
        raise