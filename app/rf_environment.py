def _num(value):
    try:
        if value in (None,""):
            return None
        return float(value)
    except Exception:
        return None


def _normalize_signed_magnitude(value):
    """Create a provisional signed observation without assigning physical units.

    Some U7 classic/rogue payloads expose positive magnitudes where a related
    field may normally be signed. Convert only plausible magnitudes and mark the
    conversion. Callers must keep the result diagnostic until the controller
    semantics are independently verified.
    """
    n=_num(value)
    if n is None:
        return None,False
    if -150.0 <= n <= 0.0:
        return n,False
    if 0.0 < n <= 127.0:
        return -n,True
    return None,False


def _first(d, keys):
    if not isinstance(d,dict):
        return None
    for k in keys:
        if k in d and d.get(k) not in (None,""):
            return d.get(k)
    return None


def _band_from_radio(value, channel=None, frequency=None):
    s=str(value or "").lower()
    if s in ("ng","2g","2.4","2.4ghz") or "2.4" in s:
        return 2.4
    if s in ("na","5g","5","5ghz") or s.startswith("5"):
        return 5.0
    if s in ("6e","6g","6","6ghz") or s.startswith("6"):
        return 6.0
    try:
        freq=float(frequency)
        if 2400 <= freq < 2500:
            return 2.4
        if 4900 <= freq < 5925:
            return 5.0
        if freq >= 5925:
            return 6.0
    except Exception:
        pass
    try:
        ch=int(channel)
        if ch <= 14:
            return 2.4
        if ch >= 30:
            return 5.0
    except Exception:
        pass
    return None


def _radio_key(r):
    return str(_first(r,("radio","name","radio_name","phy")) or "")


def _neighbor_band(n):
    return _band_from_radio(
        _first(n,("radio","radio_name","band","frequency_band")),
        _first(n,("channel","channel_number")),
        _first(n,("frequency","freq","frequency_mhz","freq_mhz"))
    )


def _neighbor_row(n):
    raw_rssi=n.get("rssi") if "rssi" in n else None
    raw_signal=n.get("signal") if "signal" in n else None
    raw_signal_dbm=n.get("signal_dbm") if "signal_dbm" in n else None

    source=None
    source_raw=None
    for key,value in (("rssi",raw_rssi),("signal",raw_signal),("signal_dbm",raw_signal_dbm)):
        if _num(value) is not None:
            source=key
            source_raw=value
            break

    provisional,normalized=_normalize_signed_magnitude(source_raw)
    raw_noise=n.get("noise") if "noise" in n else None
    raw_noise_dbm=n.get("noise_dbm") if "noise_dbm" in n else None
    noise,noise_normalized=_normalize_signed_magnitude(raw_noise if _num(raw_noise) is not None else raw_noise_dbm)

    return {
        "ssid":_first(n,("essid","ssid","name")),
        "bssid":_first(n,("bssid","mac")),
        "channel":_first(n,("channel","channel_number")),
        # Keep the legacy normalized value for compatibility, but mark it
        # provisional and do not treat it as validated dBm in the UI/scoring.
        "rssi":provisional,
        "rssiNormalizedPositiveMagnitude":normalized,
        "signalObservationSource":source,
        "signalObservationRaw":source_raw,
        "provisionalSignal":provisional,
        "rawRssi":raw_rssi,
        "rawSignal":raw_signal,
        "rawSignalDbm":raw_signal_dbm,
        "rawNoise":raw_noise,
        "rawNoiseDbm":raw_noise_dbm,
        "noiseDbm":noise,
        "noiseNormalizedPositiveMagnitude":noise_normalized,
        "band":_neighbor_band(n),
        "radio":_first(n,("radio","radio_name","band")),
        "lastSeen":_first(n,("last_seen","lastSeen","seen")),
        "ageSeconds":_num(_first(n,("age","age_seconds"))),
        "sourceApMac":str(_first(n,("ap_mac","source_ap_mac","reporting_ap_mac","adopted_by")) or "").lower(),
    }


