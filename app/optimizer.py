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

def analyze(snapshot, retry_trends=None, ap_baselines=None):
    retry_trends = retry_trends or {}
    ap_baselines = ap_baselines or {}
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

            baseline=ap_baselines.get(d.get("id")) or {}
            baseline_avg=baseline.get("avgClients")
            samples=baseline.get("sampleCount",0)
            if samples >= 30 and baseline_avg is not None and d.get("clientCount",0) > max(float(baseline_avg)*1.8,float(baseline_avg)+6):
                recs.append({"severity":"INFO","category":"AP_BALANCE","device":d.get("name"),
                             "message":f"{d.get('clientCount',0)} clients vs this AP's 24h baseline {baseline_avg:.1f}."})
            elif samples < 30 and len(aps) >= 2 and avg and d.get("clientCount",0) > avg*1.8:
                recs.append({"severity":"INFO","category":"AP_BALANCE","device":d.get("name"),
                             "message":f"{d.get('clientCount',0)} clients vs current AP average {avg:.1f}; learning historical baseline."})

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


def _retry_for_band(ap, retry_trends, band):
    trend = (retry_trends or {}).get(ap.get("id")) or {}
    key = {2.4:"retry24",5:"retry5",6:"retry6"}.get(band)
    if trend.get("sampleCount",0) >= 3 and key and trend.get(key) is not None:
        return float(trend.get(key)), f"{trend.get('windowMinutes',15)}-min average"
    stat_radios = (((ap.get("statistics") or {}).get("interfaces") or {}).get("radios") or [])
    for r in stat_radios:
        if r.get("frequencyGHz") == band and r.get("txRetriesPct") is not None:
            return float(r.get("txRetriesPct")), "current"
    return None, "unavailable"

def _five_ghz_block(channel, width):
    if not channel or not width:
        return None
    if width <= 20:
        return f"20-{channel}"
    blocks80 = [
        ({36,40,44,48},"36-48"),
        ({52,56,60,64},"52-64 DFS"),
        ({100,104,108,112},"100-112 DFS"),
        ({116,120,124,128},"116-128 DFS"),
        ({132,136,140,144},"132-144 DFS"),
        ({149,153,157,161},"149-161"),
    ]
    if width == 40:
        groups=[({36,40},"36-40"),({44,48},"44-48"),({52,56},"52-56 DFS"),({60,64},"60-64 DFS"),
                ({100,104},"100-104 DFS"),({108,112},"108-112 DFS"),({116,120},"116-120 DFS"),
                ({124,128},"124-128 DFS"),({132,136},"132-136 DFS"),({140,144},"140-144 DFS"),
                ({149,153},"149-153"),({157,161},"157-161")]
        for chans,name in groups:
            if channel in chans:return name
    if width >= 80:
        for chans,name in blocks80:
            if channel in chans:return name
    return f"{width}MHz@{channel}"

