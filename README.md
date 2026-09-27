# UniFi Home Optimizer

Self-hosted UniFi Network monitoring and safe optimization dashboard designed for Unraid.

## v0.9.0

- Internet Health page with observed online/offline status, 24-hour availability, outage count, latency, gateway uptime, and live gateway RX/TX throughput
- Throughput and latency history charts
- Overview Internet status card
- Retry health now uses a 15-minute rolling average after enough samples are available, instead of overreacting to one 60-second spike
- Retry guidance: under 8% good, 8–15% watch, 15–25% elevated, 25%+ high
- Roaming Analyzer with current AP, 24-hour AP-change counts, and roaming history
- Custom Unraid/Docker icon and responsive dashboard
- Safe Auto Optimize for documented STANDARD Wi-Fi settings; IOT_OPTIMIZED remains protected
- Persistent SQLite history and automatic schema migrations

## Internet monitoring

Internet availability is probed from the UniFi Home Optimizer container on the Unraid server. Gateway uptime and RX/TX rates come from the UDM statistics exposed by the UniFi Network API. Gateway uptime is not the same thing as ISP-session uptime.

## Install on Unraid

Use:

```
ghcr.io/apatel1927/unifi-home-optimizer:latest
```

Required variables:

```
UNIFI_URL=https://192.168.1.1
UNIFI_API_KEY=<your key>
POLL_INTERVAL_SECONDS=60
RETENTION_DAYS=30
```

Persistent storage:

```
/mnt/user/appdata/unifi-optimizer -> /config
```

Web UI:

```
http://UNRAID-IP:8090
```

## Safe optimization policy

Automatic changes are intentionally limited to settings documented by the official UniFi Network API.

Currently automatic:
- Band Steering on eligible STANDARD Wi-Fi broadcasts
- BSS Transition on eligible STANDARD Wi-Fi broadcasts

Protected / monitor-only:
- IOT_OPTIMIZED broadcasts
- AP channel
- channel width
- transmit power
- Minimum RSSI
- SSID credentials
- VLAN configuration

## Security

Never commit your UniFi API key. Store it only in the Unraid container environment.
