import itertools

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
        "networks": api.networks(site_id),
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

def radio_conflict_key(band, channel, width):
    if channel is None:
        return None
    if band == 2.4:
        return str(channel)
    if band == 5:
        return _five_ghz_block(channel, width)
    if band == 6:
        return _six_ghz_block(channel, width)
    return None

def _scan_ap_band(ap, band, spectrum_scans, max_age_seconds=86400):
    if not spectrum_scans:
        return None
    aps=spectrum_scans.get("accessPoints") or spectrum_scans.get("aps") or []
    mac=str(ap.get("macAddress") or ap.get("mac") or "").lower().replace("-",":")
    ap_id=ap.get("id")
    name=str(ap.get("name") or "")
    match=None
    for item in aps:
        imac=str(item.get("apMac") or "").lower().replace("-",":")
        if (mac and imac==mac) or (ap_id and item.get("apId")==ap_id) or (name and item.get("apName")==name):
            match=item
            break
    if not match:
        return None
    candidates=[]
    for entry in match.get("bands") or []:
        try:
            same=float(entry.get("band"))==float(band)
        except Exception:
            same=False
        if not same or not (entry.get("rows") or []):
            continue
        age=entry.get("ageSeconds")
        if age is not None and float(age)>float(max_age_seconds):
            continue
        candidates.append(entry)
    if not candidates:
        return None
    candidates.sort(key=lambda x:x.get("scanEpoch") or 0,reverse=True)
    return candidates[0]

def _scan_row_score(row):
    util=row.get("utilizationPct")
    bss=row.get("otherBssCount")
    interference=row.get("interferenceDbm")
    if util is None and bss is None and interference is None:
        return None
    try:
        util=max(0.0,min(100.0,float(util))) if util is not None else 0.0
    except Exception:
        util=0.0
    try:
        bss=max(0.0,float(bss)) if bss is not None else 0.0
    except Exception:
        bss=0.0
    try:
        # -96 dBm is treated as the quiet reference floor; less-negative values
        # add a gradually increasing interference penalty.
        ip=max(0.0,min(45.0,float(interference)+96.0)) if interference is not None else 0.0
    except Exception:
        ip=0.0
    return round((util*0.60)+(min(30.0,bss*2.0))+(ip*0.70),2)

def _aggregate_scan_rows(rows, key_fn, channel_fn):
    grouped={}
    for row in rows:
        key=key_fn(row)
        if key is None:
            continue
        score=_scan_row_score(row)
        if score is None:
            continue
        grouped.setdefault(key,[]).append((row,score))
    output={}
    for key,items in grouped.items():
        scores=[x[1] for x in items]
        utils=[float(x[0].get("utilizationPct")) for x in items if x[0].get("utilizationPct") is not None]
        bss=[float(x[0].get("otherBssCount")) for x in items if x[0].get("otherBssCount") is not None]
        interference=[float(x[0].get("interferenceDbm")) for x in items if x[0].get("interferenceDbm") is not None]
        output[key]={
            "key":key,
            "channel":channel_fn(key,items),
            "score":round(sum(scores)/len(scores),2),
            "avgUtilizationPct":round(sum(utils)/len(utils),2) if utils else None,
            "maxUtilizationPct":round(max(utils),2) if utils else None,
            "avgOtherBssCount":round(sum(bss)/len(bss),2) if bss else None,
            "worstInterferenceDbm":round(max(interference),1) if interference else None,
            "sampleRows":len(items),
        }
    return output

def _scan_candidates_for(ap, band, width, spectrum_scans):
    entry=_scan_ap_band(ap,band,spectrum_scans)
    if not entry:
        return {},None
    rows=entry.get("rows") or []
    exact=[x for x in rows if x.get("widthMHz")==width]

    if band==2.4:
        source=exact or [x for x in rows if x.get("widthMHz")==20]
        source=[x for x in source if x.get("channel") in (1,6,11)]
        candidates=_aggregate_scan_rows(
            source,
            lambda x:str(x.get("channel")) if x.get("channel") in (1,6,11) else None,
            lambda key,items:int(key),
        )
    elif band==5:
        known_blocks={
            "36-48":36,"52-64 DFS":52,"100-112 DFS":100,
            "116-128 DFS":116,"132-144 DFS":132,"149-161":149
        }
        if exact:
            exact_known=[x for x in exact if _five_ghz_block(x.get("channel"),80) in known_blocks]
            source=exact_known or [x for x in rows if x.get("widthMHz")==20]
        else:
            source=[x for x in rows if x.get("widthMHz")==20]
        candidates=_aggregate_scan_rows(
            source,
            lambda x:(_five_ghz_block(x.get("channel"),80)
                      if _five_ghz_block(x.get("channel"),80) in known_blocks else None),
            lambda key,items:known_blocks.get(key),
        )
    elif band==6:
        source=exact
        candidates=_aggregate_scan_rows(
            source,
            lambda x:_six_ghz_block(x.get("channel"),width),
            lambda key,items:items[0][0].get("channel"),
        )
    else:
        candidates={}

    evidence={
        "scanAt":entry.get("scanAt"),
        "scanEpoch":entry.get("scanEpoch"),
        "ageSeconds":entry.get("ageSeconds"),
        "candidateCount":len(candidates),
        "widthMHz":width,
    }
    return candidates,evidence

