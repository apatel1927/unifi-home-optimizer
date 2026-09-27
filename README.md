# UniFi Home Optimizer

Self-hosted UniFi Network monitoring and safe optimization dashboard designed for Unraid.

## v0.11.1

- Cancel button is available on every active RF test phase
- Invalid A/B/A tests with identical original and proposed settings are automatically closed as INVALID_NO_CHANGE
- Diagnostic-only retry findings now show INVESTIGATE and cannot create a fake A/B/A test
- RF tests are only offered when channel or width will actually change
- Radio configuration changes are recorded so already-applied changes can be recovered into A/B/A tests
- Channel Planner includes a Recover applied change workflow with a manual fallback for changes made before config-history tracking was enabled
- A/B/A RF verification for channel and width changes
- Captures a 60-minute original-setting baseline before a test
- Ignores the first 15 minutes after a change as a settling period
- Measures the new setting across a 60-minute observation window
- Requires rollback to the original setting and verifies it with another settling + 60-minute observation window
- Uses sample counts and AP client load to avoid false conclusions when traffic/load changes materially
- Final verdicts distinguish IMPROVED_CONFIRMED, WORSE_CONFIRMED, NO_MEANINGFUL_CHANGE, and INCONCLUSIVE conditions
- Coordinated RF target plan shows the intended end-state across all APs before individual changes
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
- New tests use a 60-minute baseline plus A/B/A rollback verification instead of a single 15-minute comparison
- Manual radio changes and rollbacks are auto-detected from the live UniFi configuration when possible
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
