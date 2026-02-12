#!/usr/bin/env python3
"""
LG Horizon Integration for Unfolded Circle Remote Two/3.

:copyright: (c) 2025 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from ucapi_framework import BaseConfigManager, get_config_path

from uc_intg_horizon.config import HorizonConfig
from uc_intg_horizon.driver import HorizonDriver
from uc_intg_horizon.setup_flow import HorizonSetupFlow

logging.getLogger(__name__).addHandler(logging.NullHandler())

try:
    driver_path = Path(__file__).parent.parent.absolute() / "driver.json"
    with open(driver_path, "r", encoding="utf-8") as f:
        driver_info = json.load(f)
        __version__ = driver_info.get("version", "0.0.0")
except (FileNotFoundError, json.JSONDecodeError, KeyError):
    __version__ = "0.0.0"


logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)-40s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_LOG = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point for the integration."""
    _LOG.info("=" * 70)
    _LOG.info("LG Horizon Integration v%s (ucapi-framework)", __version__)
    _LOG.info("=" * 70)

    driver = HorizonDriver()

    config_path = get_config_path(driver.api.config_dir_path or "")
    config_manager = BaseConfigManager(
        config_path,
        add_handler=driver.on_device_added,
        remove_handler=driver.on_device_removed,
        config_class=HorizonConfig,
    )
    driver.config_manager = config_manager

    setup_handler = HorizonSetupFlow.create_handler(driver)
    await driver.api.init("driver.json", setup_handler)

    await driver.register_all_configured_devices(connect=False)

    configs = list(config_manager.all())
    if configs:
        _LOG.info("Connecting %d configured device(s)...", len(configs))
        await driver.connect_devices()
    else:
        _LOG.info("No configured devices - waiting for setup")

    await asyncio.Future()


def run() -> None:
    """Run the integration."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOG.info("Integration stopped by user")
    except Exception as e:
        _LOG.error("Fatal error: %s", e, exc_info=True)
        raise


__all__ = ["__version__", "main", "run"]