def _best_scan_assignment(rows, band, width, spectrum_scans, minimum_improvement=10.0):
    if not rows:
        return {},{}
    by_ap={}
    evidence={}
    for row in rows:
        ap={
            "id":row.get("apId"),"name":row.get("apName"),
            "macAddress":row.get("apMac"),"mac":row.get("apMac")
        }
        candidates,meta=_scan_candidates_for(ap,band,width,spectrum_scans)
        by_ap[row.get("apId")]=candidates
        evidence[row.get("apId")]=meta
        if not candidates:
            return {},evidence

    current_keys=[]
    for row in rows:
        key=(str(row.get("channel")) if band==2.4 else
             _five_ghz_block(row.get("channel"),width) if band==5 else
             _six_ghz_block(row.get("channel"),width))
        if key not in by_ap.get(row.get("apId"),{}):
            return {},evidence
        current_keys.append(key)

    current_cost=sum(by_ap[row.get("apId")][key]["score"] for row,key in zip(rows,current_keys))
    options=[list(by_ap[row.get("apId")].keys()) for row in rows]
    best=None
    for combo in itertools.product(*options):
        cost=0.0
        for row,key,current in zip(rows,combo,current_keys):
            cost+=by_ap[row.get("apId")][key]["score"]
            if key!=current:
                cost+=1.0  # hysteresis: prefer keeping a nearly-equivalent current block
        duplicate_penalty=0.0
        for i in range(len(combo)):
            for j in range(i+1,len(combo)):
                if combo[i]==combo[j]:
                    duplicate_penalty+=45.0
        cost+=duplicate_penalty
        if best is None or cost<best[0]:
            best=(cost,combo)

    if not best or (current_cost-best[0])<float(minimum_improvement):
        return {},evidence

    targets={}
    for row,key,current in zip(rows,best[1],current_keys):
        candidate=by_ap[row.get("apId")][key]
        targets[row.get("apId")]={
            **candidate,
            "currentKey":current,
            "currentScore":by_ap[row.get("apId")][current]["score"],
            "improvementScore":round(by_ap[row.get("apId")][current]["score"]-candidate["score"],2),
            "assignmentImprovementScore":round(current_cost-best[0],2),
            "scanMeta":evidence.get(row.get("apId")) or {},
        }
    return targets,evidence

def _rf_metrics_for(ap, band, rf_environment):
    if not rf_environment:
        return {}
    rows=rf_environment.get("radios") or rf_environment.get("liveRadios") or rf_environment.get("latest") or []
    mac=str(ap.get("macAddress") or ap.get("mac") or "").lower().replace("-",":")
    name=str(ap.get("name") or "")
    for r in rows:
        try:
            same_band=float(r.get("band"))==float(band)
        except Exception:
            same_band=False
        if not same_band:
            continue
        rmac=str(r.get("apMac") or r.get("ap_mac") or "").lower().replace("-",":")
        rname=str(r.get("apName") or r.get("ap_name") or "")
        if (mac and rmac==mac) or (name and rname==name):
            return {
                "rfUtilizationPct":r.get("channelUtilizationPct") if r.get("channelUtilizationPct") is not None else r.get("channel_utilization_pct"),
                "rfExternalBusyPct":r.get("externalBusyPct") if r.get("externalBusyPct") is not None else r.get("external_busy_pct"),
                "rfNoiseDbm":r.get("noiseDbm") if r.get("noiseDbm") is not None else r.get("noise_dbm"),
                "rfNeighborCount":r.get("neighborCount") if r.get("neighborCount") is not None else r.get("neighbor_count"),
                "rfNeighborRssiTrusted":False,
            }
    return {}

