import json
import requests


def _extract_output_text(data):
    if isinstance(data,dict) and isinstance(data.get("output_text"),str):
        return data.get("output_text")
    parts=[]
    for item in (data.get("output") or []) if isinstance(data,dict) else []:
        if not isinstance(item,dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content,dict):
                continue
            if content.get("type") in ("output_text","text") and content.get("text"):
                parts.append(str(content.get("text")))
    return "\n".join(parts).strip()


def build_ai_input(context):
    audit=context.get("networkAudit") or {}
    wired=context.get("wiredAudit") or {}
    wan=context.get("wanQuality24h") or {}
    traffic=context.get("traffic24h") or {}
    speed=context.get("speedtest") or {}
    rf_environment=context.get("rfEnvironment24h") or {}
    snapshot=context.get("snapshot") or {}

    compact={
        "generatedAt":context.get("generatedAt"),
        "version":context.get("version"),
        "inventory":{
            "devices":[{
                "name":d.get("name"),
                "model":d.get("model"),
                "state":d.get("state"),
                "optimizerType":d.get("optimizerType"),
                "clientCount":d.get("clientCount"),
                "interfaces":d.get("interfaces"),
                "statistics":d.get("statistics"),
            } for d in (snapshot.get("devices") or [])],
            "clients":[{
                "name":c.get("name"),
                "type":c.get("type"),
                "ipAddress":c.get("ipAddress"),
                "macAddress":c.get("macAddress"),
                "vlanId":c.get("vlanId"),
                "networkName":c.get("networkName"),
                "ssid":c.get("ssid"),
                "uplinkDeviceName":c.get("uplinkDeviceName"),
                "switchPort":c.get("switchPort"),
            } for c in (snapshot.get("clients") or [])],
            "networks":snapshot.get("networks") or [],
            "wifiBroadcasts":snapshot.get("wifiBroadcasts") or [],
        },
        "audit":{
            "overallScore":audit.get("overallScore"),
            "scores":audit.get("scores"),
            "counts":audit.get("counts"),
            "findings":audit.get("findings"),
        },
        "wired":{
            "score":wired.get("score"),
            "summary":wired.get("summary"),
            "ports":[{
                "deviceName":p.get("deviceName"),
                "portIdx":p.get("portIdx"),
                "endpointName":p.get("endpointName"),
                "endpointIp":p.get("endpointIp"),
                "endpointNetwork":p.get("endpointNetwork"),
                "endpointVlan":p.get("endpointVlan"),
                "speedMbps":p.get("speedMbps"),
                "maxSpeedMbps":p.get("maxSpeedMbps"),
                "poeState":p.get("poeState"),
                "poePowerW":p.get("poePowerW"),
                "errorDelta":p.get("errorDelta"),
                "dropDelta":p.get("dropDelta"),
                "stateChanges24h":p.get("stateChanges24h"),
                "speedChanges24h":p.get("speedChanges24h"),
                "status":p.get("status"),
                "reason":p.get("reason"),
            } for p in (wired.get("ports") or []) if p.get("state")=="UP"],
        },
        "wanQuality24h":{
            "reachabilityPct":wan.get("reachabilityPct"),
            "avgLatencyMs":wan.get("avgLatencyMs"),
            "avgJitterMs":wan.get("avgJitterMs"),
            "dnsSuccessPct":wan.get("dnsSuccessPct"),
            "dnsAvgLatencyMs":wan.get("dnsAvgLatencyMs"),
            "targets":wan.get("targets"),
        },
        "speedtest":{
            "latestSuccess":speed.get("latestSuccess"),
            "stats":speed.get("stats"),
        },
        "traffic":{
            "usage":traffic.get("usage"),
            "dpi":traffic.get("dpi"),
        },
        "rfEnvironment":{
            "latest":rf_environment.get("latest"),
            "averages":rf_environment.get("averages"),
            "neighbors":rf_environment.get("neighbors"),
            "lastSampleAt":rf_environment.get("lastSampleAt"),
            "lastError":rf_environment.get("lastError"),
        },
        "optimizationTests":context.get("optimizationTests") or [],
        "automationState":context.get("automationState") or {},
        "channelPlan":context.get("channelPlan") or {},
    }
    return json.dumps(compact,separators=(",",":"),default=str)


