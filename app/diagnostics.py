"""Read-only client roaming and RF automation explanations.

Do not infer the best AP from association counts or unvalidated signal fields.
This module does not change UniFi radio settings.
"""
from collections import defaultdict
from datetime import datetime, timezone, timedelta


ACTIVE_RF_STATUSES = frozenset(("PROPOSED", "MONITORING", "ROLLBACK_REQUIRED", "ROLLBACK_MONITORING"))


def _recent_time(value, cutoff):
    if not value:
        return False
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp >= cutoff
    except (ValueError, TypeError, OverflowError):
        return False


def build_roaming_diagnostics(states, live_clients, events, now=None):
    """Join stored AP changes to live clients; never claim signal is the best AP."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    live_by_id = {str(c.get("id")): c for c in live_clients if c.get("id")}
    live_by_mac = {str(c.get("macAddress")).lower(): c for c in live_clients if c.get("macAddress")}
    event_by_id = defaultdict(list)
    for event in events:
        if _recent_time(event.get("ts"), cutoff):
            event_by_id[str(event.get("client_id"))].append(event)

    result = []
    for state in states:
        row = dict(state)
        live = (live_by_id.get(str(row.get("clientId")))
                or live_by_mac.get(str(row.get("macAddress") or "").lower()))
        changes = sorted(event_by_id.get(str(row.get("clientId")), []), key=lambda e: e.get("ts") or "")
        # These events are a bounded recent-events sample, not a complete history.
        # Only describe a bounce when two consecutive observations establish A -> B -> A.
        bounces = sum(
            1 for a, b in zip(changes, changes[1:])
            if a.get("from_ap_id") and a.get("to_ap_id")
            and a.get("from_ap_id") == b.get("to_ap_id")
            and a.get("to_ap_id") == b.get("from_ap_id")
        )
        signal = live.get("signalDbm") if live else None
        signal = float(signal) if isinstance(signal, (int, float)) and -100 <= signal <= -15 else None
        count = int(row.get("roamCount24h") or 0)
        connected = live is not None
        advice = []
        if not connected:
            advice.append("Not currently connected; association history may be stale.")
        if count >= 8:
            advice.append("Frequent AP changes: inspect placement, band and nearby AP signal before changing channels.")
        if bounces:
            advice.append("Back-and-forth AP changes observed in the recent event sample.")
        if connected and signal is not None and signal <= -75:
            advice.append("Current classic client signal is weak; check coverage and physical placement.")
        elif connected and signal is None and count >= 3:
            advice.append("Current RSSI unavailable; check this client in UniFi before selecting a preferred AP.")
        row.update({
            "connectedNow": connected,
            "signalDbm": signal,
            "signalSource": "classic_client" if signal is not None else None,
            "channel": live.get("channel") if live else None,
            "ssid": live.get("ssid") if live else None,
            "recentBounceCount": bounces,
            "diagnostic": " ".join(advice) or "No unusual roaming identified from the available observations.",
        })
        result.append(row)
    return sorted(result, key=lambda c: (-int(c.get("roamCount24h") or 0), str(c.get("name") or "").lower()))


def rf_execution_state(enabled, configured, write_verified, plan, tests, sample_at=None, sample_error=None):
    """Describe the real Auto RF gate; never describe advisory as an applied change."""
    plan = plan or {}
    items = plan.get("items") or []
    tests = tests or []
    active = [t for t in tests if t.get("status") in ACTIVE_RF_STATUSES]
    rollbacks = [t for t in active if t.get("status") == "ROLLBACK_REQUIRED"]
    candidates = [x for x in items if x.get("status") == "CONSIDER_CHANGE" and x.get("testableChange")]
    scan_backed = [x for x in candidates if x.get("scanBackedRecommendation")]
    blockers = []
    if not configured:
        blockers.append("Private/classic API credentials unavailable")
    if not write_verified:
        blockers.append("Private RF write path not validated")
    if sample_error:
        blockers.append("Passive RF collection: " + str(sample_error))
    result = {
        "enabled": bool(enabled),
        "phase": "DISABLED",
        "label": "Auto RF disabled",
        "detail": "Read-only RF monitoring and channel recommendations remain available.",
        "candidateCount": len(candidates),
        "scanBackedCandidateCount": len(scan_backed),
        "activeTestCount": len(active),
        "activeTests": [{"id": t.get("id"), "apName": t.get("ap_name"),
                         "band": t.get("band"), "status": t.get("status"),
                         "phase": t.get("phase")} for t in active],
        "lastPassiveSampleAt": sample_at,
        "blockers": blockers,
        "automaticScanEnabled": False,
    }
    if rollbacks:
        result.update(phase="ROLLBACK_REQUIRED", label="RF rollback needs attention",
                      detail="A test is awaiting verification that its original channel/width is restored. Check the test card before starting another change.")
    elif active:
        status = active[0].get("status")
        result.update(phase="ACTIVE_TEST", label="A/B/A test in progress",
                      detail="Monitoring the active RF test (" + str(status) + "). Only one radio should change at a time.")
    elif not enabled:
        pass
    elif not configured or not write_verified:
        result.update(phase="BLOCKED", label="Auto RF blocked",
                      detail="Controller credentials and verified radio-write access are required. No automatic channel changes are eligible.")
    elif candidates:
        result.update(phase="CANDIDATES", label="RF candidates available",
                      detail=str(len(candidates)) + " candidate(s) need A/B/A testing. " +
                      (str(len(scan_backed)) + " scan-backed; " if scan_backed else "None scan-backed; ") +
                      "no change is considered proven until measured and rollback-verified.")
    else:
        result.update(phase="MONITORING", label="Monitoring — no eligible RF change",
                      detail="The planner currently recommends keeping or investigating the radios. Auto RF does not force an unnecessary channel change.")
    return result
