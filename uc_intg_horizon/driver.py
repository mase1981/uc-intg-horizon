"""
Main integration driver for Horizon.

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


def _on_token_update(new_token: str) -> None:
    global _config
    
    if _config:
        _LOG.info("Updating stored refresh token")
        _config.password = new_token
        _config.save_config()


async def _initialize_integration():
    global _config, _client, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready:
            _LOG.debug("Entities already initialized")
            return True
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return False
            
        _LOG.info("=== Starting Entity Initialization (Persistence Pattern) ===")
        
        try:
            # Step 1: Ensure Horizon API client exists and is connected
            if not _client:
                _LOG.info("Creating Horizon API client")
                _client = HorizonClient(
                    provider=_config.provider,
                    username=_config.username,
                    password=_config.password,
                    token_update_callback=_on_token_update,
                )
            
            # Step 2: Connect to Horizon API (or reconnect if needed)
            if not _client.is_connected:
                _LOG.info("Connecting to Horizon API...")
                if not await _client.connect():
                    _LOG.error("Failed to connect to Horizon API")
                    return False
                _LOG.info("âœ" Connected to Horizon API")
            else:
                _LOG.info("âœ" Already connected to Horizon API")
            
            # Step 3: Clear and recreate all entities atomically
            _LOG.info("Creating entities for %d devices...", len(_config.devices))
            api.available_entities.clear()
            _media_players.clear()
            _remotes.clear()
            
            for device in _config.devices:
                device_id = device["device_id"]
                device_name = device["name"]
                
                _LOG.info("  Creating entities for: %s (%s)", device_name, device_id)
                
                # Create Media Player
                media_player = HorizonMediaPlayer(
                    device_id=device_id,
                    device_name=device_name,
                    client=_client,
                    api=api,
                )
                _media_players[device_id] = media_player
                api.available_entities.add(media_player)
                
                # Create Remote
                remote = HorizonRemote(
                    device_id=device_id,
                    device_name=device_name,
                    client=_client,
                    api=api,
                )
                _remotes[device_id] = remote
                api.available_entities.add(remote)
            
            # Step 4: Mark entities ready BEFORE setting CONNECTED
            # This is CRITICAL per the persistence guide
            _entities_ready = True
            
            _LOG.info("âœ" Entities ready: %d media players, %d remotes",
                     len(_media_players), len(_remotes))
            _LOG.info("=== Entity Initialization Complete ===")
            
            return True
            
        except Exception as e:
            _LOG.error("Failed to initialize entities: %s", e, exc_info=True)
            _entities_ready = False
            return False


async def on_connect() -> None:
    global _config, _entities_ready
    
    _LOG.info("=== UC Remote CONNECT Event ===")
    
    if not _config:
        _config = HorizonConfig()
    
    # Reload config from disk for reboot survival
    _config.reload_from_disk()
    
    if not _config.is_configured():
        _LOG.info("Integration not configured - awaiting setup")
        await api.set_device_state(DeviceStates.DISCONNECTED)
        return
    
    # Check if entities need initialization
    if not _entities_ready:
        _LOG.info("Entities not ready - initializing now")
        success = await _initialize_integration()
        
        if not success:
            _LOG.error("Entity initialization failed")
            await api.set_device_state(DeviceStates.ERROR)
            return
    else:
        _LOG.info("Entities already ready")
        
        # Even if entities exist, ensure client is connected
        if _client and not _client.is_connected:
            _LOG.info("Client disconnected - reconnecting")
            if not await _client.connect():
                _LOG.error("Reconnection failed")
                await api.set_device_state(DeviceStates.ERROR)
                return
    
    # Only set CONNECTED after entities are confirmed ready
    _LOG.info("âœ" Setting device state to CONNECTED")
    await api.set_device_state(DeviceStates.CONNECTED)


async def on_disconnect() -> None:
    _LOG.info("=== UC Remote DISCONNECT Event ===")
    _LOG.info("Preserving entities and connection for reconnection")
    # Do NOT disconnect client or clear entities
    # This allows seamless reconnection


async def on_subscribe_entities(entity_ids: list[str]):
    _LOG.info("=== Entity Subscription Request ===")
    _LOG.info("Requested entity IDs: %s", entity_ids)
    
    # Race condition protection
    if not _entities_ready:
        _LOG.error("âš  RACE CONDITION DETECTED: Subscription before entities ready!")
        _LOG.info("Attempting emergency initialization...")
        
        if _config and _config.is_configured():
            success = await _initialize_integration()
            if not success:
                _LOG.error("Emergency initialization failed")
                return
        else:
            _LOG.error("Cannot initialize - no configuration available")
            return
    
    # Log available entities for debugging
    available_ids = []
    for mp in _media_players.values():
        available_ids.append(mp.id)
    for remote in _remotes.values():
        available_ids.append(remote.id)
    
    _LOG.info("Available entity IDs: %s", available_ids)
    
    # Process subscriptions
    for entity_id in entity_ids:
        # Check media players
        for device_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                await media_player.push_update()
                _LOG.info("âœ" Subscribed to media player: %s", entity_id)
                break
        
        # Check remotes
        for device_id, remote in _remotes.items():
            if entity_id == remote.id:
                await remote.push_update()
                _LOG.info("âœ" Subscribed to remote: %s", entity_id)
                break


async def setup_handler(msg: SetupAction) -> SetupAction:
    global _setup_manager
    
    if not _setup_manager:
        _setup_manager = SetupManager(_config)
    
    action = await _setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("=== Setup Complete - Initializing Integration ===")
        await _initialize_integration()
    
    return action


async def main():
    global api, _config
    
    try:
        loop = asyncio.get_running_loop()
        api = ucapi.IntegrationAPI(loop)
        
        _config = HorizonConfig()
        
        if _config.is_configured():
            _LOG.info("=== Pre-initialization for Reboot Survival ===")
            _LOG.info("Configuration found - creating entities before UC Remote connects")
            loop.create_task(_initialize_integration())
        
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