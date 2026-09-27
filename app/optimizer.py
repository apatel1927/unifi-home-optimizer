def device_type(device):
    features = device.get("features", {})
    if isinstance(features, dict):
        if "accessPoint" in features:
            return "ACCESS_POINT"
        if "switching" in features:
            if "Dream Machine" in device.get("model", ""):
                return "GATEWAY"
            return "SWITCH"
    return "OTHER"

def build_snapshot(api):
    site = api.site()
    if not site:
        return None
    site_id = site["id"]
    basics = api.devices(site_id)
    clients = api.clients(site_id)
    details = []
    for b in basics:
        d = api.device_detail(site_id, b["id"]) or b
        d = dict(d)
        d["optimizerType"] = device_type(d)
        d["statistics"] = api.device_stats(site_id, d["id"]) or {}
        details.append(d)

    device_map = {d.get("id"): d for d in details}
    counts = {}
    for c in clients:
        u = c.get("uplinkDeviceId")
        if u:
            counts[u] = counts.get(u, 0) + 1

    for d in details:
        d["clientCount"] = counts.get(d.get("id"), 0)
        uplink_id = (d.get("uplink") or {}).get("deviceId")
        d["uplinkName"] = (device_map.get(uplink_id) or {}).get("name")

    enriched = []
    for c in clients:
        row = dict(c)
        u = device_map.get(c.get("uplinkDeviceId")) or {}
        row["uplinkDeviceName"] = u.get("name", "Unknown")
        row["uplinkDeviceModel"] = u.get("model", "Unknown")
        enriched.append(row)

    return {
        "site": site,
        "devices": details,
        "clients": enriched,
        "wifiBroadcasts": api.wifi_broadcasts(site_id),
    }

def analyze(snapshot, retry_trends=None):
    retry_trends = retry_trends or {}
    recs = []
    aps = [d for d in snapshot["devices"] if d.get("optimizerType") == "ACCESS_POINT"]
    avg = (sum(d.get("clientCount",0) for d in aps) / len(aps)) if aps else 0

    for d in snapshot["devices"]:
        if d.get("state") != "ONLINE":
            recs.append({"severity":"HIGH","category":"DEVICE","device":d.get("name"),"message":"Device is offline."})

        if d.get("optimizerType") == "ACCESS_POINT":
            cfg_radios = ((d.get("interfaces") or {}).get("radios") or [])
            stat_radios = ((d.get("statistics") or {}).get("interfaces") or {}).get("radios") or []
            stat_map = {r.get("frequencyGHz"):r for r in stat_radios}

            trend = retry_trends.get(d.get("id")) or {}
            trend_key = {2.4:"retry24",5:"retry5",6:"retry6"}
            for r in cfg_radios:
                f=r.get("frequencyGHz"); width=r.get("channelWidthMHz"); ch=r.get("channel")
                current=(stat_map.get(f) or {}).get("txRetriesPct")
                averaged=trend.get(trend_key.get(f))
                sample_count=trend.get("sampleCount",0)
                retries=averaged if sample_count >= 3 and averaged is not None else current
                basis=f"{trend.get('windowMinutes',15)}-min average" if sample_count >= 3 and averaged is not None else "current"
                if f == 2.4 and width and width > 20:
                    recs.append({"severity":"MEDIUM","category":"WIFI","device":d.get("name"),
                                 "message":f"2.4 GHz is channel {ch} at {width} MHz; target 20 MHz."})
                if retries is not None and retries >= 25:
                    recs.append({"severity":"HIGH","category":"RETRIES","device":d.get("name"),
                                 "message":f"{f} GHz TX retries are {retries:.1f}% ({basis})."})
                elif retries is not None and retries >= 15:
                    recs.append({"severity":"MEDIUM","category":"RETRIES","device":d.get("name"),
                                 "message":f"{f} GHz TX retries are {retries:.1f}% ({basis})."})
                elif retries is not None and retries >= 8:
                    recs.append({"severity":"INFO","category":"RETRIES","device":d.get("name"),
                                 "message":f"{f} GHz TX retries are {retries:.1f}% ({basis}); watch for persistence."})

            if len(aps) >= 2 and avg and d.get("clientCount",0) > avg*1.8:
                recs.append({"severity":"INFO","category":"AP_BALANCE","device":d.get("name"),
                             "message":f"{d.get('clientCount',0)} clients vs AP average {avg:.1f}."})

        if d.get("optimizerType") in ("SWITCH","GATEWAY"):
            for p in ((d.get("interfaces") or {}).get("ports") or []):
                if p.get("state") == "UP" and p.get("maxSpeedMbps",0) >= 10000 and p.get("speedMbps",0) <= 100:
                    recs.append({"severity":"INFO","category":"WIRED_OBSERVATION","device":d.get("name"),
                                 "message":f"Port {p.get('idx')} negotiated at {p.get('speedMbps')} Mbps. This may be normal for a 100 Mbps endpoint; verify only if unexpected."})

    for w in snapshot["wifiBroadcasts"]:
        if w.get("type") != "STANDARD":
            continue
        if w.get("bandSteeringEnabled") is False:
            recs.append({"severity":"MEDIUM","category":"AUTO_SUPPORTED","device":w.get("name"),
                         "message":"Band Steering can be enabled automatically."})
        if w.get("bssTransitionEnabled") is False:
            recs.append({"severity":"MEDIUM","category":"AUTO_SUPPORTED","device":w.get("name"),
                         "message":"BSS Transition can be enabled automatically."})

    order={"HIGH":0,"MEDIUM":1,"INFO":2}
    recs.sort(key=lambda x: order.get(x["severity"],99))
    high = sum(1 for x in recs if x["severity"]=="HIGH")
    medium = sum(1 for x in recs if x["severity"]=="MEDIUM")
    info = sum(1 for x in recs if x["severity"]=="INFO")
    health_score = max(0, 100 - high*15 - medium*6)
    return {
        "recommendations": recs,
        "high": high,
        "medium": medium,
        "info": info,
        "healthScore": health_score,
        "wifiFindings": [x for x in recs if x["category"] in ("WIFI","RETRIES","AUTO_SUPPORTED","AP_BALANCE")],
        "wiredFindings": [x for x in recs if x["category"] in ("WIRED","WIRED_OBSERVATION","DEVICE")],
    }

