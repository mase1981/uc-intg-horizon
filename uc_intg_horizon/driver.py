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
        _LOG.debug("Token save skipped - client or config not initialized")
        return
    
    try:
        current_token = getattr(_client._api, 'refresh_token', None)
        
        if not current_token:
            _LOG.debug("No refresh token available from API")
            return
        
        stored_token = _config.password
        
        _LOG.debug("Token comparison - Stored: %s..., Current: %s...", 
                  stored_token[:20] if stored_token else "None",
                  current_token[:20])
        
        if current_token != stored_token:
            _LOG.warning("🔄 Token was refreshed during connection - updating storage")
            _LOG.info("Old token: %s...", stored_token[:20] if stored_token else "None")
            _LOG.info("New token: %s...", current_token[:20])
            
            _config.password = current_token
            
            if _config.save_config():
                _LOG.info("✅ Refreshed token saved successfully to disk")
            else:
                _LOG.error("❌ CRITICAL: Failed to save refreshed token to disk!")
                _LOG.error("This will cause 'Invalid token' errors after next reboot!")
        else:
            _LOG.debug("✅ Token unchanged, no save needed")
            
    except Exception as e:
        _LOG.error("❌ Error checking/saving refreshed token: %s", e, exc_info=True)
        _LOG.error("This may cause authentication failures after reboot!")


async def _initialize_integration():
    global _config, _client, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready and _client and _client.is_connected:
            _LOG.info("✅ Entities already initialized and client connected")
            _LOG.debug("Updating entity states without recreating entities...")
            
            for mp in _media_players.values():
                await mp.push_update()
            for remote in _remotes.values():
                await remote.push_update()
            
            _LOG.debug("Entity state update complete, continuing to connection phase...")
            return True
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return False
            
        _LOG.info("=== Starting Entity Initialization (Persistence Pattern) ===")
        
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
                
                _LOG.debug("Pre-connection token: %s...", 
                          _config.password[:20] if _config.password else "None")
                
                if not await _client.connect():
                    _LOG.error("❌ Failed to connect to Horizon API")
                    return False
                
                _LOG.info("✅ Connected to Horizon API")
            else:
                _LOG.info("✅ Already connected to Horizon API")
            
            _LOG.info("Waiting additional 2 seconds for MQTT stability...")
            await asyncio.sleep(2)
            
            if not _entities_ready:
                _LOG.info("Creating entities for %d devices...", len(_config.devices))
                api.available_entities.clear()
                _media_players.clear()
                _remotes.clear()
                
                for device in _config.devices:
                    device_id = device["device_id"]
                    device_name = device["name"]
                    
                    _LOG.info("  Creating entities for: %s (%s)", device_name, device_id)
                    
                    media_player = HorizonMediaPlayer(
                        device_id=device_id,
                        device_name=device_name,
                        client=_client,
                        api=api,
                    )
                    _media_players[device_id] = media_player
                    api.available_entities.add(media_player)
                    
                    remote = HorizonRemote(
                        device_id=device_id,
                        device_name=device_name,
                        client=_client,
                        api=api,
                    )
                    _remotes[device_id] = remote
                    api.available_entities.add(remote)
                
                _entities_ready = True
                
                _LOG.info("✅ Entities ready: %d media players, %d remotes",
                         len(_media_players), len(_remotes))
            
            _LOG.info("=== Entity Initialization Complete ===")
            
            return True
            
        except Exception as e:
            _LOG.error("❌ Failed to initialize entities: %s", e, exc_info=True)
            _entities_ready = False
            return False


async def on_connect() -> None:
    global _config, _entities_ready, _client
    
    _LOG.info("=== UC Remote CONNECT Event ===")
    
    if not _config:
        _config = HorizonConfig()
    
    _config.reload_from_disk()
    
    _LOG.debug("Loaded config - Provider: %s, Username: %s, Token: %s...",
              _config.provider,
              _config.username,
              _config.password[:20] if _config.password else "None")
    
    if not _config.is_configured():
        _LOG.info("Integration not configured - awaiting setup")
        await api.set_device_state(DeviceStates.DISCONNECTED)
        return
    
    success = await _initialize_integration()
    
    if not success:
        _LOG.error("❌ Entity initialization failed")
        await api.set_device_state(DeviceStates.ERROR)
        return
    
    if _client and _client.is_connected:
        _LOG.info("💾 Checking if token needs to be saved after connection...")
        await _save_refreshed_token()
    else:
        _LOG.warning("⚠️ Client not connected, cannot check token state")
    
    _LOG.info("✅ Setting device state to CONNECTED")
    await api.set_device_state(DeviceStates.CONNECTED)


async def on_disconnect() -> None:
    _LOG.info("=== UC Remote DISCONNECT Event ===")
    _LOG.info("Preserving entities and connection for reconnection")


async def on_subscribe_entities(entity_ids: list[str]):
    _LOG.info("=== Entity Subscription Request ===")
    _LOG.info("Requested entity IDs: %s", entity_ids)
    
    if not _entities_ready:
        _LOG.error("⚠️ RACE CONDITION DETECTED: Subscription before entities ready!")
        _LOG.info("Attempting emergency initialization...")
        
        if _config and _config.is_configured():
            success = await _initialize_integration()
            if not success:
                _LOG.error("❌ Emergency initialization failed")
                return
        else:
            _LOG.error("❌ Cannot initialize - no configuration available")
            return
    
    available_ids = []
    for mp in _media_players.values():
        available_ids.append(mp.id)
    for remote in _remotes.values():
        available_ids.append(remote.id)
    
    _LOG.info("Available entity IDs: %s", available_ids)
    
    for entity_id in entity_ids:
        for device_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                await media_player.push_update()
                _LOG.info("✅ Subscribed to media player: %s", entity_id)
                break
        
        for device_id, remote in _remotes.items():
            if entity_id == remote.id:
                await remote.push_update()
                _LOG.info("✅ Subscribed to remote: %s", entity_id)
                break


async def setup_handler(msg: SetupAction) -> SetupAction:
    global _setup_manager
    
    if not _setup_manager:
        _setup_manager = SetupManager(_config)
    
    action = await _setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("=== Setup Complete - Initializing Integration ===")
        await _initialize_integration()
        
        if _client and _client.is_connected:
            _LOG.info("💾 Saving token after initial setup...")
            await _save_refreshed_token()
    
    return action


async def main():
    global api, _config
    
    try:
        loop = asyncio.get_running_loop()
        api = ucapi.IntegrationAPI(loop)
        
        _config = HorizonConfig()
        
        if _config.is_configured():
            _LOG.info("=== Pre-initialization for Reboot Survival ===")
            _LOG.info("Configuration found - initializing entities BEFORE UC Remote connects")
            
            _LOG.debug("Initial token: %s...", 
                      _config.password[:20] if _config.password else "None")
            
            await _initialize_integration()
            
            if _client and _client.is_connected:
                _LOG.info("💾 Saving token after pre-initialization...")
                await _save_refreshed_token()
            
            _LOG.info("✅ Pre-initialization complete, entities ready for UC Remote")
        
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        
        await api.init("driver.json", setup_handler)
        await api.set_device_state(DeviceStates.DISCONNECTED)
        
        _LOG.info("=== Horizon Integration Driver Started ===")
        
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