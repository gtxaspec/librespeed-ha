# Troubleshooting Guide

## Common Issues

### Speed test button is disabled
**Symptom**: The "Manual Speed Test" button appears grayed out or unavailable.

**Cause**: A speed test is currently running. The integration prevents concurrent tests to ensure accurate results.

**Solution**: 
- Wait for the current test to complete (check `binary_sensor.librespeed_speed_test_running`)
- Check logs for any errors if the test seems stuck
- Restart the integration if the test has been running for more than 5 minutes

### Low speed results with native backend
**Symptom**: Speed test results are significantly lower than expected (e.g., 50-100 Mbps when expecting 500+ Mbps).

**Solutions**:
1. **Switch to CLI backend** (recommended for high-speed connections):
   - Navigate to Settings → Devices & Services → LibreSpeed → Configure
   - Change Backend Type to "Official CLI"
   - Save and wait for automatic restart
   
2. **Select a different server**:
   - Some servers may be overloaded or geographically distant
   - Try "Automatic" selection or manually choose a closer server

3. **Check network conditions**:
   - Ensure no other devices are consuming bandwidth
   - Test at different times of day

### Custom server not working
**Symptom**: Tests fail when using a custom LibreSpeed server.

**Diagnostic steps**:
1. **Verify server URL**:
   - Ensure URL is complete (e.g., `https://speedtest.example.com`)
   - Test the URL in a browser - you should see the LibreSpeed interface
   
2. **SSL Certificate issues**:
   - If using self-signed certificates, enable "Skip Certificate Verification"
   - Check logs for SSL-related errors
   
3. **Server compatibility**:
   - Ensure server is running LibreSpeed (PHP or Rust backend)
   - Check server logs for any access errors

### Tests not running automatically
**Symptom**: Scheduled speed tests are not executing at the configured interval.

**Solutions**:
1. **Verify configuration**:
   - Check that "Automatic Updates" is enabled
   - Confirm update interval is set (minimum 30 minutes)
   
2. **Check Home Assistant logs**:
   ```
   grep librespeed home-assistant.log
   ```
   
3. **Review automation conflicts**:
   - Ensure no other automations are interfering
   - Check if Home Assistant is in maintenance mode

## Error Messages and Solutions

### "Speed test timed out after multiple attempts"
**Cause**: Network connectivity issues or server unavailability.

**Solutions**:
- Check internet connectivity
- Try a different server
- Increase timeout in configuration
- The integration automatically retries 3 times with exponential backoff

### "Network error: Connection refused"
**Cause**: Firewall blocking connections or server is down.

**Solutions**:
- Check firewall rules for outbound HTTPS (port 443)
- Verify the server is operational
- Try the automatic server selection

### "SSL: CERTIFICATE_VERIFY_FAILED"
**Cause**: Custom server using self-signed or expired certificate.

**Solutions**:
- Enable "Skip Certificate Verification" in configuration
- Update server certificate
- Use a Let's Encrypt certificate on your server

### "Speed test already in progress"
**Cause**: Previous test didn't complete properly.

**Solutions**:
- Wait 2-3 minutes for timeout
- Restart the integration if stuck
- Check logs for underlying errors

## Advanced Debugging

### Enable debug logging
Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.librespeed: debug
```

### Check integration state
In Developer Tools → States, search for `librespeed` entities:
- `binary_sensor.librespeed_speed_test_running` - Should be `off` when idle
- `sensor.librespeed_last_test_time` - Shows last successful test

### Manual CLI testing
Test the CLI backend manually:
```bash
# From Home Assistant container/environment
./custom_components/librespeed/bin/speedtest-cli --json
```

## Performance Optimization

### For connections > 500 Mbps
- Use CLI backend for best performance
- Ensure Home Assistant has sufficient CPU resources
- Consider running tests during off-peak hours

### Reducing resource usage
- Increase update interval (e.g., every 6-12 hours)
- Disable automatic updates and use automations for specific times
- Use server selection instead of automatic to avoid latency tests

## Getting Help

If you're still experiencing issues:
1. Enable debug logging (see above)
2. Collect relevant log entries
3. Check for existing issues on [GitHub](https://github.com/gtxaspec/librespeed-ha/issues)
4. Create a new issue with:
   - Your configuration (without sensitive data)
   - Debug logs
   - Expected vs actual behavior
   - Home Assistant version
   - Integration version