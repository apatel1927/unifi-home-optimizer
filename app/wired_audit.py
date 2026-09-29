def _norm_mac(value):
    return str(value or "").lower().replace("-",":").strip()


def _num(value):
    try:
        if value in (None,""):
            return None
        return float(value)
    except Exception:
        return None


def _first(d, keys, default=None):
    if not isinstance(d,dict):
        return default
    for k in keys:
        if k in d and d.get(k) not in (None,""):
            return d.get(k)
    return default


def _port_idx(p):
    v=_first(p,("port_idx","port","idx","portIdx","index"))
    try:
        return int(v) if v is not None else None
    except Exception:
        return None


def _port_speed(p):
    return _num(_first(p,("speed","speed_mbps","speedMbps","link_speed")))


def _port_max_speed(p):
    return _num(_first(p,("max_speed","max_speed_mbps","maxSpeedMbps","supported_speed")))


def _port_state(p):
    state=str(_first(p,("state","port_state"),"")).upper()
    if state:
        if state in ("UP","CONNECTED","FORWARDING"):
            return "UP"
        if state in ("DOWN","DISCONNECTED","BLOCKED","DISABLED"):
            return state
    up=_first(p,("up","is_up","link_up"))
    if isinstance(up,bool):
        return "UP" if up else "DOWN"
    speed=_port_speed(p)
    return "UP" if speed and speed>0 else "DOWN"


def _rate_bps(p, direction):
    raw=_first(p,(
        direction+"_bytes-r",
        direction+"_bytes_r",
        direction+"BytesRate",
        direction+"_rate_bps",
        direction+"RateBps",
    ))
    n=_num(raw)
    if n is None:
        return None
    # Classic rx_bytes-r / tx_bytes-r are byte rates.
    if direction+"_bytes-r" in p or direction+"_bytes_r" in p or direction+"BytesRate" in p:
        return n*8.0
    return n


def _counter(p, keys):
    n=_num(_first(p,keys))
    return int(n) if n is not None and n>=0 else None


def _poe_info(p):
    enabled=_first(p,("poe_enable","poeEnabled","poe_enabled"))
    mode=_first(p,("poe_mode","poeMode"))
    power=_num(_first(p,("poe_power","poePower","poe_power_w","poePowerW")))
    voltage=_num(_first(p,("poe_voltage","poeVoltage")))
    current=_num(_first(p,("poe_current","poeCurrent")))
    explicit_fault=_first(p,(
        "poe_fault","poeFault","poe_fault_status","poeFaultStatus",
        "poe_overload","poeOverload","poe_error","poeError"
    ))
    mode_text=str(mode or "").lower()

    # Some UniFi classic payloads expose poe_good=false on ports that are merely
    # not delivering power. Do not treat that field alone as a fault.
    if explicit_fault not in (None,False,0,"","none","NONE","ok","OK"):
        state="FAULT"
    elif power is not None and power>0:
        state="POWERING"
    elif enabled is True or mode_text not in ("","off","disabled","none"):
        state="ENABLED"
    else:
        state="OFF"
    return {
        "state":state,
        "powerW":power,
        "voltageV":voltage,
        "currentMa":current,
        "mode":mode,
    }


def _likely_low_speed_endpoint(name, network):
    text=(str(name or "")+" "+str(network or "")).lower()
    hints=(
        "iot","cctv","camera","doorbell","thermostat","security","alarm",
        "garage","opener","washer","dryer","refrigerator","microwave",
        "roku","tv","door","backyard","driveway","lutron","hub","bridge",
        "mag","stream","media","receiver","speaker","smart"
    )
    return any(x in text for x in hints)


def _device_max_link(device):
    speeds=[]
    for p in ((device.get("interfaces") or {}).get("ports") or []):
        n=_num(p.get("maxSpeedMbps"))
        if n:
            speeds.append(n)
    return max(speeds) if speeds else None


def _classic_child_parent(child):
    uplink=child.get("uplink") or {}
    parent_mac=_first(uplink,(
        "uplink_device_mac","device_mac","remote_device_mac","parent_mac"
    )) or _first(child,("uplink_device_mac","parent_mac"))
    remote_port=_first(uplink,(
        "uplink_remote_port","uplink_remote_port_idx","remote_port","remote_port_idx","port_idx"
    )) or _first(child,("uplink_remote_port","uplink_remote_port_idx"))
    try:
        remote_port=int(remote_port) if remote_port is not None else None
    except Exception:
        remote_port=None
    return _norm_mac(parent_mac),remote_port


