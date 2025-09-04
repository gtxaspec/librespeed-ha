# Advanced Usage Guide

## Automation Blueprints

### Daily Speed Test Report

Save this as `blueprints/automation/librespeed_daily_report.yaml`:

```yaml
blueprint:
  name: LibreSpeed Daily Report
  description: Send daily speed test report via notification
  domain: automation
  input:
    test_time:
      name: Test Time
      description: When to run the daily test
      selector:
        time:
      default: "03:00:00"
    notify_device:
      name: Notification Device
      description: Device to send the report to
      selector:
        device:
          integration: mobile_app
    speed_threshold:
      name: Minimum Download Speed
      description: Alert if speed is below this value (Mbps)
      selector:
        number:
          min: 1
          max: 1000
          unit_of_measurement: Mbps
      default: 50

trigger:
  - platform: time
    at: !input test_time

action:
  - service: button.press
    target:
      entity_id: button.librespeed_run_speed_test
  
  - wait_for_trigger:
      - platform: state
        entity_id: binary_sensor.librespeed_speed_test_running
        from: "on"
        to: "off"
    timeout: "00:05:00"
  
  - variables:
      download: "{{ states('sensor.librespeed_download_speed') | float }}"
      upload: "{{ states('sensor.librespeed_upload_speed') | float }}"
      ping: "{{ states('sensor.librespeed_ping') | float }}"
      threshold: !input speed_threshold
  
  - service: notify.mobile_app_{{ device_id(!input notify_device) }}
    data:
      title: "Daily Speed Test Report"
      message: >
        📊 Speed Test Results:
        Download: {{ download }} Mbps {{ '⚠️' if download < threshold else '✅' }}
        Upload: {{ upload }} Mbps
        Ping: {{ ping }} ms
        Server: {{ states('sensor.librespeed_server_name') }}
      data:
        tag: "speed_test_report"
        group: "speed_test"
```

### Low Speed Alert

Save this as `blueprints/automation/librespeed_low_speed_alert.yaml`:

```yaml
blueprint:
  name: LibreSpeed Low Speed Alert
  description: Alert when internet speed drops below threshold
  domain: automation
  input:
    download_threshold:
      name: Download Speed Threshold
      description: Alert when download speed is below (Mbps)
      selector:
        number:
          min: 1
          max: 1000
          unit_of_measurement: Mbps
      default: 50
    upload_threshold:
      name: Upload Speed Threshold
      description: Alert when upload speed is below (Mbps)
      selector:
        number:
          min: 1
          max: 500
          unit_of_measurement: Mbps
      default: 10
    notify_device:
      name: Notification Device
      selector:
        device:
          integration: mobile_app

trigger:
  - platform: numeric_state
    entity_id: sensor.librespeed_download_speed
    below: !input download_threshold
  - platform: numeric_state
    entity_id: sensor.librespeed_upload_speed
    below: !input upload_threshold

action:
  - service: notify.mobile_app_{{ device_id(!input notify_device) }}
    data:
      title: "⚠️ Slow Internet Speed Detected"
      message: >
        {% if trigger.entity_id == 'sensor.librespeed_download_speed' %}
        Download speed is {{ states('sensor.librespeed_download_speed') }} Mbps
        (below {{ download_threshold }} Mbps threshold)
        {% else %}
        Upload speed is {{ states('sensor.librespeed_upload_speed') }} Mbps
        (below {{ upload_threshold }} Mbps threshold)
        {% endif %}
      data:
        tag: "speed_alert"
        importance: high
        channel: alerts
```

## Custom Dashboards

### Network Quality Monitoring Dashboard

Create a comprehensive dashboard for monitoring network quality:

```yaml
type: vertical-stack
cards:
  - type: custom:mini-graph-card
    name: Internet Speed History
    entities:
      - entity: sensor.librespeed_download_speed
        name: Download
        color: blue
      - entity: sensor.librespeed_upload_speed
        name: Upload
        color: green
    hours_to_show: 24
    points_per_hour: 4
    line_width: 3
    font_size: 75
    
  - type: horizontal-stack
    cards:
      - type: gauge
        entity: sensor.librespeed_download_speed
        name: Download
        max: 1000
        severity:
          green: 100
          yellow: 50
          red: 0
          
      - type: gauge
        entity: sensor.librespeed_upload_speed
        name: Upload
        max: 500
        severity:
          green: 50
          yellow: 25
          red: 0
          
      - type: gauge
        entity: sensor.librespeed_ping
        name: Latency
        max: 100
        severity:
          green: 0
          yellow: 50
          red: 100
          
  - type: entities
    title: Test Details
    entities:
      - entity: sensor.librespeed_jitter
        name: Jitter
      - entity: sensor.librespeed_server_name
        name: Server
      - entity: sensor.librespeed_last_test_time
        name: Last Test
      - entity: binary_sensor.librespeed_speed_test_running
        name: Test Status
      - entity: button.librespeed_run_speed_test
        name: Run Test Now
```

