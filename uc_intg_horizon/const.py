"""
Constants for Horizon integration.

:copyright: (c) 2025-2026 by Meir Miyara.
:license: MPL-2.0, see LICENSE for more details.
"""

CONNECT_RETRIES = 5
CONNECT_RETRY_DELAY = 3
PERIODIC_REFRESH_INTERVAL = 15
CHANNEL_UPDATE_DELAY = 2.5
POWER_COMMAND_DELAY = 3.0
DIGIT_KEY_DELAY = 0.3
DIGIT_ENTER_DELAY = 0.5
WATCHDOG_INTERVAL = 60
RECONNECT_DELAY = 10

PROVIDER_TO_COUNTRY = {
    "Ziggo": "nl",
    "VirginMedia": "gb",
    "Telenet": "be-nl",
    "UPC": "ch",
    "Sunrise": "ch",
}

KEY_MAP = {
    "UP": "ArrowUp",
    "DOWN": "ArrowDown",
    "LEFT": "ArrowLeft",
    "RIGHT": "ArrowRight",
    "SELECT": "Enter",
    "BACK": "Escape",
    "STOP": "MediaStop",
    "REWIND": "MediaRewind",
    "FASTFORWARD": "MediaFastForward",
    "VOLUME_UP": "VolumeUp",
    "VOLUME_DOWN": "VolumeDown",
    "MUTE": "VolumeMute",
    "CHANNEL_UP": "ChannelUp",
    "CHANNEL_DOWN": "ChannelDown",
    "GUIDE": "Guide",
    "RED": "Red",
    "GREEN": "Green",
    "YELLOW": "Yellow",
    "BLUE": "Blue",
    "HOME": "MediaTopMenu",
    "TV": "TV",
    "MENU": "ContextMenu",
    "SOURCE": "Settings",
    "0": "0", "1": "1", "2": "2", "3": "3", "4": "4",
    "5": "5", "6": "6", "7": "7", "8": "8", "9": "9",
}

SIMPLE_COMMANDS = [
    "POWER_ON", "POWER_OFF", "POWER_TOGGLE",
    "UP", "DOWN", "LEFT", "RIGHT", "SELECT", "BACK",
    "PLAYPAUSE", "STOP", "RECORD", "REWIND", "FASTFORWARD",
    "VOLUME_UP", "VOLUME_DOWN", "MUTE",
    "CHANNEL_UP", "CHANNEL_DOWN",
    "GUIDE", "HOME", "TV", "MENU", "SOURCE", "DVR",
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    "RED", "GREEN", "YELLOW", "BLUE",
]

STREAMING_APPS = [
    "Netflix", "BBC iPlayer", "ITVX", "All 4", "My5",
    "Prime Video", "YouTube", "Disney+",
]
