# UniFi Home Optimizer

Self-hosted UniFi Network monitoring and safe optimization dashboard designed for Unraid.

## v0.22.1

- Mobile navigation now uses a persistent Menu button and slide-out drawer instead of a long horizontally scrolling tab strip
- Selecting a page closes the drawer, updates the current-page label, and returns the view to the top for faster tab switching on phones
- RF Environment now defaults to a compact neighbor channel summary instead of rendering the full neighboring-BSS list inline
- Neighbor observations are deduplicated by BSSID/channel and grouped by band/channel with unique BSS count, strongest observed RSSI, and a clearly labeled relative BSS-pressure heuristic
- The raw neighbor list remains available in a collapsed expandable section for detailed troubleshooting

- Passive RF Environment page collects read-only classic UniFi radio telemetry every 5 minutes when available
- RF telemetry includes current-channel utilization, self RX/TX airtime, estimated external busy time, noise floor, TX power, retry rate, client count, and neighboring BSS observations exposed by the controller
- Channel Planner cards now display passive RF evidence alongside retries and own-AP overlap; passive current-channel data is treated as supporting evidence, not proof that an unscanned candidate is cleaner
- Active/off-channel RF scanning remains disabled until the exact controller/AP command is separately verified because undocumented scans may interrupt clients
- Wired / Switches now supports persistent expected-link-speed acknowledgments for known 100 Mbps / 1G / 2.5G / 5G / 10G / faster endpoints
- Expected-speed acknowledgments follow the endpoint MAC when known, or the switch port when no endpoint identity is available
- AI Approval Queue can generate constrained proposals and requires explicit user approval before any whitelisted action executes
- Executable AI actions are limited to creating a validated RF A/B/A test or running the existing narrow Auto Optimize path; firewall/VLAN/DHCP/MLO/client-isolation items remain review-only
- Approved RF proposals are revalidated against the current Channel Planner and stored RF history before a test is created
- RF environment data and the AI approval queue are included in sanitized support exports

- Traffic page now includes a manual Sample now control and safe collector diagnostics
- Traffic diagnostics report station/DPI structure and counter-field coverage without exposing credentials or packet contents
- Per-client traffic collection supports additional UniFi counter field names and falls back to station DPI cumulative counters when /stat/sta omits byte totals
- Cancelled RF A/B/A tests now have a Retest cancelled change action that creates a fresh test instead of leaving the old cancelled record as a dead end
- Retesting refuses to create a misleading no-op when the AP is still on the cancelled B setting and tells the user to restore A first
- Channel Planner now explains the RF revalidation policy: one variable at a time, fresh baseline, B observation, rollback verification, and prior confirmed-worse results retained as evidence