SYSTEM_PROMPT="""You are the embedded advisor for a homeowner's UniFi network optimizer.
Analyze only the supplied telemetry and configuration summary.

Priorities, in order:
1. stability and avoiding outages,
2. security and segmentation,
3. wired reliability,
4. Wi-Fi reliability/roaming,
5. WAN quality,
6. performance tuning.

Rules:
- Never claim a setting is wrong when the telemetry only supports review.
- Distinguish observed facts from hypotheses.
- Do not recommend changing several RF variables at once.
- Treat existing A/B/A verification as the required method for RF changes.
- Do not recommend disabling security protections merely to improve speed.
- Do not expose or ask for credentials.
- Prefer reversible, low-risk actions.
- The AI is advisory. Do not claim that you changed any setting.
- When a deterministic automation already exists (Auto RF or Auto Optimize), say whether it is a suitable execution path.
- Auto Optimize only enables Band Steering and BSS Transition on eligible STANDARD Wi-Fi broadcasts. Do not describe it as a general execution path for other network changes.
- Use automationState.autoOptimizeCapabilities and automationState.autoRfCapabilities as the authoritative execution scope.
- Auto RF is an experimental validated private/classic UniFi API path, not an official/supported radio-write API. Never call Auto RF an official execution path.
- Treat channelPlan.automaticRadioWritesAvailable as describing the supported official API only. Use automationState to determine whether the validated private/classic Auto RF path is actually available.
- Use optimizationTests as historical evidence. Do not recommend repeating a previously completed WORSE_CONFIRMED, WORSE_TOPOLOGY, INVALID_NO_CHANGE, or clearly worse test unless you can identify a materially changed condition and explain why a retest is justified.
- If a prior RF test already produced a confirmed result, prefer that evidence over a generic planner recommendation.
- Use passive RF environment telemetry (channel utilization, external busy time, noise and neighboring BSS observations) as supporting evidence when present. Do not invent missing RF scan data.
- Distinguish learned history since app restart from long-term evidence when the supplied data does not establish how long a counter has been observed.
- Do not promote REVIEW-only findings into a recommendation to enable/disable a feature unless the supplied telemetry establishes a concrete benefit or a security requirement. For DHCP guarding, disabled firewall policies, client isolation, MLO and similar context-dependent settings, use language such as "review", "confirm intent", or "consider after validation" unless there is stronger evidence.
- A disabled policy is not evidence that it should be enabled. State the observed disabled status and what must be confirmed before any change.
- For wired link state/speed changes, treat a small number of changes with zero current error/drop deltas as a watch item unless there is repeated recurrence, active degradation, or corroborating evidence.

Return concise plain text with these sections:
NETWORK STATUS
TOP FINDINGS
SAFE AUTOMATIONS
APPROVAL-REQUIRED CHANGES
WATCH / NO ACTION
Include at most 8 findings total."""


def analyze_with_openai(api_key, model, context, timeout=90):
    if not api_key:
        return {"ok":False,"error":"OPENAI_API_KEY is not configured"}
    payload={
        "model":model,
        "store":False,
        "input":[
            {"role":"system","content":SYSTEM_PROMPT},
            {"role":"user","content":"Analyze this current UniFi Home Optimizer snapshot:\n"+build_ai_input(context)},
        ],
        "max_output_tokens":2200,
    }
    try:
        r=requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization":"Bearer "+api_key,
                "Content-Type":"application/json",
            },
            json=payload,
            timeout=timeout,
        )
        try:
            data=r.json()
        except Exception:
            data={"raw":r.text[:4000]}
        if not (200 <= r.status_code < 300):
            err=(data.get("error") or {}).get("message") if isinstance(data,dict) else None
            return {"ok":False,"status":r.status_code,"error":err or str(data)[:1000]}
        text=_extract_output_text(data)
        if not text:
            return {"ok":False,"status":r.status_code,"error":"OpenAI response contained no text output"}
        return {
            "ok":True,
            "model":data.get("model") or model,
            "responseId":data.get("id"),
            "text":text,
            "usage":data.get("usage"),
        }
    except Exception as e:
        return {"ok":False,"error":str(e)}


