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


def _on_token_update(new_token: str) -> None:
    """
    Callback for when the refresh token is updated.
    
    :param new_token: New refresh token
    """
    global _config
    
    if _config:
        _LOG.info("Updating stored refresh token")
        _config.password = new_token
        _config.save_config()


async def _initialize_entities():
    """Initialize entities with race condition protection - MANDATORY for reboot survival."""
    global _config, _client, _media_players, _remotes, api, _entities_ready
    
    async with _initialization_lock:
        if _entities_ready:
            _LOG.debug("Entities already initialized, skipping")
            return
            
        if not _config or not _config.is_configured():
            _LOG.info("Integration not configured, skipping entity initialization")
            return
            
        _LOG.info("Initializing entities for reboot survival...")
        
        try:
            # Create Horizon API client with token update callback
            _client = HorizonClient(
                provider=_config.provider,
                username=_config.username,
                password=_config.password,
                token_update_callback=_on_token_update,  # ← NEW: Token refresh handler
            )
            
            if not await _client.connect():
                _LOG.error("Failed to connect to Horizon API during initialization")
                _entities_ready = False
                return
            
            api.available_entities.clear()
            _media_players.clear()
            _remotes.clear()
            
            for device in _config.devices:
                device_id = device["device_id"]
                device_name = device["name"]
                
                _LOG.info("Creating entities for device: %s (%s)", device_name, device_id)
                
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
            
            _LOG.info(
                "Entities created and ready: %d media players, %d remotes",
                len(_media_players),
                len(_remotes),
            )
            
        except Exception as e:
            _LOG.error("Failed to initialize entities: %s", e, exc_info=True)
            _entities_ready = False
            raise


async def on_connect() -> None:
    """Handle Remote connection with reboot survival."""
    global _config, _entities_ready, _client
    
    _LOG.info("Remote connected. Checking configuration state...")
    
    if not _config:
        _config = HorizonConfig()
    
    _config.reload_from_disk()
    
    if _config.is_configured() and not _entities_ready:
        _LOG.info("Configuration found but entities missing, reinitializing...")
        try:
            await _initialize_entities()
        except Exception as e:
            _LOG.error("Failed to reinitialize entities: %s", e)
            await api.set_device_state(DeviceStates.ERROR)
            return
    
    if _config.is_configured() and _entities_ready:
        await api.set_device_state(DeviceStates.CONNECTED)
    elif not _config.is_configured():
        await api.set_device_state(DeviceStates.DISCONNECTED)
    else:
        await api.set_device_state(DeviceStates.ERROR)


async def on_disconnect() -> None:
    """Handle Remote disconnection."""
    global _client
    
    _LOG.info("Remote disconnected")
    
    if _client:
        await _client.disconnect()


async def on_subscribe_entities(entity_ids: list[str]):
    """Handle entity subscriptions with race condition protection."""
    _LOG.info(f"Entities subscription requested: {entity_ids}")
    
    if not _entities_ready:
        _LOG.error("RACE CONDITION: Subscription before entities ready! Attempting recovery...")
        if _config and _config.is_configured():
            await _initialize_entities()
        else:
            _LOG.error("Cannot recover - no configuration available")
            return
    
    available_entity_ids = []
    for device_id in _media_players.keys():
        available_entity_ids.append(_media_players[device_id].id)
    for device_id in _remotes.keys():
        available_entity_ids.append(_remotes[device_id].id)
    
    _LOG.info(f"Available entities: {available_entity_ids}")
    
    for entity_id in entity_ids:
        for device_id, media_player in _media_players.items():
            if entity_id == media_player.id:
                await media_player.push_update()
                _LOG.info(f"Subscribed to media player: {entity_id}")
                break
        
        for device_id, remote in _remotes.items():
            if entity_id == remote.id:
                await remote.push_update()
                _LOG.info(f"Subscribed to remote: {entity_id}")
                break


async def setup_handler(msg: SetupAction) -> SetupAction:
    """Handle setup flow and create entities."""
    global _setup_manager, _entities_ready
    
    if not _setup_manager:
        _setup_manager = SetupManager(_config)
    
    action = await _setup_manager.handle_setup(msg)
    
    if isinstance(action, SetupComplete):
        _LOG.info("Setup confirmed. Initializing integration components...")
        await _initialize_entities()
    
    return action


async def main():
    """Main entry point with pre-initialization for reboot survival."""
    global api, _config
    
    try:
        loop = asyncio.get_running_loop()
        api = ucapi.IntegrationAPI(loop)
        
        _config = HorizonConfig()
        if _config.is_configured():
            _LOG.info(
                "Found existing configuration, pre-initializing entities for reboot survival"
            )
            loop.create_task(_initialize_entities())
        
        api.add_listener(Events.CONNECT, on_connect)
        api.add_listener(Events.DISCONNECT, on_disconnect)
        api.add_listener(Events.SUBSCRIBE_ENTITIES, on_subscribe_entities)
        
        await api.init("driver.json", setup_handler)
        await api.set_device_state(DeviceStates.DISCONNECTED)
        
        _LOG.info("Horizon integration driver started successfully")
        
        await asyncio.Future()
        
    except asyncio.CancelledError:
        _LOG.info("Driver task cancelled.")
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