- AI wording now distinguishes validated private/classic Auto RF from the separate official API limitations
- REVIEW-only findings such as DHCP guarding, disabled policies, client isolation and MLO are no longer promoted into enable/disable recommendations without stronger evidence
- Small wired state/speed-change counts with zero current error/drop deltas are treated as watch items unless they recur or have corroborating evidence
- AI defer messages now remain visible instead of flashing away
- When an RF A/B/A test blocks AI analysis, the Export / AI page shows the exact AP, band and test status causing the deferral
- Fixes a short AI launch-state race so the button remains in STARTING/RUNNING state from click through completion
- AI advisor now receives current Auto RF / Auto Optimize state and full stored RF test history
- Prevents the advisor from treating official-API radio-write limitations as proof that validated private Auto RF is unavailable
- Uses completed RF A/B/A history as stronger evidence than generic planner recommendations and avoids casually repeating previously worse tests
- Export / AI tab creates a one-click sanitized support bundle for sharing with ChatGPT
- Export formats include a ZIP with individual JSON sections, a single JSON file, and a compact copy-to-clipboard text summary
- Export recursively redacts passwords, API keys, tokens, secrets and credentials while retaining useful local troubleshooting identifiers
- Optional embedded OpenAI advisor uses the Responses API with an API key supplied only through the Unraid container environment
- Manual AI analysis plus optional scheduled 1/3/6/12/24-hour advisory reviews
- AI analysis is advisory-only and pauses during active RF A/B/A tests; it cannot directly change firewall, VLAN or Wi-Fi settings
- Existing deterministic Auto RF and Auto Optimize remain the execution layer for already-validated low-risk automation
- AI analysis history is stored locally in SQLite for the configured retention period
- Automatic speed-test scheduler is explicitly started with the application
- Fixes wired false positives from lifetime error/drop counters by scoring only counter growth between monitor samples
- Keeps cumulative error/drop totals visible while showing a separate recent-delta line
- Fixes PoE false faults: poe_good=false alone no longer means FAULT when a port simply is not delivering PoE
- Merges official port metadata with classic telemetry so port capability/name can be filled when available
- Expands expected 100 Mbps endpoint recognition for Lutron hubs, bridges, media/streaming and smart-home devices
- Deep Wired & Switch Audit maps active switch ports to connected UniFi devices and wired clients when classic telemetry exposes the relationship
- Shows negotiated link speed, port capability, PoE state/watts, live RX/TX rate, errors/drops, VLAN/profile and 24-hour state/speed changes
- Learns wired link state changes over time without storing a high-volume per-minute port history
- Distinguishes likely 100 Mbps IoT/camera endpoints from suspicious 100 Mbps infrastructure links so normal low-speed devices do not unfairly lower the wired score
- Network Audit now uses the deep wired score instead of treating every 100 Mbps endpoint as a problem
- Topology links can show parent switch port, negotiated speed and PoE power when UniFi exposes those details
- Fixes the topology switch-node CSS collision that caused gray slider-like bars to appear beside switch branches
- Fixes the nearby-server button event handler so Load nearby servers actually requests and populates the Ookla list
- Hardens parsing of official Ookla -L output and returns visible diagnostics on lookup/parse failures
- Fixes false firewall warnings where zone-scoped ALLOW policies were incorrectly treated as unrestricted any-to-any rules
- Official Ookla Speedtest CLI replaces the legacy Python speedtest client
- Nearby server picker lets you keep Ookla automatic selection or lock tests to a specific nearby server ID
- Completed speed tests now store server provider, location, country, server ID, host, jitter and packet loss when available
- Speed Test page shows jitter and packet loss alongside ping/download/upload
- Read-only Network Audit page checks security, firewall, segmentation, Wi-Fi, wired links, WAN, DHCP/DNS and device health
- Category scorecards for Security, Firewall, Segmentation, Wi-Fi, Wired, WAN, DHCP/DNS and Device Health
- Findings use PASS / REVIEW / WARNING / CRITICAL so context-dependent settings are not mislabeled as failures
- Audit checks include duplicate active IPs, offline devices, firmware availability, high CPU/memory, Wi-Fi security modes, 6 GHz security consistency, MLO readiness, BSS Transition, Band Steering, DHCP guarding, broad firewall allows, disabled policies/rules, VLAN presence and obvious link-speed mismatches
- Configuration inventory summarizes networks, SSIDs, firewall/ACL objects, WAN interfaces and DNS policies
- Audit is intentionally read-only; firewall/VLAN/security changes are never applied automatically
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

Speed tests use the official Ookla Speedtest CLI. Automatic mode lets Ookla choose a nearby server using its native selection logic. The Speed Test page can also list nearby Ookla servers and lock all tests to a selected server ID, which is useful when ISP IP geolocation causes a bad automatic choice. Completed results store the exact server/provider/location/country/ID plus ping, jitter and packet loss when returned.


## Network audit

The Network Audit page performs a read-only review of the current UniFi configuration and health data. Findings are deliberately separated into PASS, REVIEW, WARNING, and CRITICAL. REVIEW means the setting is context-dependent and should be confirmed rather than automatically changed.

