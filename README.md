# KiwiSDR Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This integration allows you to connect and control KiwiSDR software-defined radios in Home Assistant.

## Features
- Real-time status monitoring
- Audio streaming via media player
- Waterfall spectrum display
- **Frequency control via number entity** - Easy tuning from the dashboard
- **Step up/down frequency controls** - Fine-tune with buttons
- Preset station support (FT8, WWV, Air Band, etc.)
- WebSocket support for real-time updates
- Admin controls (with admin password)

## Installation

### HACS (Recommended)
1. Add this repository to HACS as a custom repository
2. Search for "KiwiSDR" in HACS
3. Install the integration
4. Restart Home Assistant
5. Add KiwiSDR via UI

### Manual Installation
Copy the `custom_components/kiwisdr` folder to your Home Assistant configuration directory.

## Configuration
Configure via UI: Settings → Devices & Services → Add Integration → KiwiSDR

## Entities

This integration creates the following entities:

- **Media Player**: `media_player.kiwisdr_radio` - Audio streaming and playback control
- **Camera**: `camera.kiwisdr_waterfall` - Real-time waterfall spectrum display
- **Number**: `number.kiwisdr_frequency` - Frequency control (0-30000 kHz)
- **Sensors**: Status, users, frequency, mode, signal strength, GPS, uptime, etc.

## Dashboard Usage

### Basic Frequency Control

Add the frequency number entity to your dashboard for easy tuning:

```yaml
type: entities
entities:
  - entity: number.kiwisdr_frequency
    name: Frequency (kHz)
  - entity: media_player.kiwisdr_radio
  - entity: camera.kiwisdr_waterfall
    name: Waterfall
```

### Advanced Tuning Controls

Create a custom card with frequency step buttons:

```yaml
type: vertical-stack
cards:
  - type: entities
    entities:
      - entity: number.kiwisdr_frequency
        name: Frequency (kHz)
      - entity: media_player.kiwisdr_radio
  - type: horizontal-stack
    cards:
      - type: button
        name: "-1 kHz"
        tap_action:
          action: call-service
          service: kiwisdr.step_frequency_down
          target:
            entity_id: media_player.kiwisdr_radio
          data:
            step: 1.0
      - type: button
        name: "-0.1 kHz"
        tap_action:
          action: call-service
          service: kiwisdr.step_frequency_down
          target:
            entity_id: media_player.kiwisdr_radio
          data:
            step: 0.1
      - type: button
        name: "+0.1 kHz"
        tap_action:
          action: call-service
          service: kiwisdr.step_frequency_up
          target:
            entity_id: media_player.kiwisdr_radio
          data:
            step: 0.1
      - type: button
        name: "+1 kHz"
        tap_action:
          action: call-service
          service: kiwisdr.step_frequency_up
          target:
            entity_id: media_player.kiwisdr_radio
          data:
            step: 1.0
  - type: picture-entity
    entity: camera.kiwisdr_waterfall
    show_state: false
```

### Preset Stations

Quick access to preset stations:

```yaml
type: horizontal-stack
cards:
  - type: button
    name: FT8 7.074
    tap_action:
      action: call-service
      service: kiwisdr.tune_preset
      data:
        preset: "FT8 7.074 MHz"
  - type: button
    name: WWV 10 MHz
    tap_action:
      action: call-service
      service: kiwisdr.tune_preset
      data:
        preset: "WWV 10 MHz"
  - type: button
    name: Air Band
    tap_action:
      action: call-service
      service: kiwisdr.tune_preset
      data:
        preset: "Air Band"
```

## Services

### Tuning Services
- `kiwisdr.tune`: Tune to specific frequency and mode
- `kiwisdr.step_frequency_up`: Increase frequency by step amount
- `kiwisdr.step_frequency_down`: Decrease frequency by step amount
- `kiwisdr.tune_preset`: Tune to preset station
- `kiwisdr.set_mode`: Change demodulation mode

### Receiver Configuration
- `kiwisdr.set_agc`: Configure Automatic Gain Control
- `kiwisdr.set_squelch`: Set squelch level
- `kiwisdr.set_bandwidth`: Set receiver bandwidth

### Display Settings
- `kiwisdr.waterfall_settings`: Configure waterfall zoom, speed, and colormap

## Available Preset Stations

- WWV time stations (2.5, 5, 10, 15 MHz)
- CHU time stations (3.33, 7.85 MHz)
- FT8 frequencies (3.573, 7.074, 14.074 MHz)
- WSPR frequencies (7.0386, 14.0956 MHz)
- CB Channel 19, Air Band, Marine VHF, and more

## Troubleshooting

### Waterfall Not Showing
- Ensure the waterfall is enabled in the integration configuration
- Check that the KiwiSDR WebSocket is connected (check sensor attributes)
- Verify your KiwiSDR has waterfall enabled

### Audio Not Playing
- Make sure audio streaming is enabled in the integration configuration
- Check that the media player state is "playing"
- Verify the audio stream URL is accessible
