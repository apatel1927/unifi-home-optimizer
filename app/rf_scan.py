from datetime import datetime, timezone


RADIO_BANDS={"ng":2.4,"na":5.0,"6e":6.0}


def _num(value):
    try:
        if value is None or value=="":
            return None
        return float(value)
    except Exception:
        return None


def _int(value):
    n=_num(value)
    return int(n) if n is not None else None


def _epoch_seconds(value):
    n=_num(value)
    if n is None:
        return None
    if n > 10_000_000_000:
        n=n/1000.0
    return float(n)


def _age_seconds(epoch):
    if epoch is None:
        return None
    try:
        return max(0.0,datetime.now(timezone.utc).timestamp()-float(epoch))
    except Exception:
        return None


def _iso_time(epoch):
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(float(epoch),timezone.utc).isoformat()
    except Exception:
        return None


def normalize_spectrum_scan(items, ap_mac=None, ap_name=None, ap_id=None, model=None):
    """Normalize UniFi classic spectrum-scan state into stable planner/UI fields."""
    if isinstance(items,dict):
        items=[items]
    items=items or []
    output={
        "apMac":str(ap_mac or "").lower().replace("-",":"),
        "apName":ap_name,
        "apId":ap_id,
        "model":model,
        "inProgress":False,
        "available":False,
        "latestScanAt":None,
        "latestScanEpoch":None,
        "bands":[],
        "rowCount":0,
    }

    by_radio={}
    newest=None
    for item in items:
        if not isinstance(item,dict):
            continue
        if item.get("spectrum_scanning") is True or item.get("spectrumScanning") is True:
            output["inProgress"]=True
        scans=item.get("scans") or item.get("scan") or []
        if isinstance(scans,dict):
            scans=[scans]
        for scan in scans:
            if not isinstance(scan,dict):
                continue
            radio=str(scan.get("radio") or scan.get("radio_name") or "").lower()
            band=RADIO_BANDS.get(radio)
            if band is None:
                raw_band=_num(scan.get("band") or scan.get("frequencyGHz"))
                if raw_band in (2.4,5.0,6.0):
                    band=raw_band
            if band is None:
                continue
            table=scan.get("spectrum_table") or scan.get("spectrumTable") or []
            if not isinstance(table,list):
                table=[]
            epoch=_epoch_seconds(scan.get("spectrum_table_time") or scan.get("spectrumTableTime"))
            if epoch is not None and (newest is None or epoch>newest):
                newest=epoch
            key=(radio,band,epoch)
            bucket=by_radio.setdefault(key,{
                "radio":radio,
                "band":band,
                "scanEpoch":epoch,
                "scanAt":_iso_time(epoch),
                "ageSeconds":_age_seconds(epoch),
                "rows":[],
            })
            for raw in table:
                if not isinstance(raw,dict):
                    continue
                row={
                    "channel":_int(raw.get("channel")),
                    "centerFreqMHz":_int(raw.get("center_freq") if raw.get("center_freq") is not None else raw.get("centerFreq")),
                    "widthMHz":_int(raw.get("width")),
                    "interferenceDbm":_num(raw.get("interference")),
                    "utilizationPct":_num(raw.get("utilization")),
                    "otherBssCount":_int(raw.get("other_bss_count") if raw.get("other_bss_count") is not None else raw.get("otherBssCount")),
                    "interferenceTypes":raw.get("interference_type") or raw.get("interferenceTypes") or [],
                }
                if row["channel"] is None:
                    continue
                bucket["rows"].append(row)

    output["bands"]=sorted(
        by_radio.values(),
        key=lambda x:(float(x.get("band") or 99),-(x.get("scanEpoch") or 0))
    )
    output["rowCount"]=sum(len(x.get("rows") or []) for x in output["bands"])
    output["available"]=output["rowCount"]>0
    output["latestScanEpoch"]=newest
    output["latestScanAt"]=_iso_time(newest)
    output["latestAgeSeconds"]=_age_seconds(newest)
    return output


def scan_summary(scans, max_age_seconds=86400):
    scans=scans or []
    available=[x for x in scans if x.get("available")]
    fresh=[x for x in available if x.get("latestAgeSeconds") is not None and x.get("latestAgeSeconds")<=max_age_seconds]
    newest=max((x.get("latestScanEpoch") or 0 for x in available),default=0) or None
    return {
        "accessPoints":scans,
        "availableCount":len(available),
        "freshCount":len(fresh),
        "freshMaxAgeSeconds":max_age_seconds,
        "latestScanEpoch":newest,
        "latestScanAt":_iso_time(newest),
        "latestAgeSeconds":_age_seconds(newest),
    }