def _six_ghz_block(channel, width):
    if not channel or not width:
        return None
    primaries=max(1,int(width/20))
    span=4*primaries
    start=1+((int(channel)-1)//span)*span
    end=start+span-4
    return f"{start}-{end}"

def build_channel_plan(snapshot, retry_trends=None):
    retry_trends = retry_trends or {}
    aps=[d for d in snapshot.get("devices",[]) if d.get("optimizerType")=="ACCESS_POINT"]
    plan=[]
    conflicts=[]

    band_rows={2.4:[],5:[],6:[]}
    for ap in aps:
        cfg=((ap.get("interfaces") or {}).get("radios") or [])
        for r in cfg:
            band=r.get("frequencyGHz")
            if band not in band_rows:
                continue
            retry,basis=_retry_for_band(ap,retry_trends,band)
            row={
                "apId":ap.get("id"),"apName":ap.get("name"),"model":ap.get("model"),
                "band":band,"channel":r.get("channel"),"widthMHz":r.get("channelWidthMHz"),
                "retryPct":retry,"retryBasis":basis,"clientCount":ap.get("clientCount",0)
            }
            if band==5:
                row["channelBlock"]=_five_ghz_block(row["channel"],row["widthMHz"])
            elif band==6:
                row["channelBlock"]=_six_ghz_block(row["channel"],row["widthMHz"])
            else:
                row["channelBlock"]=str(row["channel"])
            band_rows[band].append(row)

    # Detect only conflicts we can prove from our own AP configuration.
    for band,rows in band_rows.items():
        for i in range(len(rows)):
            for j in range(i+1,len(rows)):
                a,b=rows[i],rows[j]
                same=False
                if band==2.4:
                    same=a.get("channel")==b.get("channel")
                else:
                    same=a.get("channelBlock") and a.get("channelBlock")==b.get("channelBlock")
                if same:
                    conflicts.append({
                        "band":band,"aps":[a["apName"],b["apName"]],
                        "detail":f"Both APs use {band} GHz block {a.get('channelBlock')}."
                    })

    used24=set()
    for row in band_rows[2.4]:
        ch=row.get("channel"); width=row.get("widthMHz"); retry=row.get("retryPct")
        rec_ch=ch if ch in (1,6,11) else next((x for x in (1,6,11) if x not in used24),1)
        used24.add(rec_ch)
        actions=[]
        if width and width>20: actions.append("Change width to 20 MHz")
        if ch not in (1,6,11): actions.append(f"Move to channel {rec_ch}")
        if retry is not None and retry>=15: actions.append("Investigate external interference / client quality")
        plan.append({**row,"recommendedChannel":rec_ch,"recommendedWidthMHz":20,
                     "status":"CONSIDER_CHANGE" if actions else "KEEP",
                     "actions":actions or ["Keep current 2.4 GHz channel plan"]})

    preferred5=[
        {"block":"36-48","channel":36,"dfs":False},
        {"block":"100-112 DFS","channel":100,"dfs":True},
        {"block":"149-161","channel":149,"dfs":False},
    ]
    assigned=set()
    # Keep unique current blocks first.
    block_counts={}
    for row in band_rows[5]:
        block_counts[row.get("channelBlock")]=block_counts.get(row.get("channelBlock"),0)+1
    for row in band_rows[5]:
        current=row.get("channelBlock")
        target=None
        if current in {x["block"] for x in preferred5} and block_counts.get(current,0)==1 and current not in assigned:
            target=next(x for x in preferred5 if x["block"]==current)
        if target is None:
            target=next((x for x in preferred5 if x["block"] not in assigned),preferred5[0])
        assigned.add(target["block"])
        actions=[]
        if current!=target["block"]:
            actions.append(f"Consider {target['block']} block (primary channel {target['channel']})")
        if row.get("retryPct") is not None and row["retryPct"]>=15:
            actions.append("High retry trend: prioritize a cleaner block after RF survey")
        plan.append({**row,"recommendedChannel":target["channel"],"recommendedWidthMHz":80,
                     "recommendedBlock":target["block"],"dfs":target["dfs"],
                     "status":"CONSIDER_CHANGE" if actions else "KEEP",
                     "actions":actions or ["Keep current 5 GHz block"]})

    used6=set()
    for row in band_rows[6]:
        block=row.get("channelBlock")
        actions=[]
        recommended_width=row.get("widthMHz")
        if block in used6:
            actions.append("Overlaps another AP's 6 GHz block")
            if row.get("widthMHz",0)>160:
                recommended_width=160
                actions.append("Consider 160 MHz for better channel reuse")
        used6.add(block)
        if row.get("retryPct") is not None and row["retryPct"]>=15 and row.get("widthMHz",0)>160:
            recommended_width=160
            actions.append("Elevated retries: consider reducing 320 MHz to 160 MHz")
        plan.append({**row,"recommendedChannel":row.get("channel"),"recommendedWidthMHz":recommended_width,
                     "status":"CONSIDER_CHANGE" if actions else "KEEP",
                     "actions":actions or ["Keep current 6 GHz channel block"]})

    return {
        "mode":"SAFE_ADVISORY",
        "externalRfScanAvailable":False,
        "automaticRadioWritesAvailable":False,
        "notes":[
            "Planner uses current AP radio configuration, AP-to-AP channel overlap, client load and retry trends.",
            "The official UniFi Network API used by this app does not expose a documented neighboring-network RF scan or per-AP radio write endpoint.",
            "Recommended DFS channels may be cleaner but can change if radar is detected."
        ],
        "conflicts":conflicts,
        "items":plan
    }