def _port_profile(p):
    return _first(p,(
        "portconf_name","profile_name","portProfileName","network_name","native_network_name"
    ))


def _native_vlan(p):
    return _first(p,("native_vlan","nativeVlan","vlan","vlan_id","vlanId"))


def _build_endpoint_maps(snapshot, classic_clients, classic_devices):
    clients={}
    for c in classic_clients or []:
        sw=_norm_mac(c.get("sw_mac"))
        port=c.get("sw_port")
        try:
            port=int(port) if port is not None else None
        except Exception:
            port=None
        if sw and port is not None:
            clients[(sw,port)]={
                "type":"CLIENT",
                "key":_norm_mac(c.get("mac")) or str(c.get("_id") or ""),
                "name":c.get("name") or c.get("hostname") or c.get("mac") or "Wired client",
                "ip":c.get("ip"),
                "mac":_norm_mac(c.get("mac")),
                "network":c.get("network") or c.get("network_name"),
                "vlan":c.get("vlan"),
                "model":c.get("dev_cat") or c.get("dev_id"),
            }

    devices_by_mac={_norm_mac(d.get("macAddress") or d.get("mac")):d for d in snapshot.get("devices",[]) if d.get("macAddress") or d.get("mac")}
    classic_by_mac={_norm_mac(d.get("mac")):d for d in classic_devices or [] if d.get("mac")}
    children={}
    for cmac,cdev in classic_by_mac.items():
        parent_mac,parent_port=_classic_child_parent(cdev)
        if not parent_mac or parent_port is None:
            continue
        official=devices_by_mac.get(cmac) or {}
        children[(parent_mac,parent_port)]={
            "type":"UNIFI_DEVICE",
            "key":official.get("id") or cmac,
            "deviceId":official.get("id"),
            "name":official.get("name") or cdev.get("name") or cdev.get("model") or cmac,
            "ip":official.get("ipAddress") or cdev.get("ip"),
            "mac":cmac,
            "model":official.get("model") or cdev.get("model"),
            "optimizerType":official.get("optimizerType"),
            "expectedMaxMbps":_device_max_link(official),
        }
    return clients,children


