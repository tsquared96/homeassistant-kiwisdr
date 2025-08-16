# KiwiSDR Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

This integration allows you to connect and control KiwiSDR software-defined radios in Home Assistant.

## Features
- Real-time status monitoring
- Audio streaming via media player
- Waterfall spectrum display
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

## Services
- `kiwisdr.tune`: Tune to frequency
- `kiwisdr.set_agc`: Configure AGC
- `kiwisdr.set_squelch`: Set squelch level
- `kiwisdr.waterfall_settings`: Configure waterfall
