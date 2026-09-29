import io
import json
import zipfile
from datetime import datetime, timezone


SENSITIVE_FRAGMENTS=(
    "password","passphrase","secret","psk","pre_shared",
    "token","api_key","apikey","private_key","credential",
    "authorization","cookie"
)


def _is_sensitive_key(key):
    k=str(key or "").lower().replace("-","_")
    return any(fragment in k for fragment in SENSITIVE_FRAGMENTS)


def sanitize(value):
    if isinstance(value,dict):
        out={}
        for k,v in value.items():
            if _is_sensitive_key(k):
                out[k]="[REDACTED]"
            else:
                out[k]=sanitize(v)
        return out
    if isinstance(value,list):
        return [sanitize(x) for x in value]
    if isinstance(value,tuple):
        return [sanitize(x) for x in value]
    return value


def compact_support_summary(payload):
    audit=payload.get("networkAudit") or {}
    wired=payload.get("wiredAudit") or {}
    wan=payload.get("wanQuality24h") or {}
    speed=payload.get("speedtest") or {}
    snapshot=payload.get("snapshot") or {}
    ai=payload.get("ai") or {}
    counts=audit.get("counts") or {}
    scores=audit.get("scores") or {}
    ws=wired.get("summary") or {}
    latest_speed=speed.get("latestSuccess") or {}

    lines=[
        "UniFi Home Optimizer support summary",
        f"Generated: {payload.get('generatedAt')}",
        f"App version: {payload.get('version')}",
        "",
        "Inventory",
        f"- UniFi devices: {len(snapshot.get('devices') or [])}",
        f"- Clients: {len(snapshot.get('clients') or [])}",
        f"- Networks/VLANs: {len(snapshot.get('networks') or [])}",
        f"- Wi-Fi broadcasts: {len(snapshot.get('wifiBroadcasts') or [])}",
        "",
        "Network audit",
        f"- Overall: {audit.get('overallScore','—')}",
        f"- Critical: {counts.get('CRITICAL',0)}",
        f"- Warnings: {counts.get('WARNING',0)}",
        f"- Review: {counts.get('REVIEW',0)}",
        f"- Security: {scores.get('SECURITY','—')}",
        f"- Firewall: {scores.get('FIREWALL','—')}",
        f"- Wi-Fi: {scores.get('WIFI','—')}",
        f"- Wired: {scores.get('WIRED','—')}",
        f"- WAN: {scores.get('WAN','—')}",
        "",
        "Wired",
        f"- Score: {wired.get('score','—')}",
        f"- Active ports: {ws.get('active',0)}",
        f"- Warnings: {ws.get('warning',0)}",
        f"- Review: {ws.get('review',0)}",
        f"- Expected low-speed: {ws.get('normal',0)}",
        f"- Flapping/changing: {ws.get('flapping',0)}",
        "",
        "WAN quality (24h)",
        f"- Reachability: {wan.get('reachabilityPct','—')}",
        f"- Avg latency ms: {wan.get('avgLatencyMs','—')}",
        f"- Avg jitter ms: {wan.get('avgJitterMs','—')}",
        f"- DNS success: {wan.get('dnsSuccessPct','—')}",
        "",
        "Latest speed test",
        f"- Download Mbps: {latest_speed.get('download_mbps','—')}",
        f"- Upload Mbps: {latest_speed.get('upload_mbps','—')}",
        f"- Ping ms: {latest_speed.get('ping_ms','—')}",
        f"- Jitter ms: {latest_speed.get('jitter_ms','—')}",
        f"- Packet loss %: {latest_speed.get('packet_loss_pct','—')}",
        f"- Server: {latest_speed.get('server_sponsor') or latest_speed.get('server_name') or '—'}",
        "",
        "AI",
        f"- Configured: {ai.get('configured',False)}",
        f"- Model: {ai.get('model','—')}",
        f"- Automatic analysis: {ai.get('automaticEnabled',False)}",
        "",
        "Privacy",
        "- API keys, passwords, tokens, secrets and credentials are recursively redacted.",
        "- Local device names, MAC addresses and private IP addresses remain because they are useful for troubleshooting.",
    ]
    return "\n".join(lines)+"\n"


def build_json_bytes(payload):
    safe=sanitize(payload)
    return json.dumps(safe,indent=2,sort_keys=True,default=str).encode("utf-8")


def build_zip_bytes(payload):
    safe=sanitize(payload)
    generated=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    files={
        "README.txt":compact_support_summary(safe),
        "support-bundle.json":json.dumps(safe,indent=2,sort_keys=True,default=str),
        "network-audit.json":json.dumps(safe.get("networkAudit") or {},indent=2,sort_keys=True,default=str),
        "wired-audit.json":json.dumps(safe.get("wiredAudit") or {},indent=2,sort_keys=True,default=str),
        "wan-quality-24h.json":json.dumps(safe.get("wanQuality24h") or {},indent=2,sort_keys=True,default=str),
        "rf-environment-24h.json":json.dumps(safe.get("rfEnvironment24h") or {},indent=2,sort_keys=True,default=str),
        "traffic-24h.json":json.dumps(safe.get("traffic24h") or {},indent=2,sort_keys=True,default=str),
        "speedtest.json":json.dumps(safe.get("speedtest") or {},indent=2,sort_keys=True,default=str),
        "snapshot.json":json.dumps(safe.get("snapshot") or {},indent=2,sort_keys=True,default=str),
        "recent-log.json":json.dumps(safe.get("recentLog") or [],indent=2,sort_keys=True,default=str),
        "ai-proposals.json":json.dumps(safe.get("aiProposals") or [],indent=2,sort_keys=True,default=str),
    }
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name,text in files.items():
            z.writestr(name,text)
        z.writestr("manifest.json",json.dumps({
            "generatedAt":safe.get("generatedAt"),
            "version":safe.get("version"),
            "bundleFormat":"1",
            "privacy":"Secrets recursively redacted; local troubleshooting identifiers retained.",
            "suggestedFilename":f"unifi-optimizer-support-{generated}.zip",
        },indent=2))
    bio.seek(0)
    return bio