PROPOSAL_PROMPT="""You generate an approval queue for a homeowner's UniFi network optimizer.
Use only the supplied snapshot. Return JSON only, with this exact top-level shape:
{"proposals":[...]}

Allowed actionType values:
- RF_ABA_TEST
- AUTO_OPTIMIZE_RUN
- REVIEW_SETTING

Rules:
- Maximum 5 proposals.
- Propose nothing merely to fill the queue.
- RF_ABA_TEST is allowed only for a current channelPlan item with testableChange=true and status=CONSIDER_CHANGE, only one RF variable/change set at a time, and only when stored RF history does not already establish that the same change is worse. Params must contain apId, apName, band, proposedChannel, proposedWidthMHz.
- AUTO_OPTIMIZE_RUN is allowed only when the supplied data shows an eligible STANDARD Wi-Fi broadcast needs Band Steering or BSS Transition enabled. It has no params.
- REVIEW_SETTING never changes the network. Use it for firewall, VLAN, DHCP guarding, client isolation, MLO, credentials, WAN, security or any other setting outside the two whitelisted execution paths. Params may include a short setting identifier.
- Do not infer endpoint capabilities.
- Do not propose an active RF/spectrum scan.
- Auto RF uses the validated private/classic path and is not an official radio-write API.
- Include title, reason, risk, rollback, actionType, params for every proposal.
- risk must be LOW, MEDIUM, or REVIEW.
- rollback must explain what the deterministic execution path will do or say "No automatic change" for REVIEW_SETTING.
"""


def _extract_json_object(text):
    if not text:
        return None
    raw=text.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start=raw.find("{")
    end=raw.rfind("}")
    if start>=0 and end>start:
        try:
            return json.loads(raw[start:end+1])
        except Exception:
            return None
    return None


def generate_ai_proposals(api_key, model, context, timeout=90):
    if not api_key:
        return {"ok":False,"error":"OPENAI_API_KEY is not configured"}
    payload={
        "model":model,
        "store":False,
        "input":[
            {"role":"system","content":PROPOSAL_PROMPT},
            {"role":"user","content":"Build the approval queue from this current network snapshot:\n"+build_ai_input(context)},
        ],
        "max_output_tokens":1800,
    }
    try:
        r=requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization":"Bearer "+api_key,
                "Content-Type":"application/json",
            },
            json=payload,
            timeout=timeout,
        )
        try:
            data=r.json()
        except Exception:
            data={"raw":r.text[:4000]}
        if not (200 <= r.status_code < 300):
            err=(data.get("error") or {}).get("message") if isinstance(data,dict) else None
            return {"ok":False,"status":r.status_code,"error":err or str(data)[:1000]}
        text=_extract_output_text(data)
        parsed=_extract_json_object(text)
        if not isinstance(parsed,dict):
            return {"ok":False,"error":"AI proposal response was not valid JSON"}
        proposals=parsed.get("proposals") or []
        if not isinstance(proposals,list):
            return {"ok":False,"error":"AI proposal response did not contain a proposals list"}

        allowed={"RF_ABA_TEST","AUTO_OPTIMIZE_RUN","REVIEW_SETTING"}
        clean=[]
        for p in proposals[:5]:
            if not isinstance(p,dict):
                continue
            action=str(p.get("actionType") or "")
            if action not in allowed:
                continue
            clean.append({
                "actionType":action,
                "title":str(p.get("title") or action)[:200],
                "reason":str(p.get("reason") or "")[:2000],
                "risk":str(p.get("risk") or "REVIEW").upper()[:20],
                "rollback":str(p.get("rollback") or "No automatic change")[:1500],
                "params":p.get("params") if isinstance(p.get("params"),dict) else {},
            })
        return {
            "ok":True,
            "model":data.get("model") or model,
            "proposals":clean,
            "usage":data.get("usage"),
        }
    except Exception as e:
        return {"ok":False,"error":str(e)}