The first audit release checks device health, firmware availability, duplicate active IPs, VLAN/network inventory, DHCP guarding, Wi-Fi security, 6 GHz consistency, MLO readiness, BSS Transition, Band Steering, client isolation context, radio-width sanity, obvious wired negotiation mismatches, firewall/ACL inventory, broad allow policies, WAN interfaces, gateway QoS throughput risk, and DNS policy inventory.

Future audit releases can add port-forward/UPnP exposure, deeper switch error/PoE analysis, remote-access posture, VPN posture and change auditing as those data sources are verified.


## Wired and switch audit

The Wired / Switches page combines the supported Integration API with read-only classic device/client telemetry when local private credentials are configured. Active ports are mapped to endpoints where UniFi exposes switch MAC/port relationships. The page shows negotiated link speed, port capability, PoE, live traffic, errors/drops, VLAN/profile data and 24-hour state/speed changes.

The wired score is intentionally endpoint-aware. A 100 Mbps link is not automatically a fault: likely IoT/camera/smart-home endpoints can be classified as expected low-speed links, while 100 Mbps infrastructure links, explicit PoE faults and repeated link flaps receive stronger attention. Error/drop totals are displayed as cumulative controller counters, but scoring uses only increases observed between monitor samples so old lifetime counters do not create false warnings. Link-change history begins learning after v0.19.0 is installed.


## Export and AI advisor

The Export / AI tab can generate a support bundle for sharing with ChatGPT. The ZIP contains a compact README plus sanitized JSON for the current network audit, wired audit, WAN quality, traffic summary, speed tests, network snapshot and recent optimizer log. A single JSON export and a compact clipboard summary are also available.

Sensitive configuration keys containing password, passphrase, secret, PSK, token, API key, private key, credentials, authorization or cookies are recursively replaced with [REDACTED]. Local device names, MAC addresses and private IP addresses are intentionally retained because they are useful when troubleshooting a home network.

Embedded AI is optional. Configure these Unraid environment variables only if you want the optimizer to call the OpenAI API:

```
OPENAI_API_KEY=<your OpenAI API key>
OPENAI_MODEL=gpt-5.6-luna
```

The API key is read from the container environment, is never returned by the app and is excluded from support exports. The AI advisor can run manually or on a 1/3/6/12/24-hour schedule. AI is advisory-only: it summarizes current health, proposes safe automations and identifies approval-required changes. Existing deterministic automation remains responsible for actual configuration changes.


## RF environment

The RF Environment page uses read-only classic UniFi telemetry because the supplied official Network Integration API documentation exposes device/radio statistics but does not document a neighboring-network or active RF scan command. When the controller exposes `radio_table_stats`, the app records current-channel utilization, self RX/TX airtime, external busy time, noise, TX power, retries and client counts. It also attempts a read-only neighboring/rogue AP inventory through the classic API.

These values are used as supporting evidence in Channel Planner and AI analysis. They describe the current RF environment; they do not prove that an unscanned candidate channel is better. Active spectrum scanning stays disabled until a controller-specific command is separately verified.

## Expected wired link speeds

On Wired / Switches, a confirmed endpoint can be assigned an expected negotiated speed. Matching links stop lowering the wired score, but an acknowledged endpoint can still warn if it drops below the expected speed, accumulates new errors/drops, flaps or develops a PoE fault.

## AI approval queue

The AI Approval Queue is deliberately constrained. AI can propose:
- `RF_ABA_TEST` for a current, still-valid Channel Planner change
- `AUTO_OPTIMIZE_RUN` only when an eligible STANDARD SSID actually needs Band Steering or BSS Transition enabled
- `REVIEW_SETTING` for everything else

Nothing executes until the user presses Approve. Review-only proposals never change the network. RF approvals are revalidated against the live radio state, current planner recommendation, active-test state and stored RF history before creating a fresh A/B/A test.