## ISP Performance Tracking

Track ISP performance against advertised speeds:

```yaml
sensor:
  - platform: template
    sensors:
      internet_performance_percentage:
        friendly_name: "ISP Performance"
        unit_of_measurement: "%"
        value_template: >
          {% set advertised = 500 %}  # Your advertised speed in Mbps
          {% set actual = states('sensor.librespeed_download_speed') | float %}
          {{ ((actual / advertised) * 100) | round(1) }}
        icon_template: >
          {% set perf = states('sensor.internet_performance_percentage') | float %}
          {% if perf >= 90 %}
            mdi:check-circle
          {% elif perf >= 70 %}
            mdi:alert-circle
          {% else %}
            mdi:close-circle
          {% endif %}

  - platform: statistics
    name: "Average Download Speed"
    entity_id: sensor.librespeed_download_speed
    state_characteristic: mean
    max_age:
      days: 7
```

## Integration with Other Services

### Discord Notification

```yaml
automation:
  - alias: "Speed Test Discord Report"
    trigger:
      - platform: state
        entity_id: binary_sensor.librespeed_speed_test_running
        from: "on"
        to: "off"
    action:
      - service: notify.discord
        data:
          message: |
            **Speed Test Results**
            :arrow_down: Download: {{ states('sensor.librespeed_download_speed') }} Mbps
            :arrow_up: Upload: {{ states('sensor.librespeed_upload_speed') }} Mbps
            :stopwatch: Ping: {{ states('sensor.librespeed_ping') }} ms
            :satellite: Server: {{ states('sensor.librespeed_server_name') }}
```

### Telegram Bot Integration

```yaml
automation:
  - alias: "Speed Test Telegram Report"
    trigger:
      - platform: state
        entity_id: binary_sensor.librespeed_speed_test_running
        from: "on"
        to: "off"
    action:
      - service: telegram_bot.send_message
        data:
          message: |
            *Speed Test Complete*
            ⬇️ Download: {{ states('sensor.librespeed_download_speed') }} Mbps
            ⬆️ Upload: {{ states('sensor.librespeed_upload_speed') }} Mbps
            ⏱ Ping: {{ states('sensor.librespeed_ping') }} ms
          parse_mode: markdown
```

## Advanced Automations

### Adaptive Testing Frequency

Run tests more frequently when performance is poor:

```yaml
automation:
  - alias: "Adaptive Speed Test Frequency"
    trigger:
      - platform: numeric_state
        entity_id: sensor.librespeed_download_speed
        below: 50
        for: "00:10:00"
    action:
      - service: button.press
        target:
          entity_id: button.librespeed_run_speed_test
      - delay: "00:30:00"
      - service: button.press
        target:
          entity_id: button.librespeed_run_speed_test
```

### Network Issue Detection

Detect and respond to network issues:

```yaml
automation:
  - alias: "Network Issue Detection"
    trigger:
      - platform: numeric_state
        entity_id: sensor.librespeed_ping
        above: 100
        for: "00:05:00"
    action:
      - service: notify.persistent_notification
        data:
          title: "Network Latency Warning"
          message: >
            High network latency detected: {{ states('sensor.librespeed_ping') }} ms
            This may affect streaming and gaming performance.
      - service: script.restart_network_equipment
```

## Data Export and Analysis

### Export to InfluxDB

```yaml
influxdb:
  host: localhost
  port: 8086
  database: home_assistant
  include:
    entities:
      - sensor.librespeed_download_speed
      - sensor.librespeed_upload_speed
      - sensor.librespeed_ping
      - sensor.librespeed_jitter
```

### Long-term Statistics

```yaml
recorder:
  purge_keep_days: 365
  include:
    entities:
      - sensor.librespeed_download_speed
      - sensor.librespeed_upload_speed
      - sensor.librespeed_ping
```

## Custom Scripts

### Multi-Server Test

Test against multiple servers for comparison:

```yaml
script:
  multi_server_test:
    sequence:
      - service: librespeed.set_server
        data:
          server_id: 1
      - service: button.press
        entity_id: button.librespeed_run_speed_test
      - delay: "00:02:00"
      - service: librespeed.set_server
        data:
          server_id: 2
      - service: button.press
        entity_id: button.librespeed_run_speed_test
```