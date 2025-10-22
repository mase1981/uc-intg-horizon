# European TV Box (LG Horizon STB) Integration for Unfolded Circle REMOTE Two/3

![lghorizon](https://img.shields.io/badge/lg-horizon-red)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-horizon)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-horizon/total)
![License](https://img.shields.io/badge/license-MPL--2.0-blue)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA)](https://github.com/sponsors/mase1981/button)


> **Control your LG Horizon set-top boxes (Ziggo, Virgin Media, Telenet, UPC, Sunrise, Magenta) with the Unfolded Circle Remote 2/3**

Full integration for LG Horizon set-top boxes providing complete media player and remote control functionality with the Unfolded Circle Remote Two and Remote 3.

---

## 📺 Supported Providers

This integration works with LG Horizon boxes from the following providers:

- 🇳🇱 **Ziggo** (Netherlands)
- 🇬🇧 **Virgin Media** (United Kingdom & Ireland) - Verified Tested
- 🇧🇪 **Telenet** (Belgium)
- 🇨🇭 **UPC** (Switzerland)
- 🇨🇭 **Sunrise** (Switzerland)
- 🇦🇹 **Magenta** (Austria)

---

## ✨ Features

### Media Player
- ✅ **Power Control** - Turn box on/off, toggle power state
- ✅ **Playback Control** - Play, Pause, Stop, Fast Forward, Rewind
- ✅ **Recording** - Start recordings with Record button
- ✅ **Channel Navigation** - Channel up/down, direct channel entry (0-9)
- ✅ **Source Selection** - Switch between HDMI inputs and streaming apps
- ✅ **Now Playing Info** - Current channel and program information with artwork

### Remote Control
- ✅ **Full Button Mapping** - All physical remote buttons supported
- ✅ **D-Pad Navigation** - Complete directional pad with Enter/OK
- ✅ **Menu Controls** - Home, Guide, TV, Back, Context menu
- ✅ **Color Buttons** - Red, Green, Yellow, Blue function keys
- ✅ **Custom UI Pages** - Multiple control pages for different functions


---

## 📋 Requirements

- **Unfolded Circle Remote Two** or **Remote 3** (firmware 1.6.0+)
- **LG Horizon Set-Top Box** from a supported provider
- **Account Credentials** for your provider (username/email + password or refresh token)
- **Network Connectivity** between Remote and Horizon box

---

## 🚀 Installation

### Method 1: Remote Web Configurator (Recommended)

1. Download the latest `uc-intg-horizon-X.X.X.tar.gz` from [Releases](https://github.com/mase1981/uc-intg-horizon/releases)
2. Open your Unfolded Circle **Web Configurator** (http://remote-ip/)
3. Navigate to **Integrations** → **Add Integration**
4. Click **Upload Driver**
5. Select the downloaded `.tar.gz` file
6. Follow the on-screen setup wizard

### Method 2: Docker Run (One-Line Command)
```bash
docker run -d --name uc-intg-horizon --restart unless-stopped --network host -v $(pwd)/data:/data -e UC_CONFIG_HOME=/data -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9090 -e UC_DISABLE_MDNS_PUBLISH=false ghcr.io/mase1981/uc-intg-horizon:latest
```

### Method 3: Docker Compose

Create a `docker-compose.yml` file:
```yaml
version: '3.8'

services:
  horizon-integration:
    image: ghcr.io/mase1981/uc-intg-horizon:latest
    container_name: uc-intg-horizon
    restart: unless-stopped
    network_mode: host
    volumes:
      - ./data:/data
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_DISABLE_MDNS_PUBLISH=false
```

Then run:
```bash
docker-compose up -d
```

### Method 4: Python (Development)
```bash
# Clone repository
git clone https://github.com/mase1981/uc-intg-horizon.git
cd uc-intg-horizon

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run integration
python uc_intg_horizon/driver.py
```

---

## ⚙️ Configuration

### Step 1: Obtain Your Credentials

#### 🔑 For Virgin Media (UK/IE), Telenet (BE), UPC (CH) - Refresh Token Required

These providers require a **refresh token** instead of a password:

1. Open your browser's **Developer Tools** (press `F12`)
2. Go to the **Network** tab
3. Log in to your provider's website
4. Look for API requests to domains containing `horizon.tv`
5. Find the response containing `refresh_token`
6. Copy the entire refresh token string (long alphanumeric value)

**Example locations:**
- Virgin Media: https://www.virginmedia.com/
- Telenet: https://www.telenet.be/
- UPC: https://www.upc.ch/

#### 🔑 For Ziggo (NL), Sunrise (CH), Magenta (AT) - Password

Use your standard account **username** and **password**.

### Step 2: Setup in Remote Configurator

1. In the UC Remote web configurator, go to **Integrations**
2. Find **LG Horizon Set-Top Box** and click **Configure**
3. Enter your credentials:
   - **Provider**: Select your TV provider from dropdown
   - **Username / Email**: Your account email address
   - **Password (or Refresh Token)**:
     - 🇳🇱🇦🇹 NL/AT: Enter your account password
     - 🇬🇧🇧🇪🇨🇭 UK/BE/CH: Enter your refresh token
4. Click **Submit**
5. Integration will automatically discover all boxes on your account
6. Entities are created automatically for each discovered box

---

## 🎮 Usage

### Entities Created

For each Horizon box discovered, **two entities** are created:

#### 1️⃣ Media Player Entity
- **Entity ID**: `{device_id}`
- **Name**: `{Device Name}`
- **Type**: Media Player

**Features:**
- Power on/off/toggle
- Play/Pause/Stop playback
- Channel up/down navigation
- Volume control (via HDMI-CEC)
- Source selection (HDMI inputs + apps)
- D-Pad navigation
- Now playing information with artwork

#### 2️⃣ Remote Control Entity
- **Entity ID**: `{device_id}_remote`
- **Name**: `{Device Name} Remote`
- **Type**: Remote

**Features:**
- Complete physical remote button mapping
- Four custom UI pages:
  - **Main Control**: Power, navigation, playback, menus
  - **Channel Numbers**: 0-9 keypad with channel controls
  - **Playback**: Transport controls with volume
  - **Color Buttons**: Red, Green, Yellow, Blue keys

### Adding to Activities

1. Create or edit an **Activity**
2. Add the **Media Player** entity as the main device
3. Map power on/off commands
4. Optionally set default source (HDMI input or app)
5. Use the **Remote Control** entity for advanced button access

### Channel Entry

Direct channel entry using number buttons:

1. Open the **Remote Control** entity
2. Navigate to **Channel Numbers** page
3. Press digit buttons for channel (e.g., `1` → `0` → `3` for channel 103)
4. Press **OK** to confirm
5. Box will change to the entered channel

### Source Switching

Switch between HDMI inputs and streaming apps:

1. Open **Media Player** entity
2. Click **Sources**
3. Select from:
   - HDMI 1, HDMI 2, HDMI 3, HDMI 4
   - Netflix, BBC iPlayer, ITVX, All 4, My5
   - Prime Video, YouTube, Disney+
4. Settings menu will open for navigation

---

## 🎛️ Button Mapping

Complete mapping of all physical Horizon remote buttons:

| Physical Button | Remote Entity Command | Function |
|----------------|----------------------|----------|
| **Power** | POWER_ON / POWER_OFF | Turn box on/off |
| **TV** | TV | Return to live TV from menus |
| **Home** | HOME | Open main menu |
| **Guide** | GUIDE | Open TV guide |
| **Back** | BACK | Go back one screen |
| **OK** | SELECT | Confirm/Select |
| **↑ ↓ ← →** | UP / DOWN / LEFT / RIGHT | Navigate menus |
| **Play/Pause** | PLAYPAUSE | Toggle playback |
| **Stop** | STOP | Stop playback |
| **⏪ Rewind** | REWIND | Skip backward |
| **⏩ Fast Forward** | FASTFORWARD | Skip forward |
| **Channel ↑** | CHANNEL_UP | Next channel |
| **Channel ↓** | CHANNEL_DOWN | Previous channel |
| **Volume +** | VOLUME_UP | Increase volume (CEC) |
| **Volume -** | VOLUME_DOWN | Decrease volume (CEC) |
| **Mute** | MUTE | Mute/unmute (CEC) |
| **0-9** | 0-9 | Direct channel entry |
| **Red** | RED | Red function key |
| **Green** | GREEN | Green function key |
| **Yellow** | YELLOW | Yellow function key |
| **Blue** | BLUE | Blue function key |
| **Menu** | MENU | Context menu |

---

## 🔧 Troubleshooting

### Connection Issues

**Problem**: Setup fails with "Connection refused" or timeout

**Solutions:**
1. ✅ Verify credentials are correct
2. ✅ For UK/BE/CH: Ensure you're using **refresh token**, not password
3. ✅ Check Horizon box is powered on and connected to network
4. ✅ Restart the Horizon box
5. ✅ Try obtaining a fresh refresh token from provider website

### Entities Unavailable After Reboot

**Problem**: After restarting UC Remote, entities show as "unavailable"

**Solutions:**
1. ✅ Integration includes reboot survival - wait 30-60 seconds
2. ✅ Check MQTT connection is established (box state shows in logs)
3. ✅ Restart integration from web configurator if still unavailable
4. ✅ Review integration logs for connection errors

### Volume Control Not Working

**Problem**: Volume up/down/mute buttons have no effect

**Explanation**: 
Horizon boxes control TV volume via **HDMI-CEC** (Consumer Electronics Control), not directly. The commands are sent to your TV through the HDMI cable.

**Solutions:**
1. ✅ Enable HDMI-CEC on your TV (may be called "Anynet+", "Bravia Sync", "Simplink", "VIERA Link", etc.)
2. ✅ Verify HDMI cable connects Horizon box to TV
3. ✅ Check TV settings for CEC/external device control
4. ✅ Enable CEC for the specific HDMI input being used
5. ✅ Some TVs require CEC to be enabled per HDMI port

**CEC Names by TV Brand:**
- Samsung: "Anynet+"
- LG: "Simplink"
- Sony: "Bravia Sync"
- Panasonic: "VIERA Link"
- Philips: "EasyLink"
- Toshiba: "CE-Link"

### Commands Execute But Nothing Happens

**Problem**: Buttons report success but TV doesn't respond

**Root Cause**: Some commands are **context-dependent**

**Examples:**
- `BACK` only works when inside a menu
- `HOME` may not respond if already on home screen
- `TV` returns to live TV from menus

**Solutions:**
1. ✅ Ensure box is in correct state for the command
2. ✅ Try the same button on physical remote to verify behavior
3. ✅ Some commands require the menu to be open first
4. ✅ Reboot the Horizon box if commands stop responding

### Refresh Token Expired

**Problem**: Integration stops working after weeks/months

**Solution:**
1. ✅ Refresh tokens expire periodically (typically 90 days)
2. ✅ Obtain a new refresh token using the instructions above
3. ✅ Reconfigure integration with new token in web configurator
4. ✅ No need to remove/re-add - just update credentials

---

## ⚠️ Known Limitations

| Limitation | Explanation | Workaround |
|-----------|-------------|------------|
| **Volume via CEC only** | Horizon boxes use HDMI-CEC for TV volume control | Enable CEC on your TV settings |
| **No individual channel sources** | Showing all TV channels would cause timeout | Use direct channel entry (0-9 buttons) |
| **Recording management** | Can start recordings but can't list/manage existing ones | Use Horizon box UI or mobile app |
| **Multi-room sync** | Each box requires separate setup | Add each box individually to integration |
| **Some menus non-responsive** | Certain proprietary menus can't be controlled | Use physical remote for those menus |

---

## 🏗️ Architecture

### Integration Components
```
uc-intg-horizon/
├── uc_intg_horizon/
│   ├── __init__.py           # Package initialization with version
│   ├── client.py             # LG Horizon API client wrapper
│   ├── config.py             # Configuration management with persistence
│   ├── driver.py             # Main integration driver with reboot survival
│   ├── media_player.py       # Media Player entity implementation
│   ├── remote.py             # Remote Control entity implementation
│   └── setup_manager.py      # Setup flow handler
├── driver.json               # Integration metadata
├── pyproject.toml            # Python project configuration
├── requirements.txt          # Runtime dependencies
├── LICENSE                   # MPL-2.0 license
└── README.md                # This file
```

### Dependencies

- **ucapi** (>=0.3.1) - Unfolded Circle Integration API
- **lghorizon** (>=0.8.6) - LG Horizon Python library
- **aiohttp** (>=3.9.0) - Async HTTP client
- **certifi** - SSL certificate verification

---

## 👨‍💻 Development

### Building From Source
```bash
# Clone repository
git clone https://github.com/mase1981/uc-intg-horizon.git
cd uc-intg-horizon

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Build distribution package
python -m build

# Output: dist/uc-intg-horizon-X.X.X.tar.gz
```

### Contributing

Contributions are welcome! Please follow these guidelines:

1. 🍴 Fork the repository
2. 🌿 Create a feature branch (`git checkout -b feature/amazing-feature`)
3. 💾 Commit your changes (`git commit -m 'Add amazing feature'`)
4. 📤 Push to the branch (`git push origin feature/amazing-feature`)
5. 🎉 Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Use type hints where applicable
- Add docstrings to all functions and classes
- Keep line length to 100 characters
- Use absolute imports only

---

## 🙏 Credits & Acknowledgments

### Integration Development
- **Author**: [Meir Miyara](https://www.linkedin.com/in/meirmiyara/)

### Libraries & References
- **lghorizon-python**: [Sholofly/lghorizon-python](https://github.com/Sholofly/lghorizon-python) - Python library for LG Horizon
- **Home Assistant Integration**: [Sholofly/lghorizon](https://github.com/Sholofly/lghorizon) - Reference implementation
- **Unfolded Circle**: [Integration Python Library](https://github.com/unfoldedcircle/integration-python-library)

### Community
- **Unfolded Circle Community**: For testing and feedback
- **Home Assistant Community**: For command mapping reference

---

## 💖 Support the Project

If you find this integration useful, please consider:

- ⭐ **Star this repository** on GitHub
- 🐛 **Report issues** to help improve the integration
- 💡 **Share feedback** in discussions
- 📖 **Contribute** documentation or code improvements

### Sponsor

If you'd like to support continued development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Support-yellow?logo=buy-me-a-coffee)](https://www.buymeacoffee.com/mase1981)

---

## 📞 Support & Community

### Getting Help

- 📋 **Issues**: [GitHub Issues](https://github.com/mase1981/uc-intg-horizon/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/mase1981/uc-intg-horizon/discussions)
- 🌐 **UC Community**: [Unfolded Circle Forum](https://unfoldedcircle.com/community)

### Reporting Issues

When reporting issues, please include:

1. Integration version
2. Horizon provider (Ziggo, Virgin Media, etc.)
3. Horizon box model
4. UC Remote firmware version
5. Detailed description of the problem
6. Relevant log excerpts

---

## 📜 License

This project is licensed under the **Mozilla Public License 2.0** (MPL-2.0).

See the [LICENSE](LICENSE) file for full details.
```
Copyright (c) 2025 Meir Miyara

This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at http://mozilla.org/MPL/2.0/.
```

<div align="center">

**Enjoy controlling your LG Horizon set-top box with your Unfolded Circle Remote!** 🎉

Made with ❤️ by [Meir Miyara](https://www.linkedin.com/in/meirmiyara/)

</div>