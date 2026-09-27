# UniFi Home Optimizer

Self-hosted UniFi Network monitoring and safe optimization dashboard designed for Unraid.

## v0.10.0

- Modernized dashboard visual design with improved navigation, cards, tables, responsiveness and status hierarchy
- Automatic detection of manual radio changes for active before/after tests
- Live elapsed / remaining test timer with progress bar
- 24-hour network health score history chart
- Historical per-AP client-load baselines for smarter load findings
- System & Diagnostics page with poll status, database size, retention, monitor health and last errors
- Optional local browser alerts for Internet outages, AP outages and completed optimization tests
- Completed RF tests are written into Optimization History
- Experimental Auto RF readiness panel remains read-only until private UniFi authentication and U7 radio payloads are verified
- New Channel Planner page for 2.4, 5 and 6 GHz
- Detects proven channel/block conflicts between your own APs
- Uses current radio settings, client load and retry trends to recommend KEEP or CONSIDER CHANGE
- 2.4 GHz planner targets 20 MHz and channels 1/6/11
- 5 GHz planner tries to spread APs across distinct 80 MHz blocks, including DFS options when needed
- 6 GHz planner flags overlapping wide blocks and can suggest reducing 320 MHz to 160 MHz when reuse or retry trends justify it
- Safe advisory only: no undocumented radio writes are performed
- Before / after optimization tests for Channel Planner recommendations
- Capture the 15-minute retry baseline before a manual radio change
- Mark the change applied, monitor for at least 60 minutes, and classify the outcome as IMPROVED, NO_CHANGE, or WORSE
- Internet Health page with availability, outages, latency, gateway uptime and throughput history
- Retry health uses rolling averages instead of single-sample spikes
- Roaming Analyzer with current AP and AP-change history

## Channel Planner limitations

The official UniFi Network API used by this app does not expose a documented neighboring-network RF scan or supported per-AP radio channel/width/power write endpoint. The planner therefore analyzes your own AP configuration and measured retry trends, and keeps channel changes advisory-only.

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
