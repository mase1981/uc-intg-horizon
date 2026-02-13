# LG Horizon Integration for Unfolded Circle Remote 2/3

Control your LG Horizon set-top boxes directly from your Unfolded Circle Remote 2 or Remote 3 with comprehensive media player and remote control functionality.

![lghorizon](https://img.shields.io/badge/lg-horizon-red)
[![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-horizon?style=flat-square)](https://github.com/mase1981/uc-intg-horizon/releases)
![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)
[![GitHub issues](https://img.shields.io/github/issues/mase1981/uc-intg-horizon?style=flat-square)](https://github.com/mase1981/uc-intg-horizon/issues)
[![Community Forum](https://img.shields.io/badge/community-forum-blue?style=flat-square)](https://unfolded.community/)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-horizon/total?style=flat-square)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg?style=flat-square)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA&style=flat-square)](https://github.com/sponsors/mase1981)


## Features

Full integration for LG Horizon set-top boxes providing complete media player and remote control functionality with the Unfolded Circle Remote Two and Remote 3.

---
## ❤️ Support Development ❤️

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

Your support helps maintain this integration. Thank you! ❤️
---

### 📺 **Supported Providers**

This integration works with LG Horizon boxes from the following providers:

- 🇳🇱 **Ziggo** (Netherlands)
- 🇬🇧 **Virgin Media** (United Kingdom & Ireland) - Verified Tested
- 🇧🇪 **Telenet** (Belgium)
- 🇨🇭 **UPC** (Switzerland)
- 🇨🇭 **Sunrise** (Switzerland)

### 🎵 **Media Player Control**

#### **Power Management**
- **Power Control** - Turn box on/off, toggle power state
- **State Feedback** - Real-time power state monitoring

#### **Playback Control**
- **Play/Pause Toggle** - Control playback state
- **Stop** - Stop playback
- **Fast Forward/Rewind** - Skip forward/backward
- **Seek** - Jump to specific position in recordings/catch-up TV
- **Record** - Start recordings with Record button

#### **Channel Navigation**
- **Channel Up/Down** - Navigate through channels
- **Direct Entry** - Direct channel entry (0-9 keypad)
- **Channel Info** - Current channel and program information

#### **Source Selection**
- **HDMI Inputs** - Switch between HDMI 1-4
- **Streaming Apps** - Netflix, BBC iPlayer, ITVX, All 4, My5, Prime Video, YouTube, Disney+
- **Settings Access** - Settings menu navigation

#### **Media Information**
- **Now Playing** - Current channel and program information
- **Artwork Display** - Program artwork and images

### 🎛️ **Remote Control**

#### **Complete Button Mapping**
- **D-Pad Navigation** - Complete directional pad with Enter/OK
- **Menu Controls** - Home, Guide, TV, Back, Context menu
- **Color Buttons** - Red, Green, Yellow, Blue function keys
- **Transport Controls** - Play, Pause, Stop, Fast Forward, Rewind
- **Volume Control** - Volume up/down, mute (via HDMI-CEC)
- **Channel Controls** - Channel up/down navigation
- **Number Keypad** - Direct channel entry (0-9)

#### **Custom UI Pages**
- **Main Control** - Power, navigation, playback, menus
- **Channel Numbers** - 0-9 keypad with channel controls
- **Playback** - Transport controls with volume
- **Color Buttons** - Red, Green, Yellow, Blue keys

### **Provider Requirements**

- **Account Credentials** - Provider account username/email + password or refresh token
- **Supported Providers** - Ziggo, Virgin Media, Telenet, UPC, Sunrise
- **Network Access** - Device must be on same local network
- **HDMI-CEC** - Required for volume control (enable on TV)

### **Network Requirements**

- **Local Network Access** - Integration requires same network as Horizon box
- **Network Connectivity** - Reliable network connection between Remote and box
- **Static IP Recommended** - Device should have static IP or DHCP reservation

## Installation

### Option 1: Remote Web Interface (Recommended)
1. Navigate to the [**Releases**](https://github.com/mase1981/uc-intg-horizon/releases) page
2. Download the latest `uc-intg-horizon-<version>-aarch64.tar.gz` file
3. Open your remote's web interface (`http://your-remote-ip`)
4. Go to **Settings** → **Integrations** → **Add Integration**
5. Click **Upload** and select the downloaded `.tar.gz` file

### Option 2: Docker (Advanced Users)

The integration is available as a pre-built Docker image from GitHub Container Registry:

**Image**: `ghcr.io/mase1981/uc-intg-horizon:latest`

**Docker Compose:**
```yaml
services:
  uc-intg-horizon:
    image: ghcr.io/mase1981/uc-intg-horizon:latest
    container_name: uc-intg-horizon
    network_mode: host
    volumes:
      - </local/path>:/data
    environment:
      - UC_CONFIG_HOME=/data
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - PYTHONPATH=/app
    restart: unless-stopped
```

**Docker Run:**
```bash
docker run -d --name uc-horizon --restart unless-stopped --network host -v horizon-config:/app/config -e UC_CONFIG_HOME=/app/config -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9090 -e PYTHONPATH=/app ghcr.io/mase1981/uc-intg-horizon:latest
```

## Configuration

### Step 1: Obtain Your Credentials

**IMPORTANT**: Different providers require different authentication methods.

#### 🔑 Easy Token Extraction Tool (Recommended)

For **Virgin Media, Telenet, UPC, Sunrise** (token-based providers):

1. Download [`get_horizon_token.html`](https://github.com/mase1981/uc-intg-horizon/raw/main/get_horizon_token.html) from the repository
2. Open the file in any web browser (Chrome, Firefox, Edge, Safari)
3. Follow the 3-step wizard:
   - **Step 1** - Select your provider from the dropdown
   - **Step 2** - Click to open login page and sign in with your credentials
   - **Step 3** - Paste your token and click "Clean & Prepare Token"
4. Click "Copy Token to Clipboard"
5. Use the cleaned token in the integration setup below

The tool automatically cleans and validates your token, removing quotes, whitespace, and prefixes.

#### 🔑 Provider Authentication

**For Virgin Media (UK/IE), Telenet (BE), UPC (CH), Sunrise (CH):**
- Require **refresh token**
- Use Token Extractor Tool above

**For Ziggo (NL):**
- Use regular account **password**
- No token extraction needed

#### Network Setup:
- **Wired Connection** - Recommended for stability
- **Static IP** - Recommended via DHCP reservation
- **Firewall** - Allow network traffic
- **Network Isolation** - Must be on same subnet as Remote

### Step 2: Setup Integration

1. After installation, go to **Settings** → **Integrations**
2. The LG Horizon integration should appear in **Available Integrations**
3. Click **"Configure"** to begin setup:

#### **Configuration:**
- **Provider** - Select your TV provider from dropdown
- **Username/Email** - Your account email address
- **Password (or Refresh Token)**:
  - 🇳🇱 NL - Enter your account password
  - 🇬🇧🇧🇪🇨🇭 UK/BE/CH - Enter your refresh token
- Click **Submit**

#### **Connection Test:**
- Integration verifies credentials
- Discovers all boxes on your account
- Setup fails if credentials invalid

4. Integration will create entities for each discovered box:
   - **Media Player** - `{device_id}` - Full media control
   - **Remote** - `{device_id}_remote` - Button mapping and UI pages
   - **State Sensor** - `{device_id}_state` - Device connection state (ONLINE_RUNNING/ONLINE_STANDBY/OFFLINE)
   - **Channel Sensor** - `{device_id}_channel` - Current channel name
   - **Program Sensor** - `{device_id}_program` - Current program title

## Using the Integration

### Media Player Entity

The media player entity provides complete control:

- **Power Control** - On/Off with state feedback
- **Playback Control** - Play/Pause, Stop, Fast Forward, Rewind
- **Channel Navigation** - Channel up/down
- **Source Selection** - HDMI inputs and streaming apps
- **Volume Control** - Volume up/down, mute (via HDMI-CEC)
- **Media Info** - Current channel, program, artwork

### Remote Control Entity

The remote entity provides complete button mapping:

- **D-Pad Navigation** - Up, Down, Left, Right, OK
- **Menu Controls** - Home, Guide, TV, Back, Menu
- **Transport Controls** - Play, Pause, Stop, Rewind, Fast Forward
- **Channel Controls** - Channel up/down, number entry (0-9)
- **Color Buttons** - Red, Green, Yellow, Blue
- **Volume Controls** - Volume up/down, mute (via HDMI-CEC)

### Channel Entry

Direct channel entry using number buttons:

1. Open the **Remote Control** entity
2. Navigate to **Channel Numbers** page
3. Press digit buttons for channel (e.g., `1` → `0` → `3` for channel 103)
4. Press **OK** to confirm

### Source Switching

Switch between HDMI inputs and streaming apps:

1. Open **Media Player** entity
2. Click **Sources**
3. Select from HDMI inputs or streaming apps
4. Settings menu will open for navigation

### Seek Support

For recordings and catch-up TV, use seek to jump to specific positions:

1. During playback of recorded content or catch-up TV
2. Use the seek control in the **Media Player** entity
3. Jump forward or backward to any position in the program

### Sensor Entities

Three sensor entities are created for each set-top box:

| Sensor | Entity ID | Description |
|--------|-----------|-------------|
| **Device State** | `{device_id}_state` | Connection state: `ONLINE_RUNNING`, `ONLINE_STANDBY`, or `OFFLINE` |
| **Channel** | `{device_id}_channel` | Name of the current channel being watched |
| **Program** | `{device_id}_program` | Title of the current program |

These sensors update in real-time via MQTT and can be used for automations or status displays.

## Credits

- **Developer** - Meir Miyara
- **lghorizon-python** - [Sholofly/lghorizon-python](https://github.com/Sholofly/lghorizon-python) - Python library for LG Horizon
- **Home Assistant Integration** - [Sholofly/lghorizon](https://github.com/Sholofly/lghorizon) - Reference implementation
- **Unfolded Circle** - Remote 2/3 integration framework (ucapi)
- **Community** - Testing and feedback from UC community

## License

This project is licensed under the Mozilla Public License 2.0 (MPL-2.0) - see LICENSE file for details.

## Support & Community

- **GitHub Issues** - [Report bugs and request features](https://github.com/mase1981/uc-intg-horizon/issues)
- **UC Community Forum** - [General discussion and support](https://unfolded.community/)
- **Developer** - [Meir Miyara](https://www.linkedin.com/in/meirmiyara)

---

**Made with ❤️ for the Unfolded Circle Community**

**Thank You** - Meir Miyara