def build_wired_audit(snapshot, classic_devices=None, classic_clients=None, event_summary=None, recent_events=None, counter_summary=None, expectations=None):
    classic_devices=classic_devices or []
    classic_clients=classic_clients or []
    event_summary=event_summary or {}
    recent_events=recent_events or []
    counter_summary=counter_summary or {}
    expectations=expectations or {}
    if isinstance(expectations,list):
        expectations={str(x.get("scope_key")):x for x in expectations if x.get("scope_key")}

    devices=snapshot.get("devices") or []
    official_by_mac={_norm_mac(d.get("macAddress") or d.get("mac")):d for d in devices if d.get("macAddress") or d.get("mac")}
    classic_by_mac={_norm_mac(d.get("mac")):d for d in classic_devices if d.get("mac")}
    client_map,child_map=_build_endpoint_maps(snapshot,classic_clients,classic_devices)

    rows=[]
    links=[]
    counters={"active":0,"good":0,"normal":0,"review":0,"warning":0,"poe":0,"flapping":0}

    for device in devices:
        if device.get("optimizerType") not in ("SWITCH","GATEWAY"):
            continue
        mac=_norm_mac(device.get("macAddress") or device.get("mac"))
        classic=classic_by_mac.get(mac) or {}
        official_ports=((device.get("interfaces") or {}).get("ports") or [])
        official_port_map={_port_idx(op):op for op in official_ports if _port_idx(op) is not None}
        raw_ports=classic.get("port_table") or official_ports
        for p in raw_ports:
            idx=_port_idx(p)
            if idx is None:
                continue
            official_port=official_port_map.get(idx) or {}
            state=_port_state(p)
            speed=_port_speed(p)
            if speed is None:
                speed=_port_speed(official_port)
            max_speed=_port_max_speed(p)
            if max_speed is None:
                max_speed=_port_max_speed(official_port)
            endpoint=child_map.get((mac,idx)) or client_map.get((mac,idx))
            poe=_poe_info(p)
            if poe.get("state")=="POWERING":
                counters["poe"]+=1

            rx_errors=_counter(p,("rx_errors","rxErrors","rx_error","rxErrorCount"))
            tx_errors=_counter(p,("tx_errors","txErrors","tx_error","txErrorCount"))
            rx_drops=_counter(p,("rx_dropped","rxDrops","rx_drop","rxDropped"))
            tx_drops=_counter(p,("tx_dropped","txDrops","tx_drop","txDropped"))
            cumulative_errors=sum(x or 0 for x in (rx_errors,tx_errors))
            cumulative_drops=sum(x or 0 for x in (rx_drops,tx_drops))

            key=f"{device.get('id')}:{idx}"
            expectation_scope=(_norm_mac(endpoint.get("mac")) if endpoint and endpoint.get("mac") else "PORT:"+key)
            expectation=expectations.get(expectation_scope) or {}
            expected_speed=_num(expectation.get("expected_speed_mbps"))
            events=event_summary.get(key) or {}
            counters_now=counter_summary.get(key) or {}
            error_delta=int(counters_now.get("errorDelta") or 0)
            drop_delta=int(counters_now.get("dropDelta") or 0)
            state_changes=int(events.get("stateChanges") or 0)
            speed_changes=int(events.get("speedChanges") or 0)

            status="UNUSED"
            reason="Port is not currently active."
            if state=="UP":
                counters["active"]+=1
                status="GOOD"
                reason="Active link is operating without an obvious issue."

                if poe.get("state")=="FAULT":
                    status="WARNING"
                    reason="PoE reports a fault on this active port."
                elif state_changes>=4:
                    status="WARNING"
                    reason=f"Port changed link state {state_changes} times in the last 24 hours."
                    counters["flapping"]+=1
                elif state_changes>=2 or speed_changes>=3:
                    status="REVIEW"
                    reason=f"Port changed state {state_changes} times and speed {speed_changes} times in the last 24 hours."
                    counters["flapping"]+=1
                elif error_delta>=1000 or drop_delta>=5000:
                    status="WARNING"
                    reason=f"Port added {error_delta} error(s) and {drop_delta} drop(s) since the last monitor sample."
                elif error_delta>=100 or drop_delta>=500:
                    status="REVIEW"
                    reason=f"Port added {error_delta} error(s) and {drop_delta} drop(s) since the last monitor sample."
                elif expected_speed is not None and speed is not None:
                    if speed >= expected_speed:
                        status="NORMAL"
                        reason=f"Link matches the acknowledged expected speed of {expected_speed:g} Mbps."
                    elif speed <= expected_speed/2:
                        status="WARNING"
                        reason=f"Link is {speed:g} Mbps, below the acknowledged expected speed of {expected_speed:g} Mbps."
                    else:
                        status="REVIEW"
                        reason=f"Link is {speed:g} Mbps, below the acknowledged expected speed of {expected_speed:g} Mbps."
                elif speed is not None and speed<=100:
                    if endpoint and endpoint.get("type")=="UNIFI_DEVICE":
                        status="WARNING"
                        reason="A UniFi infrastructure device is linked at 100 Mbps or below."
                    elif endpoint and _likely_low_speed_endpoint(endpoint.get("name"),endpoint.get("network")):
                        status="NORMAL"
                        reason="100 Mbps link appears consistent with an IoT/camera-class endpoint."
                    else:
                        status="REVIEW"
                        reason="100 Mbps link may be normal for this endpoint; confirm its Ethernet capability."
                elif endpoint and endpoint.get("type")=="UNIFI_DEVICE" and speed is not None:
                    child_max=_num(endpoint.get("expectedMaxMbps"))
                    path_max=min(x for x in (max_speed,child_max) if x is not None) if any(x is not None for x in (max_speed,child_max)) else None
                    if path_max and speed < path_max and speed <= path_max/2:
                        status="REVIEW"
                        reason=f"Infrastructure link is {speed:g} Mbps while both sides may support up to {path_max:g} Mbps."

                if status=="GOOD":
                    counters["good"]+=1
                elif status=="NORMAL":
                    counters["normal"]+=1
                elif status=="REVIEW":
                    counters["review"]+=1
                elif status=="WARNING":
                    counters["warning"]+=1

            row={
                "deviceId":device.get("id"),
                "deviceName":device.get("name") or device.get("model"),
                "deviceModel":device.get("model"),
                "deviceMac":mac,
                "portIdx":idx,
                "portName":_first(p,("name","port_name","portName")) or _first(official_port,("name","port_name","portName","connector")),
                "state":state,
                "speedMbps":speed,
                "maxSpeedMbps":max_speed,
                "profile":_port_profile(p),
                "nativeVlan":_native_vlan(p),
                "rxRateBps":_rate_bps(p,"rx"),
                "txRateBps":_rate_bps(p,"tx"),
                "rxErrors":rx_errors,
                "txErrors":tx_errors,
                "rxDrops":rx_drops,
                "txDrops":tx_drops,
                "cumulativeErrors":cumulative_errors,
                "cumulativeDrops":cumulative_drops,
                "errorDelta":error_delta,
                "dropDelta":drop_delta,
                "counterSampleAt":counters_now.get("sampleAt"),
                "poeState":poe.get("state"),
                "poePowerW":poe.get("powerW"),
                "poeVoltageV":poe.get("voltageV"),
                "poeCurrentMa":poe.get("currentMa"),
                "poeMode":poe.get("mode"),
                "endpointType":endpoint.get("type") if endpoint else None,
                "endpointKey":endpoint.get("key") if endpoint else None,
                "endpointDeviceId":endpoint.get("deviceId") if endpoint else None,
                "endpointName":endpoint.get("name") if endpoint else None,
                "endpointIp":endpoint.get("ip") if endpoint else None,
                "endpointMac":endpoint.get("mac") if endpoint else None,
                "endpointModel":endpoint.get("model") if endpoint else None,
                "endpointNetwork":endpoint.get("network") if endpoint else None,
                "endpointVlan":endpoint.get("vlan") if endpoint else None,
                "expectationScopeKey":expectation_scope,
                "expectedSpeedMbps":expected_speed,
                "expectationNote":expectation.get("note"),
                "status":status,
                "reason":reason,
                "stateChanges24h":state_changes,
                "speedChanges24h":speed_changes,
                "lastEvent":events.get("lastEvent"),
            }
            rows.append(row)

            if endpoint and endpoint.get("type")=="UNIFI_DEVICE":
                links.append({
                    "parentDeviceId":device.get("id"),
                    "parentDeviceName":device.get("name") or device.get("model"),
                    "parentPortIdx":idx,
                    "childDeviceId":endpoint.get("deviceId"),
                    "childDeviceName":endpoint.get("name"),
                    "speedMbps":speed,
                    "maxSpeedMbps":max_speed,
                    "poeState":poe.get("state"),
                    "poePowerW":poe.get("powerW"),
                    "status":status,
                    "reason":reason,
                })

    # Include logical UniFi uplinks even when the classic API did not reveal the parent port.
    existing={(x.get("parentDeviceId"),x.get("childDeviceId")) for x in links}
    for child in devices:
        parent_id=(child.get("uplink") or {}).get("deviceId")
        if not parent_id or (parent_id,child.get("id")) in existing:
            continue
        parent=next((d for d in devices if d.get("id")==parent_id),None)
        if not parent:
            continue
        links.append({
            "parentDeviceId":parent_id,
            "parentDeviceName":parent.get("name") or parent.get("model"),
            "parentPortIdx":None,
            "childDeviceId":child.get("id"),
            "childDeviceName":child.get("name") or child.get("model"),
            "speedMbps":None,
            "maxSpeedMbps":None,
            "poeState":None,
            "poePowerW":None,
            "status":"INFO",
            "reason":"UniFi reports the logical uplink but not the parent switch port in the current data source.",
        })

    actionable=counters["warning"]+counters["review"]
    score=max(0,100-counters["warning"]*12-counters["review"]*4)
    rows.sort(key=lambda x:(x.get("deviceName") or "",x.get("portIdx") or 0))

    return {
        "score":score,
        "summary":counters,
        "ports":rows,
        "links":links,
        "events":recent_events,
        "classicAvailable":bool(classic_devices),
        "actionableCount":actionable,
    }