def parse_rf_environment(classic_devices, rogue_aps=None):
    rogue_aps=rogue_aps or []
    neighbors=[_neighbor_row(x) for x in rogue_aps if isinstance(x,dict)]
    rows=[]
    diagnostics=[]

    for d in classic_devices or []:
        if not isinstance(d,dict):
            continue
        configs=d.get("radio_table") or []
        stats=d.get("radio_table_stats") or d.get("radio_stats") or []
        if not configs and not stats:
            continue

        stat_map={}
        for s in stats:
            if not isinstance(s,dict):
                continue
            key=_radio_key(s)
            if key:
                stat_map[key]=s

        seen=set()
        for cfg in configs:
            if not isinstance(cfg,dict):
                continue
            key=_radio_key(cfg)
            st=stat_map.get(key) or {}
            seen.add(key)
            channel=_first(st,("channel","channel_number"))
            if channel is None:
                channel=_first(cfg,("channel","channel_number"))
            band=_band_from_radio(key,channel)
            if band is None:
                continue

            total=_num(_first(st,("cu_total","channel_utilization","channel_utilization_pct","cuTotal")))
            self_rx=_num(_first(st,("cu_self_rx","self_rx","self_rx_pct","cuSelfRx")))
            self_tx=_num(_first(st,("cu_self_tx","self_tx","self_tx_pct","cuSelfTx")))
            external=None
            if total is not None and self_rx is not None and self_tx is not None:
                external=max(0.0,total-self_rx-self_tx)

            noise=_num(_first(st,("noise","noise_dbm","noiseFloor","noise_floor")))
            tx_power=_num(_first(st,("tx_power","txPower","tx_power_dbm")))
            if tx_power is None:
                tx_power=_num(_first(cfg,("tx_power","txPower")))
            clients=_num(_first(st,("num_sta","numStations","client_count","clientCount")))
            retries=_num(_first(st,("tx_retries_pct","txRetriesPct","retry_pct","retryPct")))

            ap_mac=str(d.get("mac") or "").lower()
            matching=[n for n in neighbors if n.get("band")==band and (not n.get("sourceApMac") or n.get("sourceApMac")==ap_mac)]
            rows.append({
                "apMac":ap_mac,
                "apName":d.get("name") or d.get("model") or d.get("mac"),
                "model":d.get("model"),
                "radioName":key,
                "band":band,
                "channel":int(channel) if str(channel).isdigit() else channel,
                "widthMHz":_num(_first(cfg,("ht","channel_width","channelWidthMHz"))),
                "channelUtilizationPct":total,
                "selfRxPct":self_rx,
                "selfTxPct":self_tx,
                "externalBusyPct":external,
                "noiseDbm":noise,
                "txPowerDbm":tx_power,
                "clientCount":int(clients) if clients is not None else None,
                "txRetriesPct":retries,
                "neighborCount":len(matching),
            })

        for key,st in stat_map.items():
            if key in seen:
                continue
            channel=_first(st,("channel","channel_number"))
            band=_band_from_radio(key,channel)
            if band is None:
                continue
            total=_num(_first(st,("cu_total","channel_utilization","channel_utilization_pct","cuTotal")))
            self_rx=_num(_first(st,("cu_self_rx","self_rx","self_rx_pct","cuSelfRx")))
            self_tx=_num(_first(st,("cu_self_tx","self_tx","self_tx_pct","cuSelfTx")))
            external=max(0.0,total-self_rx-self_tx) if None not in (total,self_rx,self_tx) else None
            rows.append({
                "apMac":str(d.get("mac") or "").lower(),
                "apName":d.get("name") or d.get("model") or d.get("mac"),
                "model":d.get("model"),
                "radioName":key,
                "band":band,
                "channel":channel,
                "widthMHz":None,
                "channelUtilizationPct":total,
                "selfRxPct":self_rx,
                "selfTxPct":self_tx,
                "externalBusyPct":external,
                "noiseDbm":_num(_first(st,("noise","noise_dbm","noiseFloor","noise_floor"))),
                "txPowerDbm":_num(_first(st,("tx_power","txPower","tx_power_dbm"))),
                "clientCount":_num(_first(st,("num_sta","numStations","client_count","clientCount"))),
                "txRetriesPct":_num(_first(st,("tx_retries_pct","txRetriesPct","retry_pct","retryPct"))),
                "neighborCount":len([n for n in neighbors if n.get("band")==band and (not n.get("sourceApMac") or n.get("sourceApMac")==str(d.get("mac") or "").lower())]),
            })

        diagnostics.append({
            "apName":d.get("name") or d.get("model") or d.get("mac"),
            "deviceKeys":sorted(str(k) for k in d.keys()),
            "radioConfigKeys":sorted({str(k) for r in configs if isinstance(r,dict) for k in r.keys()}),
            "radioStatKeys":sorted({str(k) for r in stats if isinstance(r,dict) for k in r.keys()}),
        })

    rssi_normalized=sum(1 for n in neighbors if n.get("rssiNormalizedPositiveMagnitude"))
    noise_normalized=sum(1 for n in neighbors if n.get("noiseNormalizedPositiveMagnitude"))
    rssi_missing=sum(1 for n in neighbors if n.get("provisionalSignal") is None)
    raw_rssi_count=sum(1 for n in neighbors if n.get("rawRssi") not in (None,""))
    raw_signal_count=sum(1 for n in neighbors if n.get("rawSignal") not in (None,""))
    raw_signal_dbm_count=sum(1 for n in neighbors if n.get("rawSignalDbm") not in (None,""))
    paired_rssi_signal=sum(1 for n in neighbors if n.get("rawRssi") not in (None,"") and n.get("rawSignal") not in (None,""))

    signal_examples=[]
    for n in neighbors:
        if len(signal_examples)>=12:
            break
        if all(n.get(k) in (None,"") for k in ("rawRssi","rawSignal","rawSignalDbm")):
            continue
        signal_examples.append({
            "ssid":n.get("ssid"),
            "bssid":n.get("bssid"),
            "band":n.get("band"),
            "channel":n.get("channel"),
            "rawRssi":n.get("rawRssi"),
            "rawSignal":n.get("rawSignal"),
            "rawSignalDbm":n.get("rawSignalDbm"),
            "source":n.get("signalObservationSource"),
            "sourceRaw":n.get("signalObservationRaw"),
            "provisionalSignal":n.get("provisionalSignal"),
            "normalizedPositiveMagnitude":bool(n.get("rssiNormalizedPositiveMagnitude")),
        })

    return {
        "radios":rows,
        "neighbors":neighbors,
        "diagnostics":diagnostics,
        "dataQuality":{
            "neighborRssiValidated":False,
            "neighborRssiPositiveMagnitudeNormalized":rssi_normalized,
            "neighborNoisePositiveMagnitudeNormalized":noise_normalized,
            "neighborRssiMissingOrInvalid":rssi_missing,
            "neighborRawRssiCount":raw_rssi_count,
            "neighborRawSignalCount":raw_signal_count,
            "neighborRawSignalDbmCount":raw_signal_dbm_count,
            "neighborPairedRssiSignalCount":paired_rssi_signal,
            "signalExamples":signal_examples,
            "detail":"Raw rogue-AP rssi, signal, and signal_dbm fields are captured separately. A provisional normalized signal is shown without claiming dBm semantics, and no neighbor signal field is used to choose or score channels until the U7/controller field meaning is independently validated."
        },
    }
