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

### Via HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **⋮** → **Custom repositories**
3. Add repository: `https://github.com/gtxaspec/librespeed-ha`
4. Category: **Integration**
5. Click **Add** → **Install**
6. Restart Home Assistant

### Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/librespeed` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

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

The integration creates the following entities per instance. Entity IDs include the instance name (e.g. `sensor.librespeed_automatic_download_speed` for an instance titled "LibreSpeed (Automatic)").

### Sensors
- **Download Speed** - Download speed in Mbps
- **Upload Speed** - Upload speed in Mbps
- **Ping** - Latency in milliseconds
- **Jitter** - Connection jitter in milliseconds
- **Server Name** - Server used for testing (diagnostic)
- **Last Test Time** - Timestamp of last test (diagnostic)
- **Test Data Downloaded** - Data downloaded during last test in MB (diagnostic)
- **Test Data Uploaded** - Data uploaded during last test in MB (diagnostic)
- **Lifetime Data Downloaded** - Total data downloaded across all tests in GB (diagnostic)
- **Lifetime Data Uploaded** - Total data uploaded across all tests in GB (diagnostic)

### Controls
- **Run Speed Test** - Button to manually trigger a speed test
- **Speed Test Running** - Binary sensor indicating if a test is in progress

## Basic Usage

### Manual Speed Test
Press the "Run Speed Test" button in the UI or use the service:
```yaml
service: button.press
target:
  entity_id: button.librespeed_automatic_run_speed_test
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
          entity_id: button.librespeed_automatic_run_speed_test
```

### Dashboard Card
```yaml
type: entities
title: Internet Speed
entities:
  - entity: sensor.librespeed_automatic_download_speed
    name: Download
  - entity: sensor.librespeed_automatic_upload_speed
    name: Upload
  - entity: sensor.librespeed_automatic_ping
    name: Latency
  - entity: button.librespeed_automatic_run_speed_test
    name: Run Test
```

> **Note:** Replace `automatic` with your instance name slug if you chose a specific server or custom title.

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