def build_channel_plan(snapshot, retry_trends=None, rf_environment=None, spectrum_scans=None):
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
                "apMac":ap.get("macAddress") or ap.get("mac"),
                "band":band,"channel":r.get("channel"),"widthMHz":r.get("channelWidthMHz"),
                "retryPct":retry,"retryBasis":basis,"clientCount":ap.get("clientCount",0),
                **_rf_metrics_for(ap,band,rf_environment)
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

    scan24_targets,scan24_meta=_best_scan_assignment(
        band_rows[2.4],2.4,20,spectrum_scans,minimum_improvement=8.0
    )
    scan5_targets,scan5_meta=_best_scan_assignment(
        band_rows[5],5,80,spectrum_scans,minimum_improvement=10.0
    )

    used24=set()
    for row in band_rows[2.4]:
        ch=row.get("channel"); width=row.get("widthMHz"); retry=row.get("retryPct")
        scan_target=scan24_targets.get(row.get("apId"))
        rec_ch=(scan_target.get("channel") if scan_target else
                (ch if ch in (1,6,11) else next((x for x in (1,6,11) if x not in used24),1)))
        used24.add(rec_ch)
        config_actions=[]
        diagnostic_actions=[]
        if width and width>20: config_actions.append("Change width to 20 MHz")
        if ch not in (1,6,11): config_actions.append(f"Move to channel {rec_ch}")
        elif scan_target and rec_ch!=ch:
            config_actions.append(
                f"Spectrum scan favors channel {rec_ch}; coordinated site assignment improves scan score by {scan_target.get('assignmentImprovementScore')}"
            )
        if retry is not None and retry>=15: diagnostic_actions.append("Investigate external interference / client quality")
        if row.get("rfUtilizationPct") is not None and float(row.get("rfUtilizationPct"))>=60:
            diagnostic_actions.append("High current-channel utilization in passive RF telemetry")
        if row.get("rfExternalBusyPct") is not None and float(row.get("rfExternalBusyPct"))>=40:
            diagnostic_actions.append("High external busy time on the current channel")
        testable=(rec_ch!=ch or 20!=width)
        status="CONSIDER_CHANGE" if testable else ("INVESTIGATE" if diagnostic_actions else "KEEP")
        actions=config_actions+diagnostic_actions
        scan_meta=(scan_target or {}).get("scanMeta") or scan24_meta.get(row.get("apId")) or {}
        current_scan=(scan_target or {}).get("currentScore")
        recommended_scan=(scan_target or {}).get("score")
        plan.append({**row,"recommendedChannel":rec_ch,"recommendedWidthMHz":20,
                     "testableChange":testable,"status":status,
                     "scanBackedRecommendation":bool(scan_target and rec_ch!=ch),
                     "scanAgeSeconds":scan_meta.get("ageSeconds"),
                     "scanAt":scan_meta.get("scanAt"),
                     "scanCandidateCount":scan_meta.get("candidateCount"),
                     "scanCurrentScore":current_scan,
                     "scanRecommendedScore":recommended_scan,
                     "scanImprovementScore":(scan_target or {}).get("improvementScore"),
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
        scan_target=scan5_targets.get(row.get("apId"))
        target=None
        if scan_target:
            target={
                "block":scan_target.get("key"),
                "channel":scan_target.get("channel"),
                "dfs":"DFS" in str(scan_target.get("key") or ""),
            }
        if target is None and current in {x["block"] for x in preferred5} and block_counts.get(current,0)==1 and current not in assigned:
            target=next(x for x in preferred5 if x["block"]==current)
        if target is None:
            target=next((x for x in preferred5 if x["block"] not in assigned),preferred5[0])
        assigned.add(target["block"])
        config_actions=[]
        diagnostic_actions=[]
        if current!=target["block"]:
            if scan_target:
                config_actions.append(
                    f"Spectrum scan favors {target['block']} (primary channel {target['channel']}); coordinated site assignment improves scan score by {scan_target.get('assignmentImprovementScore')}"
                )
            else:
                config_actions.append(f"Consider {target['block']} block (primary channel {target['channel']})")
        if row.get("retryPct") is not None and row["retryPct"]>=15:
            diagnostic_actions.append("High retry trend: prioritize a cleaner block after RF survey")
        if row.get("rfUtilizationPct") is not None and float(row.get("rfUtilizationPct"))>=60:
            diagnostic_actions.append("High current-channel utilization in passive RF telemetry")
        if row.get("rfExternalBusyPct") is not None and float(row.get("rfExternalBusyPct"))>=40:
            diagnostic_actions.append("High external busy time on the current channel")
        testable=(current!=target["block"] or row.get("widthMHz")!=80)
        status="CONSIDER_CHANGE" if testable else ("INVESTIGATE" if diagnostic_actions else "KEEP")
        actions=config_actions+diagnostic_actions
        scan_meta=(scan_target or {}).get("scanMeta") or scan5_meta.get(row.get("apId")) or {}
        plan.append({**row,"recommendedChannel":target["channel"],"recommendedWidthMHz":80,
                     "recommendedBlock":target["block"],"dfs":target["dfs"],
                     "testableChange":testable,"status":status,
                     "scanBackedRecommendation":bool(scan_target and current!=target["block"]),
                     "scanAgeSeconds":scan_meta.get("ageSeconds"),
                     "scanAt":scan_meta.get("scanAt"),
                     "scanCandidateCount":scan_meta.get("candidateCount"),
                     "scanCurrentScore":(scan_target or {}).get("currentScore"),
                     "scanRecommendedScore":(scan_target or {}).get("score"),
                     "scanImprovementScore":(scan_target or {}).get("improvementScore"),
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
        if row.get("rfUtilizationPct") is not None and float(row.get("rfUtilizationPct"))>=60:
            actions.append("High current-channel utilization in passive RF telemetry")
        if row.get("rfExternalBusyPct") is not None and float(row.get("rfExternalBusyPct"))>=40:
            actions.append("High external busy time on the current channel")
        testable=(recommended_width!=row.get("widthMHz"))
        status="CONSIDER_CHANGE" if testable else ("INVESTIGATE" if actions else "KEEP")
        scan6,scan6_meta=_scan_candidates_for(
            {"id":row.get("apId"),"name":row.get("apName"),"macAddress":row.get("apMac")},
            6,recommended_width,spectrum_scans
        )
        current6=scan6.get(_six_ghz_block(row.get("channel"),recommended_width)) if scan6 else None
        plan.append({**row,"recommendedChannel":row.get("channel"),"recommendedWidthMHz":recommended_width,
                     "testableChange":testable,"status":status,
                     "scanBackedRecommendation":False,
                     "scanAgeSeconds":(scan6_meta or {}).get("ageSeconds"),
                     "scanAt":(scan6_meta or {}).get("scanAt"),
                     "scanCandidateCount":(scan6_meta or {}).get("candidateCount"),
                     "scanCurrentScore":(current6 or {}).get("score"),
                     "scanRecommendedScore":None,
                     "scanImprovementScore":None,
                     "actions":actions or ["Keep current 6 GHz channel block"]})

    return {
        "mode":"SAFE_ADVISORY",
        "externalRfScanAvailable":bool(spectrum_scans and (spectrum_scans.get("freshCount") or spectrum_scans.get("availableCount"))),
        "spectrumScanFreshCount":(spectrum_scans or {}).get("freshCount",0),
        "scanBackedCount":sum(1 for x in plan if x.get("scanBackedRecommendation")),
        "automaticRadioWritesAvailable":False,
        "neighborRssiTrusted":False,
        "notes":[
            "Fresh spectrum-scan evidence is used to rank candidate channels when available; existing A/B/A history remains the final validation layer because scan snapshots alone do not prove a real client-performance improvement.",
            "Fresh spectrum scans (24 hours or newer) can score candidate 2.4 GHz channels and 5 GHz 80 MHz blocks using measured utilization, neighboring-BSS count, and interference. Changes are only proposed when the coordinated site-wide score improves by a meaningful margin.",
            "Spectrum scans are snapshots. Any scan-backed channel change still goes through the existing one-radio-at-a-time A/B/A workflow and is rolled back if retries or topology get worse.",
            "Neighbor RSSI remains observational only and is not used in scan/channel scoring until controller field semantics are independently validated.",
            "Manual spectrum scans are never launched automatically because some AP/firmware combinations briefly interrupt client traffic while scanning.",
            "Recommended DFS channels may be cleaner but can change if radar is detected."
        ],
        "conflicts":conflicts,
        "items":plan
    }
