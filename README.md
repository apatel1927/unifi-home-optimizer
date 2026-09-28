# UniFi Home Optimizer

Self-hosted UniFi Network monitoring and safe optimization dashboard designed for Unraid.

## v0.17.0

- Live Network Topology page builds the current Internet -> UDM -> switch/AP -> client tree from UniFi uplink relationships
- Topology shows device state, model, IP, AP radio channels/widths, client counts, and downstream device counts
- Client nodes show IP, type, VLAN, network, and SSID when available
- Topology filters support client type, VLAN, network, show/hide clients, and compact client display
- Devices without a trustworthy live parent are shown separately instead of having a path guessed
- Speed Test page now explains automatic best-server selection and continues to store the exact server/sponsor/location/distance used by each completed test
- WAN Quality page with continuous multi-target latency, packet-loss, jitter, gateway latency, and DNS reliability monitoring
- Probes Cloudflare, Google, and Quad9 plus the local UDM gateway
- ICMP samples run every 60 seconds with three probes per target; DNS samples run every 5 minutes
- DNS monitoring compares the system resolver with Cloudflare and Google
- Adds 1 hour / 24 hour / 7 day / 30 day WAN-quality ranges
- Stores WAN probe history in SQLite using the existing retention policy
- Includes a WAN quality score derived from reachability, latency, jitter, and DNS reliability
- Separates local gateway latency from external Internet latency to make LAN-vs-WAN problems easier to distinguish
- Traffic Analytics page with live per-client RX/TX rates, historical usage, AP/uplink, VLAN, and network breakdowns
- Stores traffic counter deltas every 5 minutes so usage history survives dashboard reloads and container restarts
- Adds 1 hour / 24 hour / 7 day / 30 day traffic ranges
- Tracks top clients, top VLANs, top networks, and top AP/uplink paths by data usage
- Integrates UniFi classic DPI read-only endpoints for application/category traffic history
- Shows top applications and application categories when UniFi DPI identifies them
- Traffic client table supports search plus AP/uplink, VLAN, network, and usage sorting filters
- Exact URLs and every encrypted destination are deliberately not inferred; unknown/private traffic remains unknown
- Automatic Internet speed testing from the Unraid server with persistent download, upload, and ping history
- Dedicated Speed Test page with Run Now, automatic enable/disable, and 1/3/6/12/24-hour intervals
- Default automatic interval is 6 hours
- 30-day speed and ping charts plus detailed test history including server and duration
- Automatic speed tests are deferred while an RF A/B/A test is active to avoid adding traffic during RF measurements
- Failed speed tests are recorded with the error for troubleshooting
- Client page now supports selectable filters for access point/uplink, connection type, VLAN, and network
- Client list can be grouped by access point/uplink, VLAN, network, or connection type
- Client sorting includes IP low-to-high/high-to-low, name, VLAN, network, access point, and connection type
- Client inventory now shows MAC address, VLAN, network/SSID, connected-through device, switch port when available, and uplink model
- Matching/wireless/wired/VLAN summary counts update live with filters
- VLAN/SSID enrichment uses read-only classic client station data when private credentials are configured; unsupported/missing values safely display as Unknown
- Topology-aware A/B/A scoring now evaluates proven own-AP conflict removal alongside retry performance
- Adds IMPROVED_TOPOLOGY and WORSE_TOPOLOGY outcomes
- Near-zero retry baselines no longer use misleading percentage comparisons; low retry rates use absolute-point thresholds
- Auto RF can keep/re-apply a proposed channel when it removes an own-AP conflict without materially worsening retries
- RF test cards show own-AP conflict count for A -> B
- Experimental Auto RF can automate A/B/A channel and width changes after an explicit write-path validation
- Adds a separate cookie/CSRF classic UniFi API client for the per-AP radio controls missing from the supported Integration API
- Staged safety flow: credentials -> read-only radio_table discovery -> explicit no-op write validation -> Auto RF enable
- Auto RF applies the B setting, rolls back to A for verification, and re-applies B when the result is IMPROVED_CONFIRMED or IMPROVED_TOPOLOGY
- Any private API write failure disables Auto RF automatically
- Private API credentials stay in Unraid environment variables and are never stored in the SQLite database
- New optional Unraid variables: UNIFI_PRIVATE_USERNAME, UNIFI_PRIVATE_PASSWORD, and UNIFI_SITE_NAME
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

The official UniFi Network Integration API used by this app does not expose a documented neighboring-network RF scan or supported per-AP radio channel/width/power write endpoint. Experimental Auto RF therefore uses UniFi's local classic API for channel/width writes only after a separate local-admin login, read-only discovery, and an explicit no-op write validation. The private path is undocumented and may change between UniFi releases.

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

Protected / monitor-only by default:
- IOT_OPTIMIZED broadcasts
- AP channel and channel width unless Experimental Auto RF has been explicitly validated and enabled
- transmit power
- Minimum RSSI
- SSID credentials
- VLAN configuration

## Security

Never commit your UniFi API key. Store it only in the Unraid container environment.


## Speed testing

Automatic speed testing is enabled by default and runs every 6 hours. The interval can be changed from the Speed Test page without editing the container. Tests originate from the Unraid server, so they measure the server-to-Internet path rather than Wi-Fi performance of an individual client.

A full speed test can transfer a meaningful amount of data, especially on fast Internet connections. Increase the interval if you want to reduce test traffic.


## Traffic analytics

Traffic history uses read-only client counters from UniFi's classic local API and stores five-minute deltas in SQLite. The Traffic page can summarize one hour, 24 hours, 7 days, or 30 days and break usage down by client, VLAN/network, and AP/uplink.

Application visibility uses UniFi DPI through the classic stat/sitedpi endpoint when available. DPI can classify many applications and categories, but it does not expose or reliably identify every website, hostname, or encrypted remote destination. The dashboard does not guess when UniFi cannot identify traffic.

RX/TX labels follow the counters reported by the UniFi controller. They are kept as controller-side RX/TX rather than silently relabeled as download/upload because direction semantics can vary by interface and controller context.


## WAN quality monitoring

WAN Quality is measured independently from the existing HTTPS connectivity probe and scheduled speed tests. The app sends small ICMP probe sets to Cloudflare (1.1.1.1), Google (8.8.8.8), and Quad9 (9.9.9.9), plus the local UDM gateway. It stores packet loss, min/average/max RTT, and jitter.

DNS quality is sampled separately using the system resolver, Cloudflare DNS, and Google DNS. The dashboard stores success rate and DNS response latency.

The WAN quality score is an app-level summary for trend spotting, not an ISP SLA certification. Raw latency, packet-loss, jitter, and DNS metrics remain visible alongside it.


## Network topology

The Topology page uses device uplink relationships returned by UniFi to build a live logical tree. Connected clients are placed under the AP or switch reported as their current uplink. The app does not invent missing links; unresolved devices are shown separately.

## Speed test server selection

Each speed test creates a Speedtest client and calls get_best_server before download/upload testing. The selected Speedtest.net-compatible server can therefore change between runs. The completed result stores the exact server name/location, sponsor, server ID, distance, and ping when returned by the test service.