def wifi_status(wifi):
    if wifi.get("type") != "STANDARD":
        return {"status":"PROTECTED","detail":f"{wifi.get('type')} broadcast"}
    needs=[]
    if wifi.get("bandSteeringEnabled") is False: needs.append("Band Steering")
    if wifi.get("bssTransitionEnabled") is False: needs.append("BSS Transition")
    return {"status":"NEEDS_ATTENTION","detail":", ".join(needs)} if needs else {"status":"ALREADY_OPTIMIZED","detail":"Band Steering ON, BSS Transition ON"}

def build_wifi_payload(detail):
    allowed = [
        "type","name","network","enabled","securityConfiguration","broadcastingDeviceFilter",
        "mdnsProxyConfiguration","multicastFilteringPolicy","multicastToUnicastConversionEnabled",
        "clientIsolationEnabled","hideName","uapsdEnabled","channel2gLockedTo6",
        "dtimPeriod2gLockedTo3","basicDataRateKbpsByFrequencyGHz","clientFilteringPolicy",
        "blackoutScheduleConfiguration","broadcastingFrequenciesGHz","hotspotConfiguration",
        "mloEnabled","bandSteeringEnabled","arpProxyEnabled","bssTransitionEnabled",
        "advertiseDeviceName","dtimPeriodByFrequencyGHzOverride","dnsAssistanceConfiguration",
        "handoffSuggestionsConfiguration"
    ]
    return {k: detail[k] for k in allowed if k in detail}

def auto_optimize(api, db):
    site=api.site()
    if not site:
        return {"ok":False,"error":"No site"}
    site_id=site["id"]
    results=[]
    for w in api.wifi_broadcasts(site_id):
        name=w.get("name","WiFi")
        if w.get("type") != "STANDARD":
            msg=f"Skipped {w.get('type')} broadcast - protected from automatic modification"
            db.log("WIFI_AUTO_OPTIMIZE",name,msg,"SKIPPED")
            results.append({"name":name,"changed":False,"status":"SKIPPED","message":msg})
            continue

        payload=build_wifi_payload(w)
        changes=[]
        bands=w.get("broadcastingFrequenciesGHz") or []
        if len(bands)>=2 and w.get("bandSteeringEnabled") is False:
            payload["bandSteeringEnabled"]=True; changes.append("Band Steering enabled")
        if w.get("bssTransitionEnabled") is False:
            payload["bssTransitionEnabled"]=True; changes.append("BSS Transition enabled")

        if not changes:
            msg="Band Steering ON, BSS Transition ON"
            db.log("WIFI_AUTO_OPTIMIZE",name,msg,"ALREADY_OPTIMIZED")
            results.append({"name":name,"changed":False,"status":"ALREADY_OPTIMIZED","message":msg})
            continue

        r=api.put(f"/sites/{site_id}/wifi/broadcasts/{w.get('id')}", payload)
        if r.get("ok"):
            detail=", ".join(changes)
            db.log("WIFI_AUTO_OPTIMIZE",name,detail,"SUCCESS")
            results.append({"name":name,"changed":True,"status":"SUCCESS","message":detail})
        else:
            failure=f"FAILED {r.get('status')} {r.get('data',r.get('error'))}"
            db.log("WIFI_AUTO_OPTIMIZE",name,", ".join(changes),failure)
            results.append({"name":name,"changed":False,"status":"FAILED","message":failure})
    return {"ok":True,"results":results}
