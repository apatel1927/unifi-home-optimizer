# UniFi Home Optimizer

Self-hosted UniFi Network monitoring and safe optimization dashboard designed for Unraid.

## v0.8.0

- Cleaner Overview, Wi-Fi, Auto Optimize, Clients, Switches, and History pages
- AP cards with live channel, width, client count, CPU, memory, and TX retry percentage
- Wi-Fi broadcast status: ALREADY_OPTIMIZED, NEEDS_ATTENTION, or PROTECTED
- Safe Auto Optimize for documented UniFi Wi-Fi Broadcast settings
- IOT_OPTIMIZED broadcasts are protected from automatic modification
- Persistent SQLite history in `/config`
- Docker images automatically published to GitHub Container Registry
- Unraid template included under `unraid/`

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
/mnt/user/appdata/unifi-home-optimizer -> /config
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
