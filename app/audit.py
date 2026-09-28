from collections import defaultdict


SEVERITY_WEIGHT={"CRITICAL":30,"WARNING":12,"REVIEW":4,"PASS":0}


def _add(findings, status, category, title, detail, target=None, recommendation=None, evidence=None):
    findings.append({
        "status":status,
        "category":category,
        "title":title,
        "detail":detail,
        "target":target,
        "recommendation":recommendation,
        "evidence":evidence or {},
    })


def _security_type(wifi):
    sec=wifi.get("securityConfiguration") or {}
    return str(sec.get("type") or "").upper()


def _wifi_network_name(wifi):
    return wifi.get("name") or "WiFi"


def _action_type(policy):
    action=policy.get("action")
    if isinstance(action,dict):
        return str(action.get("type") or "").upper()
    return str(action or "").upper()


def _empty_filter(side):
    if not isinstance(side,dict):
        return True
    traffic=side.get("trafficFilter")
    return traffic in (None,{}) and not any(
        side.get(k) not in (None,{},[], "")
        for k in ("zoneId","zoneIds","networkId","networkIds","ipAddress","ipAddresses","port","ports")
    )


def _score(findings, category=None):
    rows=[x for x in findings if category is None or x.get("category")==category]
    score=100
    for row in rows:
        score-=SEVERITY_WEIGHT.get(row.get("status"),0)
    return max(0,min(100,score))


