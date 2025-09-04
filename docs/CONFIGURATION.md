# Configuration Guide

## Configuration Parameters

### Installation Parameters

During initial setup, you'll configure these parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| **Backend Type** | Select | Yes | Native Python | Processing backend for speed tests:<br>• **Native Python**: Pure Python implementation, suitable for most connections<br>• **Official CLI**: Binary CLI for high-speed connections (>500 Mbps), auto-downloaded |
| **Server Selection** | Select | Yes | Automatic | How to select the test server:<br>• **Automatic**: Auto-detect best server based on latency<br>• **Select Server**: Choose from list of available servers<br>• **Custom Server**: Use your own LibreSpeed instance |
| **Server ID** | Dropdown | If "Select Server" | None | Choose from list of available LibreSpeed servers worldwide |
| **Custom Server URL** | URL | If "Custom Server" | None | Full URL to your LibreSpeed server (e.g., `https://speedtest.example.com`) |
| **Enable Automatic Updates** | Boolean | Yes | True | Run tests automatically on schedule |
| **Update Interval** | Number | If auto enabled | 60 | Minutes between automatic tests (30-1440) |
| **Test Timeout** | Number | No | 240 | Maximum time allowed for a single speed test (60-600 seconds) |
| **Skip Certificate Verification** | Boolean | No | False | Skip SSL verification for self-signed certificates (CLI backend only) ⚠️ |

### Modifiable Options

After initial setup, you can modify these parameters through the integration options:

| Parameter | Type | Modifiable | Range/Options | Description |
|-----------|------|------------|---------------|-------------|
| **Backend Type** | Select | Yes | Native Python / Official CLI | Switch between backends without reinstalling |
| **Server Selection Mode** | Select | Yes | Automatic / Select / Custom | Change server selection method |
| **Server ID** | Dropdown | Yes | Server list | Pick different server from list |
| **Custom Server URL** | URL | Yes | Valid URL | Update custom server address |
| **Enable Automatic Updates** | Toggle | Yes | On/Off | Enable or disable scheduled tests |
| **Update Interval** | Slider | Yes | 30-1440 minutes | Adjust test frequency:<br>• 30-60 min: Frequent monitoring<br>• 60 min: Hourly (default)<br>• 180-360 min: Regular checks<br>• 720-1440 min: Daily monitoring |
| **Test Timeout** | Number | Yes | 60-600 seconds | Maximum time allowed for a single speed test |
| **Skip Certificate Verification** | Toggle | Yes | On/Off | Toggle SSL verification (CLI only) |

## Modifying Configuration

1. Go to **Settings** → **Devices & Services**
2. Find the LibreSpeed integration
3. Click **Configure**
4. Modify desired parameters
5. Click **Submit** to save changes

**Note**: Changes take effect on the next speed test. Running tests are not interrupted.

## Backend Selection Guide

### Native Python Backend

**Advantages:**
- Quick setup without downloads
- Lower resource usage
- Faster startup

**Limitations:**
- In development, may not be as accurate as CLI

### Official CLI Backend
**Advantages:**
- Official LibreSpeed implementation

**Limitations:**
- Requires binary download (~5MB)
- Platform-specific binaries

## Custom Server Configuration

### Setting Up a Custom Server

1. **Deploy LibreSpeed Server**:
   - Use Docker: `docker run -d -p 80:80 adolfintel/speedtest`
   - Or follow [manual installation](https://github.com/librespeed/speedtest)

2. **Configure in Home Assistant**:
   - Select "Custom Server" during setup
   - Enter full URL (e.g., `https://speedtest.yourdomain.com`)
   - Enable "Skip Certificate Verification" if using self-signed SSL

### Server Requirements
- LibreSpeed PHP backend (standard)
- LibreSpeed Rust backend (high-performance)
- Sufficient bandwidth for your connection speed

### Troubleshooting Custom Servers
- Verify URL is accessible from Home Assistant
- Check firewall rules allow HTTPS (port 443) if required
- Test in browser first
- Review server logs for errors

## Scheduling Strategies

### Conservative (Low Data Usage)
- Update Interval: 720-1440 minutes (12-24 hours)
- Best for: Metered connections, stable networks
- Data usage: ~50-100 MB/day

### Balanced (Default)
- Update Interval: 60-180 minutes
- Best for: Most users, regular monitoring
- Data usage: ~200-500 MB/day

### Aggressive (Frequent Monitoring)
- Update Interval: 30-60 minutes
- Best for: Troubleshooting, SLA monitoring
- Data usage: ~500-1000 MB/day

### Custom Scheduling with Automations

Disable automatic updates and use automations for precise control:

```yaml
automation:
  - alias: "Speed Test Schedule"
    trigger:
      - platform: time
        at: 
          - "06:00:00"
          - "12:00:00"
          - "18:00:00"
          - "22:00:00"
    action:
      - service: button.press
        entity_id: button.librespeed_run_speed_test
```

## Performance Tuning

### For Slow Systems
- Increase timeout to 300-600 seconds
- Reduce update interval to 180-360 minutes
- Disable automatic updates during peak hours

### For Fast Connections
- Keep default timeout (240 seconds)
- Select nearby servers manually
- Monitor CPU usage during tests

### Network Optimization
- Run tests when network is idle
- Avoid concurrent bandwidth-heavy tasks
- Use wired connection for consistency
