# LibreSpeed for Home Assistant

A Home Assistant custom component that integrates LibreSpeed for network speed testing with scheduling, data persistence, and UI configuration capabilities.

## Overview

LibreSpeed is a free and open-source, self-hosted speed test application. This integration brings LibreSpeed's privacy-respecting speed testing to Home Assistant, allowing you to monitor your internet connection performance over time without sharing data with third parties.

## Features

- **Speed Test Execution**: Run LibreSpeed tests to measure download speed, upload speed, and latency
- **Automatic Scheduling**: Configure automatic speed tests at regular intervals
- **Server Selection**: Choose from available LibreSpeed servers or use custom servers
- **Multiple Backends**: Choose between native Python implementation or official CLI for better performance
- **Data Persistence**: All test results are stored in Home Assistant's database

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository: `https://github.com/gtxaspec/librespeed-ha`
2. Search for "LibreSpeed" in HACS
3. Install the integration
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/librespeed` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Quick Start

### Initial Setup

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for **LibreSpeed**
4. Follow the configuration wizard:
   - Choose backend type (Native Python for most users, CLI for 500+ Mbps connections)
   - Select server (Automatic, choose from list, or enter custom server URL)
   - Configure automatic testing interval (default: 60 minutes)
5. Click **Submit**

For detailed configuration options, see [Configuration Guide](docs/CONFIGURATION.md).

## Entities

The integration creates the following entities:

### Sensors
- `sensor.librespeed_download_speed` - Download speed in Mbps
- `sensor.librespeed_upload_speed` - Upload speed in Mbps  
- `sensor.librespeed_ping` - Latency in milliseconds
- `sensor.librespeed_jitter` - Connection jitter (hidden by default)
- `sensor.librespeed_server_name` - Server used for testing
- `sensor.librespeed_last_test_time` - Timestamp of last test

### Controls
- `button.librespeed_run_speed_test` - Manually trigger a speed test
- `binary_sensor.librespeed_speed_test_running` - Indicates if test is running

## Basic Usage

### Manual Speed Test
Press the "Run Speed Test" button in the UI or use the service:
```yaml
service: button.press
target:
  entity_id: button.librespeed_run_speed_test
```

### Simple Automation
Run a speed test when internet connectivity is restored:
```yaml
automation:
  - alias: "Speed Test on Internet Restore"
    trigger:
      - platform: state
        entity_id: binary_sensor.internet_connection
        to: "on"
        from: "off"
        for: "00:02:00"
    action:
      - service: button.press
        target:
          entity_id: button.librespeed_run_speed_test
```

### Dashboard Card
```yaml
type: entities
title: Internet Speed
entities:
  - entity: sensor.librespeed_download_speed
    name: Download
  - entity: sensor.librespeed_upload_speed
    name: Upload
  - entity: sensor.librespeed_ping
    name: Latency
  - entity: button.librespeed_run_speed_test
    name: Run Test
```

## Documentation

- [Configuration Guide](docs/CONFIGURATION.md) - Detailed configuration options and parameters
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Advanced Usage](docs/ADVANCED_USAGE.md) - Automation blueprints, dashboards, and integrations

## Custom Server Setup

If you're running your own LibreSpeed server:

1. Select "Custom Server" during configuration
2. Enter your server URL (e.g., `https://speedtest.example.com`)
3. Enable "Skip Certificate Verification" if using self-signed certificates

For Docker deployment:
```bash
docker run -d --name librespeed -p 80:80 adolfintel/speedtest
```

## Troubleshooting

### Common Issues

- **Speed test button disabled**: A test is already running. Wait for completion.
- **Low speed results**: Switch to CLI backend for connections >500 Mbps
- **Custom server not working**: Verify URL and SSL certificate settings

For detailed troubleshooting, see the [Troubleshooting Guide](docs/TROUBLESHOOTING.md).

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/gtxaspec/librespeed-ha/issues).

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Credits

- [LibreSpeed](https://github.com/librespeed/speedtest) - The open source speed test
- [LibreSpeed CLI](https://github.com/librespeed/speedtest-cli) - Official command line client