def build_network_audit(snapshot, api):
    findings=[]
    site=snapshot.get("site") or {}
    site_id=site.get("id")
    devices=snapshot.get("devices") or []
    clients=snapshot.get("clients") or []
    networks=snapshot.get("networks") or []
    wifi=snapshot.get("wifiBroadcasts") or []

    # Additional official read-only inventories.
    firewall_zones=api.firewall_zones(site_id) if site_id else []
    firewall_policies=api.firewall_policies(site_id) if site_id else []
    acl_rules=api.acl_rules(site_id) if site_id else []
    dns_policies=api.dns_policies(site_id) if site_id else []
    wans=api.wan_interfaces(site_id) if site_id else []

    # Device health / software / basic stability.
    offline=[d for d in devices if d.get("state")!="ONLINE"]
    if offline:
        for d in offline:
            _add(findings,"CRITICAL","DEVICE_HEALTH","UniFi device is offline",
                 "The device is not currently ONLINE.",
                 d.get("name") or d.get("model"),
                 "Check power, uplink, PoE, cabling and controller reachability.")
    else:
        _add(findings,"PASS","DEVICE_HEALTH","All UniFi devices online",
             f"{len(devices)} adopted UniFi devices are reporting ONLINE.")

    upgradable=[d for d in devices if d.get("firmwareUpdatable") is True]
    if upgradable:
        for d in upgradable:
            _add(findings,"REVIEW","DEVICE_HEALTH","Firmware update available",
                 f"{d.get('firmwareVersion') or 'Current version unknown'} is installed and UniFi reports an update is available.",
                 d.get("name") or d.get("model"),
                 "Review release notes and schedule a controlled firmware update.")
    else:
        _add(findings,"PASS","DEVICE_HEALTH","No pending device firmware updates reported",
             "UniFi did not report firmwareUpdatable=true for any adopted device.")

    for d in devices:
        stats=d.get("statistics") or {}
        cpu=stats.get("cpuUtilizationPct")
        mem=stats.get("memoryUtilizationPct")
        if isinstance(cpu,(int,float)) and cpu>=90:
            _add(findings,"WARNING","DEVICE_HEALTH","High device CPU utilization",
                 f"CPU utilization is {cpu:.1f}%.",d.get("name"),
                 "Check device workload, traffic and firmware if this persists.")
        elif isinstance(cpu,(int,float)) and cpu>=75:
            _add(findings,"REVIEW","DEVICE_HEALTH","Elevated device CPU utilization",
                 f"CPU utilization is {cpu:.1f}%.",d.get("name"),
                 "Watch for persistence or correlation with latency.")
        if isinstance(mem,(int,float)) and mem>=90:
            _add(findings,"WARNING","DEVICE_HEALTH","High device memory utilization",
                 f"Memory utilization is {mem:.1f}%.",d.get("name"),
                 "Check firmware and device workload if this persists.")

    # Duplicate IP detection.
    ip_map=defaultdict(list)
    for c in clients:
        ip=c.get("ipAddress")
        if ip:
            ip_map[str(ip)].append(c)
    dupes={ip:rows for ip,rows in ip_map.items() if len(rows)>1}
    if dupes:
        for ip,rows in dupes.items():
            _add(findings,"WARNING","DHCP_DNS","Duplicate active client IP detected",
                 f"{len(rows)} connected clients report {ip}.",
                 ip,
                 "Verify static IPs, DHCP reservations and rogue DHCP sources.",
                 {"clients":[x.get("name") or x.get("macAddress") for x in rows]})
    else:
        _add(findings,"PASS","DHCP_DNS","No duplicate active client IPs detected",
             f"{len(ip_map)} active client addresses were checked.")

    # Networks and DHCP guarding.
    if not networks:
        _add(findings,"WARNING","SEGMENTATION","No network inventory returned",
             "The Network API did not return any configured networks.")
    else:
        non_default=[n for n in networks if not n.get("default") and n.get("vlanId") not in (None,1)]
        if non_default:
            _add(findings,"PASS","SEGMENTATION","Multiple network segments detected",
                 f"{len(non_default)} non-default VLAN/network segment(s) are configured.")
        else:
            _add(findings,"REVIEW","SEGMENTATION","Single/default network design",
                 "No non-default VLAN/network segments were found.",
                 recommendation="If IoT, cameras, guests or servers have different trust levels, consider separate VLANs and firewall policy.")

        for n in networks:
            guard=n.get("dhcpGuarding")
            name=n.get("name") or f"VLAN {n.get('vlanId')}"
            if guard:
                trusted=guard.get("trustedDhcpServerIpAddresses") or []
                _add(findings,"PASS","DHCP_DNS","DHCP guarding configured",
                     f"DHCP guarding is present with {len(trusted)} trusted DHCP server address(es).",name)
            else:
                _add(findings,"REVIEW","DHCP_DNS","DHCP guarding not configured",
                     "This network does not report DHCP guarding.",name,
                     "Consider DHCP guarding on segments where rogue DHCP protection is useful.")

    # Wi-Fi security / compatibility / stability.
    if not wifi:
        _add(findings,"WARNING","WIFI","No Wi-Fi broadcast inventory returned",
             "The API did not return any configured Wi-Fi broadcasts.")
    for w in wifi:
        name=_wifi_network_name(w)
        kind=str(w.get("type") or "STANDARD")
        sec=_security_type(w)
        bands=w.get("broadcastingFrequenciesGHz") or []
        has6=6 in bands or 6.0 in bands
        mlo=w.get("mloEnabled") is True

        if "OPEN" in sec or sec in ("NONE",""):
            _add(findings,"CRITICAL","SECURITY","Open or unverified Wi-Fi security",
                 f"Security type is {sec or 'not reported'}.",name,
                 "Verify that this SSID is intentionally open/OWE or move it to an authenticated security mode.")
        elif "WPA3" in sec:
            _add(findings,"PASS","SECURITY","Modern Wi-Fi security",
                 f"Security type is {sec}.",name)
        elif "WPA2" in sec:
            status="PASS" if kind=="IOT_OPTIMIZED" else "REVIEW"
            _add(findings,status,"SECURITY","WPA2 compatibility Wi-Fi",
                 f"Security type is {sec}.",name,
                 "Keep WPA2 only where client compatibility requires it; prefer WPA2/WPA3 or WPA3 on modern-client SSIDs.")
        else:
            _add(findings,"REVIEW","SECURITY","Review Wi-Fi security mode",
                 f"Security type is {sec or 'not reported'}.",name)

        if has6 and "WPA3" not in sec:
            _add(findings,"WARNING","WIFI","6 GHz security compatibility review",
                 "This SSID includes 6 GHz but its reported security type does not contain WPA3.",name,
                 "Verify the UniFi 6 GHz security/PMF configuration.")

        if len(bands)>=2 and w.get("bandSteeringEnabled") is False:
            _add(findings,"REVIEW","WIFI","Band Steering is off",
                 f"SSID uses {len(bands)} bands but Band Steering is disabled.",name,
                 "Evaluate whether enabling Band Steering improves modern-client placement.")
        elif len(bands)>=2:
            _add(findings,"PASS","WIFI","Band Steering enabled",
                 "Multi-band SSID reports Band Steering enabled.",name)

        if w.get("bssTransitionEnabled") is False:
            _add(findings,"REVIEW","WIFI","BSS Transition is off",
                 "802.11v BSS Transition is disabled.",name,
                 "For a multi-AP modern-client SSID, test enabling BSS Transition unless client compatibility argues against it.")
        else:
            _add(findings,"PASS","WIFI","BSS Transition enabled",
                 "SSID reports BSS Transition enabled.",name)

        if mlo:
            status="REVIEW" if kind=="IOT_OPTIMIZED" else "PASS"
            _add(findings,status,"WIFI","Multi-Link Operation enabled",
                 "MLO is enabled on this SSID.",name,
                 "Keep MLO on modern-client SSIDs; avoid it on legacy/IoT SSIDs if compatibility problems appear.")
        elif kind=="STANDARD" and has6 and "WPA3" in sec:
            _add(findings,"REVIEW","WIFI","MLO available for controlled testing",
                 "This is a WPA3-capable 6 GHz STANDARD SSID with MLO disabled.",name,
                 "If you have Wi-Fi 7 clients, test MLO on this SSID and monitor disconnects, roaming and latency before keeping it enabled.")

        if kind in ("HOTSPOT","GUEST") and w.get("clientIsolationEnabled") is False:
            _add(findings,"WARNING","SECURITY","Guest client isolation is off",
                 "Guest/hotspot SSID does not report client isolation.",name,
                 "Enable client isolation unless guests intentionally need peer-to-peer access.")
        elif kind=="IOT_OPTIMIZED" and w.get("clientIsolationEnabled") is False:
            _add(findings,"REVIEW","SEGMENTATION","IoT client isolation is off",
                 "IoT SSID does not report client isolation.",name,
                 "Review whether local IoT device-to-device access is actually required before enabling isolation.")

    # Radio width / current topology stability.
    for d in devices:
        if d.get("optimizerType")!="ACCESS_POINT":
            continue
        for r in ((d.get("interfaces") or {}).get("radios") or []):
            band=r.get("frequencyGHz")
            width=r.get("channelWidthMHz")
            if band==2.4 and isinstance(width,(int,float)) and width>20:
                _add(findings,"REVIEW","WIFI","2.4 GHz channel width is wider than 20 MHz",
                     f"2.4 GHz is configured at {width} MHz on channel {r.get('channel')}.",d.get("name"),
                     "20 MHz is generally the safer coexistence target; validate with your A/B/A workflow before changing it.")

    # Wired link sanity.
    slow_links=[]
    for d in devices:
        if d.get("optimizerType") not in ("SWITCH","GATEWAY"):
            continue
        for p in ((d.get("interfaces") or {}).get("ports") or []):
            speed=p.get("speedMbps")
            cap=p.get("maxSpeedMbps")
            if p.get("state")=="UP" and isinstance(speed,(int,float)) and isinstance(cap,(int,float)):
                if cap>=1000 and speed<=100:
                    slow_links.append((d,p))
    if slow_links:
        for d,p in slow_links:
            _add(findings,"REVIEW","WIRED","Port negotiated well below capability",
                 f"Port {p.get('idx')} is at {p.get('speedMbps')} Mbps on a {p.get('maxSpeedMbps')} Mbps-capable port.",
                 d.get("name"),
                 "Verify this is expected for the endpoint; otherwise check cable, transceiver and NIC negotiation.")
    else:
        _add(findings,"PASS","WIRED","No obvious 100 Mbps negotiation mismatches",
             "No active >=1 Gbps-capable switch port was found negotiated at 100 Mbps or below.")

    # Firewall / ACL review.
    enabled_fw=[p for p in firewall_policies if p.get("enabled") is not False]
    disabled_fw=[p for p in firewall_policies if p.get("enabled") is False]
    if firewall_policies:
        _add(findings,"PASS","FIREWALL","Firewall policy inventory available",
             f"{len(enabled_fw)} enabled and {len(disabled_fw)} disabled policy/policies were returned.")
    else:
        _add(findings,"REVIEW","FIREWALL","No user firewall policies returned",
             "The official API returned no firewall policies.",
             recommendation="This can be valid if only system-defined policy is in use; verify segmentation intent rather than assuming it is insecure.")

    for p in disabled_fw:
        _add(findings,"REVIEW","FIREWALL","Disabled firewall policy",
             "A firewall policy exists but is disabled.",p.get("name"),
             "Confirm the disabled state is intentional.")

    for p in enabled_fw:
        metadata=p.get("metadata") or {}
        origin=str(metadata.get("origin") or "").upper()
        source=p.get("source") or {}
        destination=p.get("destination") or {}
        if _action_type(p)=="ALLOW" and _empty_filter(source) and _empty_filter(destination):
            if origin in ("SYSTEM","SYSTEM_DEFINED","DEFAULT"):
                _add(findings,"PASS","FIREWALL","System allow policy present",
                     "A broad system-defined ALLOW policy is present and is not treated as a user-created exposure.",
                     p.get("name"))
            else:
                _add(findings,"WARNING","FIREWALL","Broad allow firewall policy needs review",
                     "Enabled ALLOW policy appears to have broad/empty source and destination scope with no zone/network restriction visible.",
                     p.get("name"),
                     "Verify this user-defined policy is intentionally broad.")

    if firewall_zones:
        _add(findings,"PASS","FIREWALL","Firewall zones discovered",
             f"{len(firewall_zones)} firewall zone(s) were returned.")

    disabled_acl=[x for x in acl_rules if x.get("enabled") is False]
    if acl_rules:
        _add(findings,"PASS","FIREWALL","ACL inventory available",
             f"{len(acl_rules)} ACL rule(s) were returned.")
    for x in disabled_acl:
        _add(findings,"REVIEW","FIREWALL","Disabled ACL rule",
             "An ACL rule exists but is disabled.",x.get("name"),
             "Confirm the disabled state is intentional.")

    # DNS / WAN inventories.
    if wans:
        _add(findings,"PASS","WAN","WAN interface inventory available",
             f"{len(wans)} WAN interface definition(s) were returned.")
    else:
        _add(findings,"REVIEW","WAN","WAN interface inventory unavailable",
             "No WAN interface definitions were returned by the API.")

    disabled_dns=[x for x in dns_policies if x.get("enabled") is False]
    if dns_policies:
        _add(findings,"PASS","DHCP_DNS","DNS policy inventory available",
             f"{len(dns_policies)} DNS policy/policies were returned.")
    for x in disabled_dns:
        _add(findings,"REVIEW","DHCP_DNS","Disabled DNS policy",
             "A DNS policy exists but is disabled.",x.get("domain") or x.get("name"),
             "Confirm the disabled state is intentional.")

    categories=["SECURITY","FIREWALL","SEGMENTATION","WIFI","WIRED","WAN","DHCP_DNS","DEVICE_HEALTH"]
    scores={cat:_score(findings,cat) for cat in categories}
    overall=round(sum(scores.values())/len(scores)) if scores else 100
    counts={status:sum(1 for x in findings if x.get("status")==status)
            for status in ("CRITICAL","WARNING","REVIEW","PASS")}

    order={"CRITICAL":0,"WARNING":1,"REVIEW":2,"PASS":3}
    findings.sort(key=lambda x:(order.get(x.get("status"),9),x.get("category",""),x.get("title","")))

    return {
        "overallScore":overall,
        "scores":scores,
        "counts":counts,
        "findings":findings,
        "inventory":{
            "firewallZones":firewall_zones,
            "firewallPolicies":firewall_policies,
            "aclRules":acl_rules,
            "dnsPolicies":dns_policies,
            "wans":wans,
            "networks":networks,
            "wifi":wifi,
        },
        "mode":"READ_ONLY",
    }
