let previousAlertState={internet:null,offlineAps:new Set(),testResults:new Map()};
let report=null;

function closeMobileNav(){
  const sidebar=document.getElementById("primarySidebar");
  const backdrop=document.getElementById("mobileNavBackdrop");
  const toggle=document.getElementById("mobileNavToggle");
  sidebar?.classList.remove("mobile-open");
  document.body.classList.remove("mobile-nav-open");
  if(backdrop)backdrop.hidden=true;
  if(toggle)toggle.setAttribute("aria-expanded","false");
}
function openMobileNav(){
  const sidebar=document.getElementById("primarySidebar");
  const backdrop=document.getElementById("mobileNavBackdrop");
  const toggle=document.getElementById("mobileNavToggle");
  sidebar?.classList.add("mobile-open");
  document.body.classList.add("mobile-nav-open");
  if(backdrop)backdrop.hidden=false;
  if(toggle)toggle.setAttribute("aria-expanded","true");
}
function toggleMobileNav(){
  const sidebar=document.getElementById("primarySidebar");
  if(sidebar?.classList.contains("mobile-open"))closeMobileNav();
  else openMobileNav();
}
document.getElementById("mobileNavToggle")?.addEventListener("click",toggleMobileNav);
document.getElementById("mobileNavBackdrop")?.addEventListener("click",closeMobileNav);
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeMobileNav();});
window.addEventListener("resize",()=>{if(window.innerWidth>800)closeMobileNav();});

document.querySelectorAll(".nav").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".nav").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".page").forEach(x=>x.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.page).classList.add("active");
    const mobileLabel=document.getElementById("mobileNavLabel");
    if(mobileLabel)mobileLabel.textContent=btn.textContent.trim();
    closeMobileNav();
    window.scrollTo({top:0,behavior:"auto"});
    if(btn.dataset.page==="history") loadHistory();
    if(btn.dataset.page==="roaming") loadRoaming();
    if(btn.dataset.page==="internet") loadInternet();
    if(btn.dataset.page==="wanquality") loadWanQuality();
    if(btn.dataset.page==="traffic") loadTraffic();
    if(btn.dataset.page==="speedtest") loadSpeedtest();
    if(btn.dataset.page==="channels") loadChannelPlan();
    if(btn.dataset.page==="rfenvironment") loadRfEnvironment();
    if(btn.dataset.page==="system") loadSystem();
    if(btn.dataset.page==="topology") loadTopology();
    if(btn.dataset.page==="switches") loadWiredAudit();
    if(btn.dataset.page==="audit") loadNetworkAudit();
    if(btn.dataset.page==="exportai"){loadAiStatus();loadAiProposals();}
  });
});

function esc(v){return String(v??"—").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
function speed(v){if(!v)return "—";return v>=1000?(v/1000)+" Gbps":v+" Mbps"}
function retryClass(v){if(v==null)return "";if(v>=25)return "bad";if(v>=15)return "warn";if(v>=8)return "info";return "good"}
function fmtTime(v){try{return new Date(v).toLocaleTimeString([],{hour:"numeric",minute:"2-digit",second:"2-digit"})}catch{return "—"}}
function maxRetry(ap){
  const t=(report?.retryTrends||{})[ap.id];
  if(t && t.sampleCount>=3){
    const vals=[t.retry24,t.retry5,t.retry6].filter(x=>typeof x==="number");
    if(vals.length)return Math.max(...vals);
  }
  const r=((((ap.statistics||{}).interfaces)||{}).radios)||[];
  const vals=r.map(x=>x.txRetriesPct).filter(x=>typeof x==="number");
  return vals.length?Math.max(...vals):null;
}
function retryBasis(ap){
  const t=(report?.retryTrends||{})[ap.id];
  return t&&t.sampleCount>=3?(t.windowMinutes+"-min average"):"current";
}
function rateMbps(v){return typeof v==="number"?(v/1000000).toFixed(v>=100000000?0:1)+" Mbps":"—"}
function duration(sec){
  if(sec==null||!isFinite(sec)||sec<0)return "—";
  sec=Math.floor(sec);const d=Math.floor(sec/86400);sec%=86400;const h=Math.floor(sec/3600);sec%=3600;const m=Math.floor(sec/60);
  if(d)return d+"d "+h+"h";if(h)return h+"h "+m+"m";return m+"m";
}
function sinceDuration(iso){if(!iso)return "—";return duration((Date.now()-new Date(iso).getTime())/1000)}
function humanElapsed(iso){
  if(!iso)return {elapsed:"—",remaining:"—",done:false};
  const sec=Math.max(0,(Date.now()-new Date(iso).getTime())/1000);
  const remain=Math.max(0,3600-sec);
  return {elapsed:duration(sec),remaining:remain>0?duration(remain):"evaluation ready",done:remain<=0};
}
function fmtDateTime(v){try{return v?new Date(v).toLocaleString():"—"}catch{return "—"}}
function bytes(v){
  if(v==null)return "—";
  const units=["B","KB","MB","GB","TB","PB"];let n=Number(v),i=0;
  while(n>=1024&&i<units.length-1){n/=1024;i++}
  return n.toFixed(i?1:0)+" "+units[i];
}

async function loadReport(){
  try{
    const r=await fetch("/api/report",{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"API error");
    report=d;
    processAlerts(d);
    document.getElementById("controllerPill").textContent="Controller connected";
    document.getElementById("controllerPill").className="pill good";
    document.getElementById("lastChecked").textContent="Last checked "+fmtTime(d.lastChecked);
    document.getElementById("deviceCount").textContent=d.devices.length;
    document.getElementById("clientCount").textContent=d.clients.length;
    document.getElementById("apCount").textContent=d.accessPoints.length;
    document.getElementById("healthScore").textContent=d.analysis.healthScore;
    const healthy=d.analysis.high===0;
    document.getElementById("networkStatus").textContent=healthy?"Healthy":"Needs attention";
    document.getElementById("networkStatus").className=healthy?"good":"bad";
    document.getElementById("autoSummary").textContent=d.autoOptimizeEnabled?"ON":"OFF";
    document.getElementById("autoSummary").className=d.autoOptimizeEnabled?"good":"warn";
    const internetLatest=d.internet?.latest;
    document.getElementById("internetSummary").textContent=internetLatest?(internetLatest.online?"ONLINE":"OFFLINE"):"LEARNING";
    document.getElementById("internetSummary").className=internetLatest?(internetLatest.online?"good":"bad"):"info";
    document.getElementById("autoToggle").checked=d.autoOptimizeEnabled;
    renderOverview();renderAPs();renderBroadcasts();renderClients();renderRoamingSummary(d.roaming||[]);renderInternet(d.internet,d.gateway);renderChannelPlan(d.channelPlan);renderOptimizationTests(d.optimizationTests||[]);
  }catch(e){
    document.getElementById("controllerPill").textContent="Controller error";
    document.getElementById("controllerPill").className="pill bad";
  }
}

function findingHtml(x){
  return `<div class="recommendation ${esc(x.severity)}"><div class="rec-top"><span class="badge">${esc(x.severity)}</span><b>${esc(x.device)}</b><span class="muted">${esc(x.category)}</span></div><div class="rec-message">${esc(x.message)}</div></div>`;
}
function renderFindingList(id,list,emptyText){
  const box=document.getElementById(id);
  box.innerHTML=list.length?list.map(findingHtml).join(""):`<div class="empty">${esc(emptyText)}</div>`;
}
function renderOverview(){
  renderHealthTrend(report.healthHistory||[]);
  const apBox=document.getElementById("overviewApCards");apBox.innerHTML="";
  report.accessPoints.forEach(ap=>{
    const r=maxRetry(ap);
    const cls=retryClass(r);
    const base=(report.apBaselines||{})[ap.id];
    const clientLine=base&&base.sampleCount>=30?`${esc(ap.clientCount)} clients · 24h baseline ${Number(base.avgClients).toFixed(1)}`:`${esc(ap.clientCount)} clients · ${esc(ap.state)}`;
    apBox.insertAdjacentHTML("beforeend",`<div class="summary-card"><h3>${esc(ap.name)}</h3><div class="muted">${clientLine}</div><div class="big ${cls}">${r==null?"—":r.toFixed(1)+"%"}</div><div class="muted">highest TX retry · ${esc(retryBasis(ap))}</div></div>`);
  });
  const wifiBox=document.getElementById("overviewWifiCards");wifiBox.innerHTML="";
  report.wifiBroadcasts.forEach(w=>{
    const st=w.optimizerStatus||{};
    wifiBox.insertAdjacentHTML("beforeend",`<div class="summary-card"><h3>${esc(w.name)}</h3><div class="muted">${esc(w.type)}</div><div class="status-row"><span>${esc(st.detail)}</span><span class="status-tag ${esc(st.status)}">${esc(st.status)}</span></div></div>`);
  });
  renderFindingList("wifiFindings",report.analysis.wifiFindings||[],"No current Wi-Fi findings.");
  renderFindingList("wiredFindings",report.analysis.wiredFindings||[],"No wired observations.");
}

function renderHealthTrend(items){
  const chart=document.getElementById("healthScoreChart");
  const summary=document.getElementById("healthTrendSummary");
  if(!chart||!summary)return;
  if(!items.length){
    chart.innerHTML=chartGrid();
    summary.textContent="Learning…";
    return;
  }
  const vals=items.map(x=>typeof x.score==="number"?x.score:null);
  chart.innerHTML=chartGrid()+svgLine(vals,100,"chart-line-health");
  const first=vals.find(x=>x!=null);
  const last=[...vals].reverse().find(x=>x!=null);
  const low=Math.min(...vals.filter(Number.isFinite));
  const high=Math.max(...vals.filter(Number.isFinite));
  const delta=(first!=null&&last!=null)?last-first:0;
  summary.textContent="Low "+low.toFixed(0)+" · High "+high.toFixed(0)+" · "+(delta>=0?"+":"")+delta.toFixed(0)+" pts";
}

function renderAPs(){
  const box=document.getElementById("apCards");box.innerHTML="";
  report.accessPoints.forEach(ap=>{
    const cfg=((ap.interfaces||{}).radios||[]);
    const stats=(((ap.statistics||{}).interfaces||{}).radios||[]);
    const sm=new Map(stats.map(x=>[x.frequencyGHz,x]));
    let radios="";
    [2.4,5,6].forEach(f=>{
      const c=cfg.find(x=>x.frequencyGHz===f); if(!c)return;
      const retry=(sm.get(f)||{}).txRetriesPct;
      radios+=`<div class="radio"><b>${f} GHz</b><div class="metric"><span>Channel</span><span>${esc(c.channel)}</span></div><div class="metric"><span>Width</span><span>${esc(c.channelWidthMHz)} MHz</span></div><div class="metric"><span>TX retries</span><span class="${retryClass(retry)}">${retry==null?"—":retry.toFixed(1)+"%"}</span></div></div>`;
    });
    box.insertAdjacentHTML("beforeend",`<div class="ap-card"><h3>${esc(ap.name)}</h3><div class="muted">${esc(ap.model)} · ${esc(ap.clientCount)} clients · uplink ${esc(ap.uplinkName)}</div><div class="radio-grid">${radios}</div><div class="status-row"><span>CPU ${esc(ap.statistics?.cpuUtilizationPct)}% · Memory ${esc(ap.statistics?.memoryUtilizationPct)}%</span><span class="status-tag ${esc(ap.state)}">${esc(ap.state)}</span></div></div>`);
  });
}

function boolPill(v){return v===true?'<span class="status-tag ALREADY_OPTIMIZED">ON</span>':v===false?'<span class="status-tag NEEDS_ATTENTION">OFF</span>':'<span class="muted">—</span>'}
function renderBroadcasts(){
  const box=document.getElementById("wifiBroadcastCards");box.innerHTML="";
  report.wifiBroadcasts.forEach(w=>{
    const st=w.optimizerStatus||{};const hand=w.handoffSuggestionsConfiguration||{};
    const bands=(w.broadcastingFrequenciesGHz||[]).join(" / ")||"UniFi managed";
    box.insertAdjacentHTML("beforeend",`<div class="wifi-card"><h3>${esc(w.name)}</h3><div class="muted">${esc(w.type)} · bands ${esc(bands)}</div><div class="metric"><span>Band Steering</span><span>${boolPill(w.bandSteeringEnabled)}</span></div><div class="metric"><span>BSS Transition</span><span>${boolPill(w.bssTransitionEnabled)}</span></div><div class="metric"><span>MLO</span><span>${boolPill(w.mloEnabled)}</span></div><div class="metric"><span>5 GHz handoff</span><span>${hand.band5GHzRssiThreshold??"—"} dBm</span></div><div class="metric"><span>6 GHz handoff</span><span>${hand.band6GHzRssiThreshold??"—"} dBm</span></div><div class="status-row"><span class="muted">${esc(st.detail)}</span><span class="status-tag ${esc(st.status)}">${esc(st.status)}</span></div></div>`);
  });
}

function clientIpParts(ip){
  const s=String(ip||"");
  if(/^\d{1,3}(\.\d{1,3}){3}$/.test(s)){
    const p=s.split(".").map(Number);
    return [0,...p];
  }
  return [1,s.toLowerCase()];
}

function compareClientValues(a,b,sort){
  const dir=sort.endsWith("-desc")?-1:1;
  const field=sort.replace(/-(asc|desc)$/,"");
  let av,bv;
  if(field==="ip"){
    av=clientIpParts(a.ipAddress);bv=clientIpParts(b.ipAddress);
    for(let i=0;i<Math.max(av.length,bv.length);i++){
      const x=av[i]??"";const y=bv[i]??"";
      if(x===y)continue;
      return (x<y?-1:1)*dir;
    }
    return 0;
  }
  if(field==="vlan"){
    av=a.vlanId==null?99999:Number(a.vlanId);
    bv=b.vlanId==null?99999:Number(b.vlanId);
    return (av-bv)*dir;
  }
  if(field==="ap"){av=a.uplinkDeviceName||"";bv=b.uplinkDeviceName||""}
  else if(field==="network"){av=a.networkName||"";bv=b.networkName||""}
  else if(field==="type"){av=a.type||"";bv=b.type||""}
  else {av=a.name||a.macAddress||"";bv=b.name||b.macAddress||""}
  return String(av).localeCompare(String(bv),undefined,{numeric:true,sensitivity:"base"})*dir;
}

function setClientSelectOptions(id,values,allLabel){
  const el=document.getElementById(id);
  if(!el)return;
  const current=el.value;
  const unique=[...new Set(values.filter(v=>v!==null&&v!==undefined&&String(v)!=="").map(v=>String(v)))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true,sensitivity:"base"}));
  el.innerHTML='<option value="">'+esc(allLabel)+'</option>'+unique.map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join("");
  if(unique.includes(current))el.value=current;
}

function updateClientFilterOptions(){
  if(!report)return;
  const clients=report.clients||[];
  setClientSelectOptions("clientApFilter",clients.map(c=>c.uplinkDeviceName),"All APs / uplinks");
  setClientSelectOptions("clientVlanFilter",clients.map(c=>c.vlanId==null?"Unknown":c.vlanId),"All VLANs");
  const networks=[
    ...clients.map(c=>c.networkName),
    ...(report.networks||[]).map(n=>n.name)
  ];
  setClientSelectOptions("clientNetworkFilter",networks,"All networks");

  const typeEl=document.getElementById("clientTypeFilter");
  if(typeEl){
    const current=typeEl.value;
    const types=[...new Set(clients.map(c=>c.type).filter(Boolean))].sort();
    typeEl.innerHTML='<option value="">All types</option>'+types.map(v=>'<option value="'+esc(v)+'">'+esc(v.charAt(0)+v.slice(1).toLowerCase())+'</option>').join("");
    if(types.includes(current))typeEl.value=current;
  }
}

function clientRowHtml(c){
  const network=c.networkName&&c.networkName!=="Unknown"?c.networkName:"Unknown";
  const ssid=c.ssid&&c.ssid!==network?'<div class="muted">'+esc(c.ssid)+'</div>':"";
  const vlan=c.vlanId==null?"Unknown":c.vlanId;
  const name=c.name||c.macAddress||"Unnamed client";
  const uplink=c.uplinkDeviceName||"Unknown";
  const port=c.switchPort!=null?'<div class="muted">Port '+esc(c.switchPort)+'</div>':"";
  return '<tr>'+
    '<td><b>'+esc(name)+'</b></td>'+
    '<td class="client-ip">'+esc(c.ipAddress)+'</td>'+
    '<td class="client-mac">'+esc(c.macAddress)+'</td>'+
    '<td><span class="status-tag '+(c.type==="WIRELESS"?"PROTECTED":c.type==="WIRED"?"ALREADY_OPTIMIZED":"")+'">'+esc(c.type)+'</span></td>'+
    '<td><span class="vlan-pill">VLAN '+esc(vlan)+'</span></td>'+
    '<td>'+esc(network)+ssid+'</td>'+
    '<td>'+esc(uplink)+port+'</td>'+
    '<td>'+esc(c.uplinkDeviceModel)+'</td>'+
  '</tr>';
}

function clientGroupValue(c,groupBy){
  if(groupBy==="ap")return c.uplinkDeviceName||"Unknown AP / uplink";
  if(groupBy==="vlan")return c.vlanId==null?"VLAN Unknown":"VLAN "+c.vlanId;
  if(groupBy==="network")return c.networkName||"Unknown network";
  if(groupBy==="type")return c.type||"Unknown type";
  return "";
}

function filteredClients(){
  if(!report)return [];
  const q=(document.getElementById("clientSearch")?.value||"").trim().toLowerCase();
  const ap=document.getElementById("clientApFilter")?.value||"";
  const type=document.getElementById("clientTypeFilter")?.value||"";
  const vlan=document.getElementById("clientVlanFilter")?.value||"";
  const network=document.getElementById("clientNetworkFilter")?.value||"";
  const sort=document.getElementById("clientSort")?.value||"name-asc";

  return (report.clients||[]).filter(c=>{
    const searchFields=[
      c.name,c.ipAddress,c.macAddress,c.type,c.uplinkDeviceName,c.uplinkDeviceModel,
      c.networkName,c.ssid,c.vlanId,c.switchPort
    ];
    if(q && !searchFields.some(v=>String(v??"").toLowerCase().includes(q)))return false;
    if(ap && String(c.uplinkDeviceName||"")!==ap)return false;
    if(type && String(c.type||"")!==type)return false;
    const clientVlan=c.vlanId==null?"Unknown":String(c.vlanId);
    if(vlan && clientVlan!==vlan)return false;
    if(network && String(c.networkName||"")!==network)return false;
    return true;
  }).sort((a,b)=>compareClientValues(a,b,sort));
}

function renderClients(){
  if(!report)return;
  updateClientFilterOptions();
  const rows=filteredClients();
  const groupBy=document.getElementById("clientGroupBy")?.value||"none";
  const t=document.getElementById("clientTable");
  const flat=document.getElementById("clientFlatTable");
  const grouped=document.getElementById("clientGroupedContainer");

  const wireless=rows.filter(c=>c.type==="WIRELESS").length;
  const wired=rows.filter(c=>c.type==="WIRED").length;
  const vlans=new Set(rows.map(c=>c.vlanId==null?"Unknown":String(c.vlanId)));

  document.getElementById("clientMatchingCount").textContent=rows.length;
  document.getElementById("clientWirelessCount").textContent=wireless;
  document.getElementById("clientWiredCount").textContent=wired;
  document.getElementById("clientVlanCount").textContent=vlans.size;

  const total=(report.clients||[]).length;
  const summary=document.getElementById("clientFilterSummary");
  if(summary){
    const active=[];
    const ap=document.getElementById("clientApFilter")?.value;
    const type=document.getElementById("clientTypeFilter")?.value;
    const vlan=document.getElementById("clientVlanFilter")?.value;
    const network=document.getElementById("clientNetworkFilter")?.value;
    if(ap)active.push("uplink: "+ap);
    if(type)active.push("type: "+type);
    if(vlan)active.push("VLAN: "+vlan);
    if(network)active.push("network: "+network);
    summary.textContent=rows.length+" of "+total+" clients"+(active.length?" · "+active.join(" · "):"");
  }

  if(groupBy==="none"){
    if(flat)flat.style.display="";
    if(grouped)grouped.innerHTML="";
    if(t){
      t.innerHTML=rows.length?rows.map(clientRowHtml).join(""):'<tr><td colspan="8"><div class="empty">No clients match the selected filters.</div></td></tr>';
    }
    return;
  }

  if(flat)flat.style.display="none";
  const groups=new Map();
  rows.forEach(c=>{
    const key=clientGroupValue(c,groupBy);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(c);
  });

  if(grouped){
    if(!groups.size){
      grouped.innerHTML='<div class="empty">No clients match the selected filters.</div>';
      return;
    }
    grouped.innerHTML=[...groups.entries()].sort((a,b)=>a[0].localeCompare(b[0],undefined,{numeric:true,sensitivity:"base"})).map(([name,items])=>
      '<div class="client-group">'+
        '<div class="client-group-head"><div><h3>'+esc(name)+'</h3><span class="muted">'+items.length+' client'+(items.length===1?"":"s")+'</span></div></div>'+
        '<div class="panel table-wrap"><table><thead><tr><th>Name</th><th>IP</th><th>MAC</th><th>Type</th><th>VLAN</th><th>Network / SSID</th><th>Connected through</th><th>Model</th></tr></thead><tbody>'+
        items.map(clientRowHtml).join("")+
        '</tbody></table></div>'+
      '</div>'
    ).join("");
  }
}

["clientSearch","clientApFilter","clientTypeFilter","clientVlanFilter","clientNetworkFilter","clientGroupBy","clientSort"].forEach(id=>{
  const el=document.getElementById(id);
  if(!el)return;
  el.addEventListener(id==="clientSearch"?"input":"change",()=>report&&renderClients());
});

document.getElementById("clientResetFilters")?.addEventListener("click",()=>{
  ["clientSearch","clientApFilter","clientTypeFilter","clientVlanFilter","clientNetworkFilter"].forEach(id=>{
    const el=document.getElementById(id);if(el)el.value="";
  });
  const group=document.getElementById("clientGroupBy");if(group)group.value="none";
  const sort=document.getElementById("clientSort");if(sort)sort.value="name-asc";
  if(report)renderClients();
});

document.querySelectorAll("[data-client-sort]").forEach(th=>{
  th.addEventListener("click",()=>{
    const sort=document.getElementById("clientSort");
    if(!sort)return;
    const requested=th.dataset.clientSort;
    const base=requested.replace(/-(asc|desc)$/,"");
    const current=sort.value;
    sort.value=current===base+"-asc"?base+"-desc":base+"-asc";
    if(![...sort.options].some(o=>o.value===sort.value)){
      sort.value=requested;
    }
    if(report)renderClients();
  });
});

let wiredAuditData=null;
let topologyLinkMap=new Map();

function wiredStatusClass(status){
  if(status==="GOOD"||status==="NORMAL")return "ALREADY_OPTIMIZED";
  if(status==="WARNING")return "NEEDS_ATTENTION";
  if(status==="REVIEW")return "PROTECTED";
  return "PROTECTED";
}
function wiredScoreClass(v){
  if(v==null)return "info";
  if(v>=90)return "good";
  if(v>=75)return "info";
  if(v>=60)return "warn";
  return "bad";
}
function wiredLinkSpeed(v){
  if(v==null)return "—";
  const n=Number(v);
  if(n>=1000)return (n/1000).toFixed(n%1000===0?0:1)+" Gbps";
  return n.toFixed(0)+" Mbps";
}
function topologyLinkDetail(device){
  const link=topologyLinkMap.get(device.id);
  if(!link)return "";
  const bits=[];
  if(link.parentPortIdx!=null)bits.push("Port "+link.parentPortIdx);
  if(link.speedMbps!=null)bits.push(wiredLinkSpeed(link.speedMbps));
  if(link.poePowerW!=null&&Number(link.poePowerW)>0)bits.push("PoE "+Number(link.poePowerW).toFixed(1)+" W");
  if(!bits.length)return "";
  return '<div class="topology-link-detail '+String(link.status||"").toLowerCase()+'">'+bits.map(esc).join(" · ")+'</div>';
}

function topologyNodeTypeClass(type){
  if(type==="GATEWAY")return "topo-gateway";
  if(type==="SWITCH")return "topo-switch";
  if(type==="ACCESS_POINT")return "topo-ap";
  return "topo-device-other";
}

function topologyIcon(type){
  if(type==="GATEWAY")return "GW";
  if(type==="SWITCH")return "SW";
  if(type==="ACCESS_POINT")return "AP";
  return "DV";
}

function topologyClientIcon(type){
  if(type==="WIRELESS")return "Wi";
  if(type==="WIRED")return "Eth";
  if(type==="VPN")return "VPN";
  return "Cl";
}

function topologyClientMatches(c){
  const type=document.getElementById("topologyClientType")?.value||"";
  const vlan=document.getElementById("topologyVlanFilter")?.value||"";
  const network=document.getElementById("topologyNetworkFilter")?.value||"";
  if(type && String(c.type||"")!==type)return false;
  if(vlan && String(c.vlanId??"Unknown")!==vlan)return false;
  if(network && String(c.networkName||"Unknown")!==network)return false;
  return true;
}

function topologyRadioSummary(device){
  if(device.optimizerType!=="ACCESS_POINT")return "";
  const radios=((device.interfaces||{}).radios)||[];
  const parts=radios.map(r=>{
    const f=r.frequencyGHz;
    if(f==null)return null;
    return f+" GHz ch "+(r.channel??"—")+" / "+(r.channelWidthMHz??"—")+" MHz";
  }).filter(Boolean);
  return parts.length?'<div class="topology-radio-line">'+parts.map(esc).join(" · ")+'</div>':"";
}

function topologyClientHtml(c,compact=false){
  const name=c.name||c.macAddress||"Unnamed client";
  const vlan=c.vlanId==null?"Unknown":c.vlanId;
  const network=c.networkName||"Unknown";
  const details=compact
    ? esc(c.ipAddress||"—")+" · VLAN "+esc(vlan)
    : esc(c.type||"CLIENT")+" · "+esc(c.ipAddress||"—")+" · VLAN "+esc(vlan)+" · "+esc(network)+(c.ssid?" · "+esc(c.ssid):"");
  return '<div class="topology-client">'+
    '<div class="topology-client-icon">'+esc(topologyClientIcon(c.type))+'</div>'+
    '<div class="topology-client-copy"><b>'+esc(name)+'</b><span>'+details+'</span></div>'+
  '</div>';
}

function topologyDeviceHtml(device,childrenMap,clientsMap,seen,depth=0){
  if(!device||seen.has(device.id))return "";
  seen.add(device.id);
  const type=device.optimizerType||"DEVICE";
  const children=childrenMap.get(device.id)||[];
  const clients=(clientsMap.get(device.id)||[]).filter(topologyClientMatches);
  const showClients=document.getElementById("topologyShowClients")?.checked!==false;
  const compact=document.getElementById("topologyCompact")?.checked===true;
  const state=device.state||"UNKNOWN";
  const stateClass=state==="ONLINE"?"good":"bad";
  const ip=device.ipAddress||"—";
  const childHtml=children.map(x=>topologyDeviceHtml(x,childrenMap,clientsMap,seen,depth+1)).join("");
  const clientHtml=showClients&&clients.length
    ? '<div class="topology-clients">'+clients.map(x=>topologyClientHtml(x,compact)).join("")+'</div>'
    : "";

  return '<div class="topology-branch">'+
    '<div class="topology-device '+topologyNodeTypeClass(type)+'">'+
      '<div class="topology-device-icon">'+esc(topologyIcon(type))+'</div>'+
      '<div class="topology-device-copy">'+
        '<div class="topology-device-head"><b>'+esc(device.name||device.model||"UniFi device")+'</b><span class="'+stateClass+'">'+esc(state)+'</span></div>'+
        '<span>'+esc(type.replace("_"," "))+' · '+esc(device.model||"—")+' · '+esc(ip)+'</span>'+
        (device.uplinkName?'<span class="muted">Uplink: '+esc(device.uplinkName)+'</span>':"")+
        topologyRadioSummary(device)+
        topologyLinkDetail(device)+
      '</div>'+
      '<div class="topology-counts">'+
        (type==="ACCESS_POINT"?'<span>'+esc(device.clientCount||0)+' clients</span>':"")+
        (children.length?'<span>'+esc(children.length)+' downstream</span>':"")+
      '</div>'+
    '</div>'+
    (childHtml||clientHtml?'<div class="topology-children">'+childHtml+clientHtml+'</div>':"")+
  '</div>';
}

async function loadTopology(){
  try{
    const r=await fetch("/api/wired-audit",{cache:"no-store"});
    const d=await r.json();
    if(d.ok){
      wiredAuditData=d;
      topologyLinkMap=new Map((d.links||[]).filter(x=>x.childDeviceId).map(x=>[x.childDeviceId,x]));
    }
  }catch(e){}
  renderTopology();
}

function renderTopology(){
  if(!report)return;
  const tree=document.getElementById("topologyTree");
  if(!tree)return;

  const devices=report.devices||[];
  const clients=report.clients||[];
  const deviceMap=new Map(devices.map(d=>[d.id,d]));
  const nameMap=new Map(devices.map(d=>[String(d.name||""),d]));
  const childrenMap=new Map();
  const clientsMap=new Map();
  const unresolvedDevices=[];

  devices.forEach(d=>{
    const uplinkId=(d.uplink||{}).deviceId;
    let parent=uplinkId?deviceMap.get(uplinkId):null;
    if(!parent && d.uplinkName)parent=nameMap.get(String(d.uplinkName));
    if(parent && parent.id!==d.id){
      if(!childrenMap.has(parent.id))childrenMap.set(parent.id,[]);
      childrenMap.get(parent.id).push(d);
    }else if(d.optimizerType!=="GATEWAY"){
      unresolvedDevices.push(d);
    }
  });

  clients.forEach(c=>{
    if(!c.uplinkDeviceId)return;
    if(!clientsMap.has(c.uplinkDeviceId))clientsMap.set(c.uplinkDeviceId,[]);
    clientsMap.get(c.uplinkDeviceId).push(c);
  });

  for(const arr of childrenMap.values()){
    arr.sort((a,b)=>{
      const order={SWITCH:0,ACCESS_POINT:1,GATEWAY:2};
      const ao=order[a.optimizerType]??9,bo=order[b.optimizerType]??9;
      return ao-bo||String(a.name||"").localeCompare(String(b.name||""));
    });
  }
  for(const arr of clientsMap.values()){
    arr.sort((a,b)=>String(a.name||a.ipAddress||"").localeCompare(String(b.name||b.ipAddress||""),undefined,{numeric:true,sensitivity:"base"}));
  }

  setClientSelectOptions("topologyVlanFilter",clients.map(c=>c.vlanId==null?"Unknown":c.vlanId),"All VLANs");
  setClientSelectOptions("topologyNetworkFilter",clients.map(c=>c.networkName||"Unknown"),"All networks");

  const gateways=devices.filter(d=>d.optimizerType==="GATEWAY");
  const seen=new Set();
  let html='<div class="topology-internet"><div class="topology-internet-node"><b>Internet</b><span>WAN</span></div><div class="topology-internet-line"></div></div>';
  if(gateways.length){
    html+=gateways.map(g=>topologyDeviceHtml(g,childrenMap,clientsMap,seen,0)).join("");
  }else{
    html+='<div class="empty">No gateway was returned by the current UniFi device inventory.</div>';
  }

  const remaining=devices.filter(d=>!seen.has(d.id));
  if(remaining.length){
    html+='<div class="topology-unresolved"><h3>Unresolved / standalone</h3><div class="muted">UniFi did not report a usable uplink relationship for these devices.</div>'+
      remaining.map(d=>topologyDeviceHtml(d,new Map(),clientsMap,seen,0)).join("")+
    '</div>';
  }
  tree.innerHTML=html;

  const set=(id,val)=>{const el=document.getElementById(id);if(el)el.textContent=val};
  set("topologyDeviceCount",devices.length);
  set("topologySwitchCount",devices.filter(d=>d.optimizerType==="SWITCH").length);
  set("topologyApCount",devices.filter(d=>d.optimizerType==="ACCESS_POINT").length);
  set("topologyClientCount",clients.filter(topologyClientMatches).length);

  const notice=document.getElementById("topologyNotice");
  if(notice){
    const unresolved=remaining.length;
    notice.innerHTML='<b class="'+(unresolved?"warn":"good")+'">'+(unresolved?"Topology mostly resolved":"Topology resolved from UniFi uplinks")+'</b><br>'+
      '<span class="muted">'+esc(devices.length)+' UniFi devices · '+esc(clients.length)+' connected clients'+(unresolved?' · '+esc(unresolved)+' device'+(unresolved===1?"":"s")+' without a resolved parent':"")+'.</span>';
  }
}

["topologyShowClients","topologyClientType","topologyVlanFilter","topologyNetworkFilter","topologyCompact"].forEach(id=>{
  const el=document.getElementById(id);
  if(!el)return;
  el.addEventListener("change",()=>report&&renderTopology());
});


let networkAuditData=null;

function auditScoreClass(v){
  if(v==null)return "info";
  if(v>=90)return "good";
  if(v>=75)return "info";
  if(v>=60)return "warn";
  return "bad";
}
function auditStatusClass(status){
  if(status==="PASS")return "ALREADY_OPTIMIZED";
  if(status==="REVIEW")return "PROTECTED";
  if(status==="WARNING")return "NEEDS_ATTENTION";
  if(status==="CRITICAL")return "FAILED";
  return "PROTECTED";
}
function auditLabel(category){
  return String(category||"").replaceAll("_"," ").replace(/\b\w/g,m=>m.toUpperCase());
}
function auditFilteredFindings(){
  if(!networkAuditData)return [];
  const q=(document.getElementById("auditSearch")?.value||"").trim().toLowerCase();
  const status=document.getElementById("auditStatusFilter")?.value||"";
  const category=document.getElementById("auditCategoryFilter")?.value||"";
  return (networkAuditData.findings||[]).filter(x=>{
    if(status && x.status!==status)return false;
    if(category && x.category!==category)return false;
    if(q){
      const vals=[x.title,x.detail,x.target,x.recommendation,x.category,x.status];
      if(!vals.some(v=>String(v||"").toLowerCase().includes(q)))return false;
    }
    return true;
  });
}
function renderAuditFindings(){
  const box=document.getElementById("auditFindings");
  if(!box||!networkAuditData)return;
  const rows=auditFilteredFindings();
  box.innerHTML=rows.length?rows.map(x=>
    '<div class="audit-finding '+esc(String(x.status||"").toLowerCase())+'">'+
      '<div class="audit-finding-head">'+
        '<div><span class="status-tag '+auditStatusClass(x.status)+'">'+esc(x.status)+'</span> <span class="audit-category">'+esc(auditLabel(x.category))+'</span></div>'+
        (x.target?'<span class="audit-target">'+esc(x.target)+'</span>':"")+
      '</div>'+
      '<h3>'+esc(x.title)+'</h3>'+
      '<p>'+esc(x.detail)+'</p>'+
      (x.recommendation?'<div class="audit-recommendation"><b>Recommended review</b><span>'+esc(x.recommendation)+'</span></div>':"")+
    '</div>'
  ).join(""):'<div class="empty">No audit findings match the selected filters.</div>';
}
function renderAuditInventory(inv){
  inv=inv||{};
  const networkBox=document.getElementById("auditNetworksInventory");
  if(networkBox){
    const rows=inv.networks||[];
    networkBox.innerHTML=rows.length?rows.map(x=>
      '<div class="audit-inventory-row"><b>'+esc(x.name||"Unnamed network")+'</b><span>VLAN '+esc(x.vlanId??"—")+(x.default?" · Default":"")+(x.enabled===false?" · Disabled":"")+'</span></div>'
    ).join(""):'<div class="empty">No networks returned.</div>';
  }
  const wifiBox=document.getElementById("auditWifiInventory");
  if(wifiBox){
    const rows=inv.wifi||[];
    wifiBox.innerHTML=rows.length?rows.map(x=>{
      const sec=(x.securityConfiguration||{}).type||"Unknown";
      const bands=(x.broadcastingFrequenciesGHz||[]).join(" / ")||"—";
      return '<div class="audit-inventory-row"><b>'+esc(x.name||"Unnamed Wi-Fi")+'</b><span>'+esc(sec)+' · '+esc(bands)+' GHz · MLO '+(x.mloEnabled?"ON":"OFF")+'</span></div>';
    }).join(""):'<div class="empty">No Wi-Fi broadcasts returned.</div>';
  }
  const firewallBox=document.getElementById("auditFirewallInventory");
  if(firewallBox){
    firewallBox.innerHTML=
      '<div class="audit-inventory-row"><b>Firewall zones</b><span>'+esc((inv.firewallZones||[]).length)+'</span></div>'+
      '<div class="audit-inventory-row"><b>Firewall policies</b><span>'+esc((inv.firewallPolicies||[]).length)+'</span></div>'+
      '<div class="audit-inventory-row"><b>ACL rules</b><span>'+esc((inv.aclRules||[]).length)+'</span></div>';
  }
  const wanBox=document.getElementById("auditWanInventory");
  if(wanBox){
    wanBox.innerHTML=
      '<div class="audit-inventory-row"><b>WAN interfaces</b><span>'+esc((inv.wans||[]).length)+'</span></div>'+
      '<div class="audit-inventory-row"><b>DNS policies</b><span>'+esc((inv.dnsPolicies||[]).length)+'</span></div>';
  }
}
function renderNetworkAudit(d){
  networkAuditData=d;
  const counts=d.counts||{};
  const set=(id,val,cls)=>{
    const el=document.getElementById(id);if(!el)return;
    el.textContent=val;
    if(cls!==undefined)el.className="big "+cls;
  };
  set("auditOverallScore",d.overallScore==null?"—":String(d.overallScore),auditScoreClass(d.overallScore));
  set("auditCriticalCount",counts.CRITICAL??0,"bad");
  set("auditWarningCount",counts.WARNING??0,"warn");
  set("auditReviewCount",counts.REVIEW??0,"info");
  set("auditPassCount",counts.PASS??0,"good");
  const gen=document.getElementById("auditGeneratedAt");if(gen)gen.textContent=fmtShortDate(d.generatedAt);

  const scores=document.getElementById("auditScoreCards");
  if(scores){
    scores.innerHTML=Object.entries(d.scores||{}).map(([k,v])=>
      '<div class="summary-card"><h3>'+esc(auditLabel(k))+'</h3><div class="big '+auditScoreClass(v)+'">'+esc(v)+'</div></div>'
    ).join("");
  }

  const cats=[...new Set((d.findings||[]).map(x=>x.category).filter(Boolean))].sort();
  setClientSelectOptions("auditCategoryFilter",cats.map(auditLabel),"All categories");
  const catSelect=document.getElementById("auditCategoryFilter");
  if(catSelect){
    [...catSelect.options].forEach(o=>{
      const raw=cats.find(x=>auditLabel(x)===o.value);
      if(raw)o.value=raw;
    });
  }

  const notice=document.getElementById("auditNotice");
  if(notice){
    const critical=Number(counts.CRITICAL||0),warning=Number(counts.WARNING||0);
    notice.innerHTML='<b class="'+(critical?"bad":warning?"warn":"good")+'">'+
      (critical?critical+" critical issue"+(critical===1?"":"s")+" found":warning?warning+" warning"+(warning===1?"":"s")+" found":"No critical audit findings")+
      '</b><br><span class="muted">Read-only audit · overall score '+esc(d.overallScore)+' · '+esc(counts.REVIEW||0)+' item'+(Number(counts.REVIEW||0)===1?"":"s")+' marked REVIEW for context-dependent confirmation.</span>';
  }
  renderAuditFindings();
  renderAuditInventory(d.inventory);
}
async function loadNetworkAudit(){
  const notice=document.getElementById("auditNotice");
  if(notice)notice.innerHTML='<b class="info">Running read-only audit…</b><br><span class="muted">Reading current UniFi configuration and health data.</span>';
  try{
    const r=await fetch("/api/network-audit",{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Audit failed");
    renderNetworkAudit(d);
  }catch(e){
    if(notice)notice.innerHTML='<b class="bad">Network audit failed</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}
["auditSearch","auditStatusFilter","auditCategoryFilter"].forEach(id=>{
  const el=document.getElementById(id);
  if(!el)return;
  el.addEventListener(id==="auditSearch"?"input":"change",renderAuditFindings);
});


function filteredWiredPorts(){
  const rows=(wiredAuditData?.ports||[]);
  const q=(document.getElementById("wiredSearch")?.value||"").trim().toLowerCase();
  const sw=document.getElementById("wiredSwitchFilter")?.value||"";
  const status=document.getElementById("wiredStatusFilter")?.value||"";
  const activeOnly=document.getElementById("wiredActiveOnly")?.checked!==false;
  return rows.filter(x=>{
    if(activeOnly && x.state!=="UP")return false;
    if(sw && x.deviceName!==sw)return false;
    if(status && x.status!==status)return false;
    if(q){
      const vals=[
        x.deviceName,x.portIdx,x.portName,x.endpointName,x.endpointIp,x.endpointMac,
        x.endpointModel,x.endpointNetwork,x.endpointVlan,x.profile,x.nativeVlan,x.status,x.reason
      ];
      if(!vals.some(v=>String(v??"").toLowerCase().includes(q)))return false;
    }
    return true;
  });
}

function renderWiredAudit(d){
  wiredAuditData=d;
  topologyLinkMap=new Map((d.links||[]).filter(x=>x.childDeviceId).map(x=>[x.childDeviceId,x]));
  const s=d.summary||{};
  const set=(id,val,cls)=>{
    const el=document.getElementById(id);if(!el)return;
    el.textContent=val;
    if(cls!==undefined)el.className="big "+cls;
  };
  set("wiredScore",d.score==null?"—":String(d.score),wiredScoreClass(d.score));
  set("wiredActive",s.active??0);
  set("wiredGood",s.good??0,"good");
  set("wiredNormal",s.normal??0,"good");
  set("wiredReview",s.review??0,"info");
  set("wiredWarning",s.warning??0,"warn");
  set("wiredPoe",s.poe??0);
  set("wiredFlapping",s.flapping??0,(Number(s.flapping||0)>0?"warn":"good"));

  const notice=document.getElementById("wiredAuditNotice");
  if(notice){
    if(!d.classicAvailable){
      notice.innerHTML='<b class="warn">Limited wired visibility</b><br><span class="muted">Official UniFi data is available, but classic/private switch telemetry was not returned. Endpoint, PoE and port-detail visibility may be incomplete.</span>';
    }else if(Number(s.warning||0)>0){
      notice.innerHTML='<b class="warn">'+esc(s.warning)+' wired warning'+(Number(s.warning)===1?"":"s")+'</b><br><span class="muted">'+esc(s.active||0)+' active ports analyzed · '+esc(s.review||0)+' need review · '+esc(s.normal||0)+' expected low-speed links.</span>';
    }else{
      notice.innerHTML='<b class="good">No wired warnings</b><br><span class="muted">'+esc(s.active||0)+' active ports analyzed · '+esc(s.review||0)+' need review · '+esc(s.normal||0)+' expected low-speed links.</span>';
    }
  }

  const switchSelect=document.getElementById("wiredSwitchFilter");
  if(switchSelect){
    const current=switchSelect.value;
    const values=[...new Set((d.ports||[]).map(x=>x.deviceName).filter(Boolean))].sort((a,b)=>a.localeCompare(b));
    switchSelect.innerHTML='<option value="">All switches</option>'+values.map(v=>'<option>'+esc(v)+'</option>').join("");
    if(values.includes(current))switchSelect.value=current;
  }
  renderWiredPortTable();
  renderWiredEvents();
}

function renderWiredPortTable(){
  const table=document.getElementById("wiredPortTable");
  if(!table||!wiredAuditData)return;
  const order={WARNING:0,REVIEW:1,NORMAL:2,GOOD:3,UNUSED:4};
  const rows=filteredWiredPorts().sort((a,b)=>
    (order[a.status]??9)-(order[b.status]??9)||
    String(a.deviceName||"").localeCompare(String(b.deviceName||""))||
    Number(a.portIdx||0)-Number(b.portIdx||0)
  );
  table.innerHTML=rows.length?rows.map(x=>{
    const endpoint=x.endpointName||"—";
    const endpointDetail=[
      x.endpointIp,
      x.endpointModel,
      x.endpointNetwork,
      x.endpointVlan!=null?"VLAN "+x.endpointVlan:null
    ].filter(Boolean).join(" · ");
    const poe=x.poeState==="POWERING"
      ?("POWERING"+(x.poePowerW!=null?" · "+Number(x.poePowerW).toFixed(1)+" W":""))
      :(x.poeState||"—");
    const traffic=[x.rxRateBps!=null?"RX "+rateMbps(x.rxRateBps):null,x.txRateBps!=null?"TX "+rateMbps(x.txRateBps):null].filter(Boolean).join(" / ")||"—";
    const cumulativeErrors=Number(x.cumulativeErrors??(Number(x.rxErrors||0)+Number(x.txErrors||0)));
    const cumulativeDrops=Number(x.cumulativeDrops??(Number(x.rxDrops||0)+Number(x.txDrops||0)));
    const recentErrors=Number(x.errorDelta||0);
    const recentDrops=Number(x.dropDelta||0);
    const errors=cumulativeErrors+" err · "+cumulativeDrops+" drop"+
      '<div class="muted">recent +'+recentErrors+' err / +'+recentDrops+' drop</div>';
    const profile=[x.nativeVlan!=null?"VLAN "+x.nativeVlan:null,x.profile].filter(Boolean).join(" · ")||"—";
    const changes=(Number(x.stateChanges24h||0))+" state · "+(Number(x.speedChanges24h||0))+" speed";
    const expected=x.expectedSpeedMbps!=null?wiredLinkSpeed(x.expectedSpeedMbps):null;
    const expectationControls=
      '<div class="wired-expectation">'+
        (expected?'<span>Expected '+esc(expected)+'</span>':'')+
        '<button class="secondary set-expected-speed-btn" data-scope="'+esc(x.expectationScopeKey||"")+'" data-name="'+esc(x.endpointName||x.deviceName+" Port "+x.portIdx)+'" data-current="'+esc(x.expectedSpeedMbps??"")+'">'+
          (expected?'Edit expected':'Set expected speed')+
        '</button>'+
      '</div>';
    return '<tr>'+
      '<td><b>'+esc(x.deviceName)+'</b><div class="muted">Port '+esc(x.portIdx)+(x.portName?" · "+esc(x.portName):"")+'</div></td>'+
      '<td><b>'+esc(endpoint)+'</b><div class="muted">'+esc(endpointDetail||x.endpointType||"No mapped endpoint")+'</div></td>'+
      '<td><b>'+esc(x.state)+'</b><div class="muted">'+esc(wiredLinkSpeed(x.speedMbps))+'</div></td>'+
      '<td>'+esc(wiredLinkSpeed(x.maxSpeedMbps))+'</td>'+
      '<td>'+esc(poe)+'</td>'+
      '<td>'+esc(traffic)+'</td>'+
      '<td>'+errors+'</td>'+
      '<td>'+esc(profile)+'</td>'+
      '<td>'+esc(changes)+(x.lastEvent?'<div class="muted">'+esc(fmtShortDate(x.lastEvent))+'</div>':"")+'</td>'+
      '<td><span class="status-tag '+wiredStatusClass(x.status)+'">'+esc(x.status)+'</span><div class="muted wired-reason">'+esc(x.reason)+'</div>'+expectationControls+'</td>'+
    '</tr>';
  }).join(""):'<tr><td colspan="10"><div class="empty">No ports match the selected filters.</div></td></tr>';
}

function renderWiredEvents(){
  const table=document.getElementById("wiredEventTable");
  if(!table||!wiredAuditData)return;
  const rows=wiredAuditData.events||[];
  table.innerHTML=rows.length?rows.map(x=>
    '<tr>'+
      '<td>'+esc(fmtDateTime(x.ts))+'</td>'+
      '<td>'+esc(x.device_name||"—")+'</td>'+
      '<td>'+esc(x.port_idx??"—")+'</td>'+
      '<td>'+esc(x.event_type||"—")+'</td>'+
      '<td>'+esc(x.from_value??"—")+'</td>'+
      '<td>'+esc(x.to_value??"—")+'</td>'+
      '<td>'+esc(x.endpoint_name||"—")+'</td>'+
    '</tr>'
  ).join(""):'<tr><td colspan="7"><div class="empty">No wired link changes recorded in the last 24 hours.</div></td></tr>';
}

async function loadWiredAudit(){
  const notice=document.getElementById("wiredAuditNotice");
  if(notice)notice.innerHTML='<b class="info">Reading switch telemetry…</b><br><span class="muted">Mapping ports, endpoints, negotiated speed, PoE and recent link changes.</span>';
  try{
    const r=await fetch("/api/wired-audit",{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Unable to load wired audit");
    renderWiredAudit(d);
  }catch(e){
    if(notice)notice.innerHTML='<b class="bad">Wired audit failed</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}

async function setExpectedWiredSpeed(button){
  const scope=button.dataset.scope||"";
  const name=button.dataset.name||"Wired endpoint";
  const current=button.dataset.current||"";
  if(!scope){
    alert("This port does not have a stable endpoint/port key yet.");
    return;
  }
  const value=prompt(
    "Expected Ethernet link speed for "+name+" in Mbps.\nAllowed: 10, 100, 1000, 2500, 5000, 10000, 25000, 40000, 100000.\nLeave blank to remove an existing expectation.",
    current
  );
  if(value===null)return;
  if(value.trim()===""){
    if(!current)return;
    await fetch("/api/wired-expectations/delete",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({scopeKey:scope})
    });
    await loadWiredAudit();
    return;
  }
  const speed=Number(value);
  const allowed=[10,100,1000,2500,5000,10000,25000,40000,100000];
  if(!allowed.includes(speed)){
    alert("Choose one of the allowed expected speeds.");
    return;
  }
  const r=await fetch("/api/wired-expectations",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({
      scopeKey:scope,
      endpointName:name,
      expectedSpeedMbps:speed
    })
  });
  const d=await r.json();
  if(!d.ok){
    alert(d.error||"Unable to save expected link speed.");
    return;
  }
  await loadWiredAudit();
}

document.addEventListener("click",e=>{
  const btn=e.target.closest(".set-expected-speed-btn");
  if(btn)setExpectedWiredSpeed(btn);
});

["wiredSearch","wiredSwitchFilter","wiredStatusFilter","wiredActiveOnly"].forEach(id=>{
  const el=document.getElementById(id);
  if(!el)return;
  el.addEventListener(id==="wiredSearch"?"input":"change",renderWiredPortTable);
});


function renderAiStatus(d){
  const configured=document.getElementById("aiConfigured");
  const configuredDetail=document.getElementById("aiConfiguredDetail");
  const model=document.getElementById("aiModel");
  const autoStatus=document.getElementById("aiAutoStatus");
  const autoDetail=document.getElementById("aiAutoDetail");
  const lastRun=document.getElementById("aiLastRun");
  const lastStatus=document.getElementById("aiLastStatus");
  const notice=document.getElementById("aiAdvisorNotice");
  const output=document.getElementById("aiOutput");
  const toggle=document.getElementById("aiAutoToggle");
  const interval=document.getElementById("aiInterval");
  const runBtn=document.getElementById("runAiAnalysisBtn");

  if(configured){
    configured.textContent=d.configured?"READY":"NOT CONFIGURED";
    configured.className="big compact-big "+(d.configured?"good":"warn");
  }
  if(configuredDetail)configuredDetail.textContent=d.configured?"API key is present in the container environment":"Add OPENAI_API_KEY to the Unraid container";
  if(model)model.textContent=d.model||"—";
  if(autoStatus){
    autoStatus.textContent=d.automaticEnabled?"ON":"OFF";
    autoStatus.className="big compact-big "+(d.automaticEnabled?"good":"info");
  }
  if(autoDetail)autoDetail.textContent=d.automaticEnabled?"Every "+d.intervalHours+" hour"+(Number(d.intervalHours)===1?"":"s"):"Manual analysis only";
  if(toggle){
    toggle.checked=!!d.automaticEnabled;
    toggle.disabled=!d.configured;
  }
  if(interval){
    interval.value=String(d.intervalHours||6);
    interval.disabled=!d.configured;
  }
  if(runBtn){
    runBtn.disabled=!d.configured||!!d.running;
    runBtn.textContent=d.running?"AI Analysis Running…":"Analyze network now";
  }

  const latest=d.latest||null;
  if(lastRun)lastRun.textContent=latest?.ts?fmtShortDate(latest.ts):"Never";
  if(lastStatus)lastStatus.textContent=latest?(latest.status+(latest.trigger?" · "+latest.trigger:"")):"—";
  if(output){
    if(latest?.summary)output.textContent=latest.summary;
    else if(latest?.error)output.textContent="Last AI analysis failed: "+latest.error;
    else output.textContent="No AI analysis has been run yet.";
  }

  if(notice){
    if(!d.configured){
      notice.innerHTML='<b class="info">AI integration is optional</b><br><span class="muted">Add <code>OPENAI_API_KEY</code> to the Unraid container environment. You can optionally set <code>OPENAI_MODEL</code>; the default is a cost-sensitive model. The API key is never returned by the app or included in exports.</span>';
    }else if(d.running){
      notice.innerHTML='<b class="info">AI analysis is running…</b><br><span class="muted">The advisor is reading a sanitized current snapshot. Network settings will not be changed.</span>';
    }else if(d.lastError){
      notice.innerHTML='<b class="warn">AI advisor reported an error</b><br><span class="muted">'+esc(d.lastError)+'</span>';
    }else{
      notice.innerHTML='<b class="good">AI advisor ready</b><br><span class="muted">Advisory-only mode · '+esc(d.model||"configured model")+' · automatic review '+(d.automaticEnabled?"enabled":"disabled")+'.</span>';
    }
  }
}

async function loadAiStatus(){
  try{
    const r=await fetch("/api/ai",{cache:"no-store"});
    const d=await r.json();
    if(d.ok)renderAiStatus(d);
  }catch(e){
    const notice=document.getElementById("aiAdvisorNotice");
    if(notice)notice.innerHTML='<b class="bad">Unable to load AI status</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}

async function runAiAnalysisNow(){
  const btn=document.getElementById("runAiAnalysisBtn");
  const notice=document.getElementById("aiAdvisorNotice");
  if(btn){btn.disabled=true;btn.textContent="Starting AI analysis…";}
  let started=false;
  try{
    const r=await fetch("/api/ai/analyze",{method:"POST"});
    const d=await r.json();
    if(!d.ok){
      const blockers=(d.blockers||[]).map(x=>
        [x.apName,x.band!=null?x.band+" GHz":null,x.status].filter(Boolean).join(" · ")
      );
      if(notice){
        notice.innerHTML='<b class="warn">'+esc(d.error||"Unable to start AI analysis")+'</b>'+
          (blockers.length?'<br><span class="muted">Blocking RF test: '+esc(blockers.join(" | "))+'</span>':'');
      }
      if(btn){btn.disabled=false;btn.textContent="Analyze network now";}
      return;
    }
    started=true;
    if(notice)notice.innerHTML='<b class="info">AI analysis starting…</b><br><span class="muted">Building a stable sanitized network snapshot.</span>';
    await loadAiStatus();
  }catch(e){
    if(notice)notice.innerHTML='<b class="bad">'+esc(e.message||e)+'</b>';
    if(btn){btn.disabled=false;btn.textContent="Analyze network now";}
  }finally{
    if(started)setTimeout(loadAiStatus,1500);
  }
}

function proposalStatusClass(status){
  if(status==="EXECUTED")return "SUCCESS";
  if(status==="ACKNOWLEDGED")return "ALREADY_OPTIMIZED";
  if(status==="FAILED")return "FAILED";
  if(status==="REJECTED")return "SKIPPED";
  return "PROTECTED";
}

function proposalActionLabel(action){
  if(action==="RF_ABA_TEST")return "RF A/B/A test";
  if(action==="AUTO_OPTIMIZE_RUN")return "Auto Optimize";
  if(action==="REVIEW_SETTING")return "Review only";
  return action||"Proposal";
}

function renderAiProposals(items){
  const box=document.getElementById("aiProposalQueue");
  if(!box)return;
  if(!items||!items.length){
    box.innerHTML='<div class="empty">No AI proposals are queued. Generate proposals after a successful AI analysis when you want a fresh approval list.</div>';
    return;
  }
  box.innerHTML=items.map(p=>{
    const pending=p.status==="PENDING";
    const params=p.params||{};
    const paramLine=p.action_type==="RF_ABA_TEST"
      ?[params.apName,params.band!=null?params.band+" GHz":null,
        (params.proposedChannel!=null&&params.proposedWidthMHz!=null)?params.proposedChannel+" / "+params.proposedWidthMHz+" MHz":null].filter(Boolean).join(" · ")
      :"";
    const approveLabel=p.action_type==="REVIEW_SETTING"?"Acknowledge":"Approve";
    const controls=pending
      ?'<div class="proposal-controls"><button class="ai-proposal-approve" data-id="'+p.id+'">'+approveLabel+'</button><button class="secondary ai-proposal-reject" data-id="'+p.id+'">Reject</button></div>'
      :'';
    return '<div class="panel proposal-card">'+
      '<div class="proposal-head"><div><span class="eyebrow">'+esc(proposalActionLabel(p.action_type))+'</span><h3>'+esc(p.title||"Proposal")+'</h3></div><span class="status-tag '+proposalStatusClass(p.status)+'">'+esc(p.status)+'</span></div>'+
      (paramLine?'<div class="proposal-param">'+esc(paramLine)+'</div>':'')+
      '<p>'+esc(p.reason||"")+'</p>'+
      '<div class="proposal-meta"><div><span>Risk</span><b>'+esc(p.risk||"REVIEW")+'</b></div><div><span>Rollback / safety</span><b>'+esc(p.rollback||"No automatic change")+'</b></div></div>'+
      (p.execution_result?'<div class="muted proposal-result">'+esc(p.execution_result)+'</div>':'')+
      controls+
    '</div>';
  }).join("");
}

async function loadAiProposals(){
  try{
    const r=await fetch("/api/ai/proposals",{cache:"no-store"});
    const d=await r.json();
    if(d.ok)renderAiProposals(d.items||[]);
  }catch(e){
    const notice=document.getElementById("aiProposalNotice");
    if(notice)notice.innerHTML='<b class="warn">Unable to load approval queue</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}

async function refreshAiProposals(){
  const btn=document.getElementById("refreshAiProposalsBtn");
  const notice=document.getElementById("aiProposalNotice");
  if(btn){btn.disabled=true;btn.textContent="Generating…";}
  if(notice)notice.innerHTML='<b class="info">Generating a constrained approval queue…</b><br><span class="muted">Only whitelisted execution paths can become executable proposals.</span>';
  try{
    const r=await fetch("/api/ai/proposals/refresh",{method:"POST"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Unable to generate proposals");
    if(notice)notice.innerHTML='<b class="good">Approval queue refreshed</b><br><span class="muted">'+esc(d.generated||0)+' validated proposal'+(Number(d.generated||0)===1?"":"s")+' generated. Nothing has been changed.</span>';
    renderAiProposals(d.items||[]);
  }catch(e){
    if(notice)notice.innerHTML='<b class="warn">Proposal generation did not run</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Generate proposals";}
  }
}

async function actOnAiProposal(id,action){
  const verb=action==="approve"?"approve":"reject";
  if(action==="approve" && !confirm("Approve this proposal? Executable proposals can start only the whitelisted deterministic action shown on the card."))return;
  const r=await fetch("/api/ai/proposals/"+id+"/"+verb,{method:"POST"});
  const d=await r.json();
  if(!d.ok){
    alert(d.error||"Unable to update proposal.");
  }
  await loadAiProposals();
  if(action==="approve"){
    await loadOptimizationTests();
    await loadChannelPlan();
    await loadWiredAudit();
  }
}

document.getElementById("refreshAiProposalsBtn")?.addEventListener("click",refreshAiProposals);
document.addEventListener("click",e=>{
  const approve=e.target.closest(".ai-proposal-approve");
  if(approve){actOnAiProposal(Number(approve.dataset.id),"approve");return;}
  const reject=e.target.closest(".ai-proposal-reject");
  if(reject)actOnAiProposal(Number(reject.dataset.id),"reject");
});


async function copySupportSummary(){
  const status=document.getElementById("exportStatus");
  if(status)status.textContent="Building compact support summary…";
  try{
    const r=await fetch("/api/export/summary",{cache:"no-store"});
    const text=await r.text();
    if(!r.ok)throw new Error(text||"Unable to build summary");
    await navigator.clipboard.writeText(text);
    if(status)status.textContent="Compact support summary copied. Paste it directly into ChatGPT.";
  }catch(e){
    if(status)status.textContent="Copy failed: "+(e.message||e)+". You can use the JSON or ZIP download instead.";
  }
}

function downloadSupport(kind){
  const status=document.getElementById("exportStatus");
  if(status)status.textContent="Building sanitized support "+kind.toUpperCase()+"…";
  const url=kind==="zip"?"/api/export/support-bundle.zip":"/api/export/support-bundle.json";
  window.location.href=url;
  setTimeout(()=>{
    if(status)status.textContent="Support export requested. Upload the downloaded file into this ChatGPT conversation for analysis.";
  },1200);
}

document.getElementById("downloadSupportZipBtn")?.addEventListener("click",()=>downloadSupport("zip"));
document.getElementById("downloadSupportJsonBtn")?.addEventListener("click",()=>downloadSupport("json"));
document.getElementById("copySupportSummaryBtn")?.addEventListener("click",copySupportSummary);
document.getElementById("runAiAnalysisBtn")?.addEventListener("click",runAiAnalysisNow);
document.getElementById("aiAutoToggle")?.addEventListener("change",async e=>{
  const r=await fetch("/api/ai/settings",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({automaticEnabled:e.target.checked})
  });
  const d=await r.json();
  if(!d.ok){
    e.target.checked=false;
    const notice=document.getElementById("aiAdvisorNotice");
    if(notice)notice.innerHTML='<b class="warn">'+esc(d.error||"Unable to update AI settings")+'</b>';
  }
  await loadAiStatus();
});
document.getElementById("aiInterval")?.addEventListener("change",async e=>{
  await fetch("/api/ai/settings",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({intervalHours:Number(e.target.value)})
  });
  await loadAiStatus();
});

setInterval(()=>{
  if(document.querySelector("#exportai.page.active"))loadAiStatus();
},10000);


function renderSwitches(){
  const box=document.getElementById("switchContainer");box.innerHTML="";
  report.switches.forEach(sw=>{
    let rows="";
    (((sw.interfaces||{}).ports)||[]).forEach(p=>{
      const observed=p.state==="UP"&&p.maxSpeedMbps>=10000&&p.speedMbps<=100?' <span class="status-tag PROTECTED">OBSERVE</span>':"";
      rows+=`<tr><td>${esc(p.idx)}</td><td>${esc(p.connector)}</td><td>${esc(p.state)}</td><td>${speed(p.speedMbps)}${observed}</td><td>${speed(p.maxSpeedMbps)}</td></tr>`;
    });
    box.insertAdjacentHTML("beforeend",`<div class="switch-block"><h3>${esc(sw.name)}</h3><div class="muted">${esc(sw.model)} · uplink ${esc(sw.uplinkName||"Gateway")}</div><div class="panel table-wrap"><table><thead><tr><th>Port</th><th>Connector</th><th>State</th><th>Negotiated speed</th><th>Port capability</th></tr></thead><tbody>${rows}</tbody></table></div></div>`);
  });
}

document.getElementById("autoToggle").addEventListener("change",async e=>{
  await fetch("/api/auto-optimize",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:e.target.checked})});
  await loadReport();
});
document.getElementById("runOptimizeBtn").addEventListener("click",async()=>{
  const out=document.getElementById("optimizeResult");out.textContent="Running…";
  const btn=document.getElementById("runOptimizeBtn");btn.disabled=true;
  try{
    const r=await fetch("/api/auto-optimize/run",{method:"POST"});const d=await r.json();
    out.textContent=d.ok?d.results.map(x=>x.name+": "+x.status).join(" · "):"Optimization failed";
    await loadReport();await loadHistory();
  }finally{btn.disabled=false}
});
async function loadHistory(){
  const r=await fetch("/api/optimization-log",{cache:"no-store"});const d=await r.json();
  const t=document.getElementById("historyTable");t.innerHTML="";
  (d.items||[]).forEach(x=>t.insertAdjacentHTML("beforeend",`<tr><td>${esc(new Date(x.ts).toLocaleString())}</td><td>${esc(x.action)}</td><td>${esc(x.target)}</td><td>${esc(x.detail)}</td><td><span class="status-tag ${esc(x.result)}">${esc(x.result)}</span></td></tr>`));
}
loadReport();setInterval(loadReport,60000);


function renderRoamingSummary(items){
  const box=document.getElementById("roamingSummaryCards"); if(!box)return;
  const total=items.length;
  const active=items.filter(x=>x.roamCount24h>0).length;
  const frequent=items.filter(x=>x.status==="FREQUENT_ROAMING").length;
  const stable=items.filter(x=>x.status==="STABLE").length;
  box.innerHTML=
    `<div class="summary-card"><h3>Wireless clients tracked</h3><div class="big">${total}</div></div>`+
    `<div class="summary-card"><h3>Roamed in 24h</h3><div class="big">${active}</div></div>`+
    `<div class="summary-card"><h3>Stable</h3><div class="big good">${stable}</div></div>`+
    `<div class="summary-card"><h3>Frequent roaming</h3><div class="big ${frequent?"warn":"good"}">${frequent}</div></div>`;
}

async function loadRoaming(){
  const r=await fetch("/api/roaming",{cache:"no-store"}); const d=await r.json();
  if(!d.ok)return;
  renderRoamingSummary(d.clients||[]);
  const ct=document.getElementById("roamingClientTable"); ct.innerHTML="";
  (d.clients||[]).forEach(x=>{
    const cls=x.status==="FREQUENT_ROAMING"?"NEEDS_ATTENTION":x.status==="STABLE"?"ALREADY_OPTIMIZED":"PROTECTED";
    ct.insertAdjacentHTML("beforeend",
      `<tr><td>${esc(x.name)}</td><td>${esc(x.currentApName)}</td><td>${esc(x.roamCount24h)}</td><td>${x.lastRoam?esc(new Date(x.lastRoam.ts).toLocaleString()):"—"}</td><td><span class="status-tag ${cls}">${esc(x.status)}</span></td></tr>`);
  });
  const et=document.getElementById("roamEventTable"); et.innerHTML="";
  (d.events||[]).forEach(x=>et.insertAdjacentHTML("beforeend",
    `<tr><td>${esc(new Date(x.ts).toLocaleString())}</td><td>${esc(x.name)}</td><td>${esc(x.from_ap_name)}</td><td>${esc(x.to_ap_name)}</td></tr>`));
}


function svgLine(values,maxValue,klass){
  const points=values.map((v,i)=>{
    if(v==null)return null;
    const x=values.length<=1?0:(i/(values.length-1))*800;
    const y=210-(Math.max(0,v)/(maxValue||1))*190;
    return [x,y];
  });
  let d="",pen=false;
  for(const p of points){
    if(!p){pen=false;continue}
    d+=(pen?" L ":"M ")+p[0].toFixed(1)+" "+p[1].toFixed(1);
    pen=true;
  }
  return d?'<path class="'+klass+'" d="'+d+'" fill="none" vector-effect="non-scaling-stroke"/>':"";
}
function chartGrid(){
  return '<path class="chart-grid-line" d="M0 20H800 M0 67.5H800 M0 115H800 M0 162.5H800 M0 210H800" vector-effect="non-scaling-stroke"/>';
}
function renderInternet(inet,gateway){
  if(!inet)return;
  const latest=inet.latest||{};
  const stats=gateway?.statistics||{};
  const uplink=stats.uplink||{};
  const set=(id,val,cls)=>{
    const el=document.getElementById(id);
    if(!el)return;
    el.textContent=val;
    if(cls)el.className="big "+cls;
  };
  set("internetStatus",inet.latest?(latest.online?"ONLINE":"OFFLINE"):"LEARNING",inet.latest?(latest.online?"good":"bad"):"info");
  set("internetAvailability",inet.availabilityPct==null?"—":inet.availabilityPct.toFixed(2)+"%",inet.availabilityPct!=null&&inet.availabilityPct>=99?"good":inet.availabilityPct!=null&&inet.availabilityPct>=95?"warn":"bad");
  set("internetUpFor",sinceDuration(inet.onlineSince),"");
  set("gatewayUptime",duration(stats.uptimeSec),"");
  set("internetDownload",rateMbps(latest.rx_bps??uplink.rxRateBps),"");
  set("internetUpload",rateMbps(latest.tx_bps??uplink.txRateBps),"");
  set("internetLatency",latest.latency_ms==null?"—":latest.latency_ms.toFixed(0)+" ms",latest.latency_ms!=null&&latest.latency_ms<50?"good":latest.latency_ms!=null&&latest.latency_ms<100?"warn":"bad");
  set("internetOutages",String(inet.outageCount??0),(inet.outageCount||0)===0?"good":"warn");

  const samples=inet.samples||[];
  const rx=samples.map(x=>typeof x.rx_bps==="number"?x.rx_bps/1000000:null);
  const tx=samples.map(x=>typeof x.tx_bps==="number"?x.tx_bps/1000000:null);
  const maxT=Math.max(1,...rx.filter(Number.isFinite),...tx.filter(Number.isFinite));
  const tc=document.getElementById("throughputChart");
  if(tc)tc.innerHTML=chartGrid()+svgLine(rx,maxT,"chart-line-rx")+svgLine(tx,maxT,"chart-line-tx");

  const lat=samples.map(x=>x.online&&typeof x.latency_ms==="number"?x.latency_ms:null);
  const maxL=Math.max(50,...lat.filter(Number.isFinite));
  const lc=document.getElementById("latencyChart");
  if(lc)lc.innerHTML=chartGrid()+svgLine(lat,maxL,"chart-line-latency");
  const ls=document.getElementById("latencySummary");
  if(ls)ls.innerHTML="<span>24h avg: "+(inet.avgLatencyMs==null?"—":inet.avgLatencyMs.toFixed(0)+" ms")+"</span><span>24h peak: "+(inet.maxLatencyMs==null?"—":inet.maxLatencyMs.toFixed(0)+" ms")+"</span>";
}
async function loadInternet(){
  const r=await fetch("/api/internet",{cache:"no-store"});
  const d=await r.json();
  if(d.ok)renderInternet(d,report?.gateway);
}


let wanQualityData=null;

function pct(v,digits=2){
  return v==null?"—":Number(v).toFixed(digits)+"%";
}
function qualityClass(score){
  if(score==null)return "info";
  if(score>=90)return "good";
  if(score>=75)return "info";
  if(score>=60)return "warn";
  return "bad";
}
function metricClassLower(v,good,watch,bad){
  if(v==null)return "";
  if(v<=good)return "good";
  if(v<=watch)return "info";
  if(v<=bad)return "warn";
  return "bad";
}
function renderWanQuality(d){
  wanQualityData=d;
  const set=(id,value,cls)=>{
    const el=document.getElementById(id);
    if(!el)return;
    el.textContent=value;
    if(cls!==undefined)el.className="big "+cls;
  };

  set("wanQualityScore",d.score==null?"—":String(d.score),qualityClass(d.score));
  const reach=d.reachabilityPct;
  set("wanReachability",pct(reach,3),reach==null?"info":reach>=99.9?"good":reach>=99?"info":reach>=97?"warn":"bad");
  set("wanAvgLatency",d.avgLatencyMs==null?"—":Number(d.avgLatencyMs).toFixed(1)+" ms",metricClassLower(d.avgLatencyMs,30,60,100));
  set("wanAvgJitter",d.avgJitterMs==null?"—":Number(d.avgJitterMs).toFixed(1)+" ms",metricClassLower(d.avgJitterMs,5,10,20));
  const dnsSuccess=d.dnsSuccessPct;
  set("wanDnsSuccess",pct(dnsSuccess,2),dnsSuccess==null?"info":dnsSuccess>=99.9?"good":dnsSuccess>=99?"info":dnsSuccess>=97?"warn":"bad");
  set("wanDnsLatency",d.dnsAvgLatencyMs==null?"—":Number(d.dnsAvgLatencyMs).toFixed(1)+" ms",metricClassLower(d.dnsAvgLatencyMs,30,60,120));
  const gw=d.gateway||{};
  set("wanGatewayLatency",gw.avg_ms==null?"—":Number(gw.avg_ms).toFixed(1)+" ms",metricClassLower(gw.avg_ms,5,15,30));
  const last=document.getElementById("wanLastSample");
  if(last)last.textContent=d.lastSampleAt?fmtShortDate(d.lastSampleAt):"Learning…";

  const notice=document.getElementById("wanQualityNotice");
  if(notice){
    if(d.lastError){
      notice.innerHTML='<b class="warn">Some WAN probes reported errors</b><br><span class="muted">'+esc(d.lastError)+'</span>';
    }else if(!d.lastSampleAt){
      notice.innerHTML='<b class="info">Learning WAN quality</b><br><span class="muted">The first multi-target probe will be stored automatically by the monitor.</span>';
    }else{
      notice.innerHTML='<b class="good">WAN quality monitoring active</b><br><span class="muted">ICMP every '+esc(d.sampleIntervalSeconds||60)+' seconds · DNS every '+Math.round(Number(d.dnsSampleIntervalSeconds||300)/60)+' minutes · selected range '+esc(trafficRangeLabel(d.hours||24))+'.</span>';
    }
  }

  const ps=d.pingSeries||[];
  const lat=ps.map(x=>typeof x.avg_ms==="number"?x.avg_ms:null);
  const loss=ps.map(x=>typeof x.packet_loss_pct==="number"?x.packet_loss_pct:null);
  const jitter=ps.map(x=>typeof x.jitter_ms==="number"?x.jitter_ms:null);
  const maxLat=Math.max(30,...lat.filter(Number.isFinite));
  const maxLoss=Math.max(5,...loss.filter(Number.isFinite));
  const maxJitter=Math.max(10,...jitter.filter(Number.isFinite));

  const latChart=document.getElementById("wanLatencyChart");
  if(latChart)latChart.innerHTML=chartGrid()+svgLine(lat,maxLat,"chart-line-latency");
  const lossChart=document.getElementById("wanLossChart");
  if(lossChart)lossChart.innerHTML=chartGrid()+svgLine(loss,maxLoss,"chart-line-loss");
  const jitterChart=document.getElementById("wanJitterChart");
  if(jitterChart)jitterChart.innerHTML=chartGrid()+svgLine(jitter,maxJitter,"chart-line-jitter");

  const ds=d.dnsSeries||[];
  const dnsLat=ds.map(x=>typeof x.avg_latency_ms==="number"?x.avg_latency_ms:null);
  const maxDns=Math.max(30,...dnsLat.filter(Number.isFinite));
  const dnsChart=document.getElementById("wanDnsChart");
  if(dnsChart)dnsChart.innerHTML=chartGrid()+svgLine(dnsLat,maxDns,"chart-line-dns");

  const targetTable=document.getElementById("wanTargetTable");
  if(targetTable){
    const rows=d.targets||[];
    targetTable.innerHTML=rows.length?rows.map(x=>
      '<tr>'+
        '<td><b>'+esc(x.target_name)+'</b></td>'+
        '<td>'+esc(x.target_type)+'</td>'+
        '<td class="client-ip">'+esc(x.target_host)+'</td>'+
        '<td>'+esc(x.sent||0)+'</td>'+
        '<td>'+esc(x.received||0)+'</td>'+
        '<td class="'+(Number(x.packet_loss_pct||0)===0?"good":Number(x.packet_loss_pct||0)<1?"info":Number(x.packet_loss_pct||0)<5?"warn":"bad")+'">'+esc(pct(x.packet_loss_pct,2))+'</td>'+
        '<td>'+esc(x.avg_ms==null?"—":Number(x.avg_ms).toFixed(1)+" ms")+'</td>'+
        '<td>'+esc(x.jitter_ms==null?"—":Number(x.jitter_ms).toFixed(1)+" ms")+'</td>'+
        '<td>'+esc((x.min_ms==null?"—":Number(x.min_ms).toFixed(1))+" / "+(x.max_ms==null?"—":Number(x.max_ms).toFixed(1))+" ms")+'</td>'+
      '</tr>'
    ).join(""):'<tr><td colspan="9"><div class="empty">No WAN ping samples yet.</div></td></tr>';
  }

  const dnsTable=document.getElementById("wanDnsTable");
  if(dnsTable){
    const rows=d.dnsResolvers||[];
    dnsTable.innerHTML=rows.length?rows.map(x=>
      '<tr>'+
        '<td><b>'+esc(x.resolver_name)+'</b></td>'+
        '<td class="client-ip">'+esc(x.resolver_host||"System")+'</td>'+
        '<td>'+esc(x.samples||0)+'</td>'+
        '<td class="'+(Number(x.success_pct||0)>=99.9?"good":Number(x.success_pct||0)>=99?"info":Number(x.success_pct||0)>=97?"warn":"bad")+'">'+esc(pct(x.success_pct,2))+'</td>'+
        '<td>'+esc(x.avg_latency_ms==null?"—":Number(x.avg_latency_ms).toFixed(1)+" ms")+'</td>'+
        '<td>'+esc(x.min_latency_ms==null?"—":Number(x.min_latency_ms).toFixed(1)+" ms")+'</td>'+
        '<td>'+esc(x.max_latency_ms==null?"—":Number(x.max_latency_ms).toFixed(1)+" ms")+'</td>'+
      '</tr>'
    ).join(""):'<tr><td colspan="7"><div class="empty">No DNS probe history yet.</div></td></tr>';
  }
}

async function loadWanQuality(){
  const hours=Number(document.getElementById("wanQualityRange")?.value||24);
  try{
    const r=await fetch("/api/wan-quality?hours="+encodeURIComponent(hours),{cache:"no-store"});
    const d=await r.json();
    if(d.ok)renderWanQuality(d);
  }catch(e){
    const notice=document.getElementById("wanQualityNotice");
    if(notice)notice.innerHTML='<b class="warn">Unable to load WAN quality</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}

document.getElementById("wanQualityRange")?.addEventListener("change",loadWanQuality);
setInterval(()=>{
  if(document.querySelector("#wanquality.page.active"))loadWanQuality();
},30000);


let trafficData=null;

function trafficRangeLabel(hours){
  if(Number(hours)===1)return "last hour";
  if(Number(hours)===24)return "last 24 hours";
  if(Number(hours)===168)return "last 7 days";
  if(Number(hours)===720)return "last 30 days";
  return "selected period";
}

function trafficIpCompare(a,b){
  const ap=clientIpParts(a||"");const bp=clientIpParts(b||"");
  for(let i=0;i<Math.max(ap.length,bp.length);i++){
    const x=ap[i]??"";const y=bp[i]??"";
    if(x===y)continue;
    return x<y?-1:1;
  }
  return 0;
}

function setTrafficSelectOptions(id,values,label){
  const el=document.getElementById(id);
  if(!el)return;
  const current=el.value;
  const unique=[...new Set(values.filter(v=>v!==null&&v!==undefined&&String(v)!=="").map(v=>String(v)))].sort((a,b)=>a.localeCompare(b,undefined,{numeric:true,sensitivity:"base"}));
  el.innerHTML='<option value="">'+esc(label)+'</option>'+unique.map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join("");
  if(unique.includes(current))el.value=current;
}

function trafficFilteredClients(){
  if(!trafficData)return [];
  const rows=[...(trafficData.usage?.topClients||[])];
  const q=(document.getElementById("trafficClientSearch")?.value||"").trim().toLowerCase();
  const ap=document.getElementById("trafficApFilter")?.value||"";
  const vlan=document.getElementById("trafficVlanFilter")?.value||"";
  const network=document.getElementById("trafficNetworkFilter")?.value||"";
  const sort=document.getElementById("trafficClientSort")?.value||"total-desc";

  const filtered=rows.filter(x=>{
    if(q && ![x.name,x.ip,x.mac].some(v=>String(v||"").toLowerCase().includes(q)))return false;
    if(ap && String(x.uplink_name||"Unknown")!==ap)return false;
    if(vlan && String(x.vlan_id??"Unknown")!==vlan)return false;
    if(network && String(x.network_name||"Unknown")!==network)return false;
    return true;
  });

  filtered.sort((a,b)=>{
    if(sort==="total-desc")return Number(b.total_bytes||0)-Number(a.total_bytes||0);
    if(sort==="total-asc")return Number(a.total_bytes||0)-Number(b.total_bytes||0);
    if(sort==="rx-desc")return Number(b.rx_bytes||0)-Number(a.rx_bytes||0);
    if(sort==="tx-desc")return Number(b.tx_bytes||0)-Number(a.tx_bytes||0);
    if(sort==="ip-asc")return trafficIpCompare(a.ip,b.ip);
    return String(a.name||a.mac||"").localeCompare(String(b.name||b.mac||""),undefined,{numeric:true,sensitivity:"base"});
  });
  return filtered;
}

function renderTrafficClients(){
  const table=document.getElementById("trafficClientTable");
  if(!table||!trafficData)return;
  const rows=trafficFilteredClients();
  table.innerHTML=rows.length?rows.map(x=>
    '<tr>'+
      '<td><b>'+esc(x.name||x.mac||"Unknown")+'</b><div class="muted">'+esc(x.mac||"")+'</div></td>'+
      '<td class="client-ip">'+esc(x.ip||"—")+'</td>'+
      '<td><span class="vlan-pill">VLAN '+esc(x.vlan_id??"Unknown")+'</span></td>'+
      '<td>'+esc(x.network_name||"Unknown")+'</td>'+
      '<td>'+esc(x.uplink_name||"Unknown")+'</td>'+
      '<td>'+esc(bytes(x.rx_bytes||0))+'</td>'+
      '<td>'+esc(bytes(x.tx_bytes||0))+'</td>'+
      '<td><b>'+esc(bytes(x.total_bytes||0))+'</b></td>'+
    '</tr>'
  ).join(""):'<tr><td colspan="8"><div class="empty">No traffic records match the selected filters yet.</div></td></tr>';
}

function renderTraffic(d){
  trafficData=d;
  const usage=d.usage||{};
  const totals=usage.totals||{};
  const dpi=d.dpi||{};
  const live=d.live||{};
  const topClient=(usage.topClients||[])[0];
  const topApp=(dpi.apps||[])[0];
  const hours=d.hours||24;

  const set=(id,value)=>{const el=document.getElementById(id);if(el)el.textContent=value};
  set("trafficLiveRx",rateMbps(live.rxRateBps||0));
  set("trafficLiveTx",rateMbps(live.txRateBps||0));
  const total=Number(totals.rx_bytes||0)+Number(totals.tx_bytes||0);
  set("trafficTotalUsage",bytes(total));
  set("trafficTotalUsageDetail",trafficRangeLabel(hours)+" · RX "+bytes(totals.rx_bytes||0)+" · TX "+bytes(totals.tx_bytes||0));
  set("trafficClientCount",String(totals.client_count||0));
  set("trafficTopClient",topClient?(topClient.name||topClient.mac||"Unknown"):"—");
  set("trafficTopClientUsage",topClient?bytes(topClient.total_bytes||0)+" in "+trafficRangeLabel(hours):"Learning…");
  set("trafficTopApp",topApp?(topApp.app_name||"Unknown"):"—");
  set("trafficTopAppUsage",topApp?bytes(topApp.total_bytes||0)+" · "+(topApp.category_name||"Unknown"):"Learning DPI…");

  const notice=document.getElementById("trafficNotice");
  if(notice){
    if(!d.privateConfigured){
      notice.innerHTML='<b class="warn">Traffic details unavailable</b><br><span class="muted">The local UniFi private API credentials are required for per-client counters and DPI analytics.</span>';
    }else if(d.lastError){
      notice.innerHTML='<b class="warn">Traffic collector reported an error</b><br><span class="muted">'+esc(d.lastError)+'</span>';
    }else{
      notice.innerHTML='<b class="good">Traffic monitoring active</b><br><span class="muted">Samples every '+Math.round(Number(d.sampleIntervalSeconds||300)/60)+' minutes · last sample '+esc(d.lastSampleAt?fmtDateTime(d.lastSampleAt):"learning")+'. RX/TX follow the controller counters; exact encrypted destinations are not inferred.</span>';
    }
  }

  const series=usage.series||[];
  const rx=series.map(x=>Number(x.rx_bytes||0));
  const tx=series.map(x=>Number(x.tx_bytes||0));
  const max=Math.max(1,...rx,...tx);
  const chart=document.getElementById("trafficUsageChart");
  if(chart)chart.innerHTML=chartGrid()+svgLine(rx,max,"chart-line-rx")+svgLine(tx,max,"chart-line-tx");

  const cats=dpi.categories||[];
  const catBox=document.getElementById("trafficCategoryBars");
  if(catBox){
    const maxCat=Math.max(1,...cats.slice(0,8).map(x=>Number(x.total_bytes||0)));
    catBox.innerHTML=cats.length?cats.slice(0,8).map(x=>{
      const pct=Math.max(2,Math.min(100,(Number(x.total_bytes||0)/maxCat)*100));
      return '<div class="traffic-bar-row"><div class="traffic-bar-label"><span>'+esc(x.category_name||"Unknown")+'</span><b>'+esc(bytes(x.total_bytes||0))+'</b></div><div class="traffic-bar-track"><div class="traffic-bar-fill" style="width:'+pct.toFixed(1)+'%"></div></div></div>';
    }).join(""):'<div class="empty">DPI history is learning. Application totals will appear after at least two traffic samples.</div>';
  }

  setTrafficSelectOptions("trafficApFilter",(usage.topClients||[]).map(x=>x.uplink_name||"Unknown"),"All APs / uplinks");
  setTrafficSelectOptions("trafficVlanFilter",(usage.topClients||[]).map(x=>x.vlan_id??"Unknown"),"All VLANs");
  setTrafficSelectOptions("trafficNetworkFilter",(usage.topClients||[]).map(x=>x.network_name||"Unknown"),"All networks");
  renderTrafficClients();

  const vlanTable=document.getElementById("trafficVlanTable");
  if(vlanTable){
    const rows=usage.topVlans||[];
    vlanTable.innerHTML=rows.length?rows.map(x=>
      '<tr><td><span class="vlan-pill">VLAN '+esc(x.vlan_id??"Unknown")+'</span></td><td>'+esc(x.network_name||"Unknown")+'</td><td>'+esc(x.client_count||0)+'</td><td>'+esc(bytes(x.rx_bytes||0))+'</td><td>'+esc(bytes(x.tx_bytes||0))+'</td><td><b>'+esc(bytes(x.total_bytes||0))+'</b></td></tr>'
    ).join(""):'<tr><td colspan="6"><div class="empty">No VLAN usage history yet.</div></td></tr>';
  }

  const uplinkTable=document.getElementById("trafficUplinkTable");
  if(uplinkTable){
    const rows=usage.topUplinks||[];
    uplinkTable.innerHTML=rows.length?rows.map(x=>
      '<tr><td>'+esc(x.uplink_name||"Unknown")+'</td><td>'+esc(x.client_count||0)+'</td><td>'+esc(bytes(x.rx_bytes||0))+'</td><td>'+esc(bytes(x.tx_bytes||0))+'</td><td><b>'+esc(bytes(x.total_bytes||0))+'</b></td></tr>'
    ).join(""):'<tr><td colspan="5"><div class="empty">No AP/uplink usage history yet.</div></td></tr>';
  }

  const appTable=document.getElementById("trafficAppTable");
  if(appTable){
    const rows=dpi.apps||[];
    appTable.innerHTML=rows.length?rows.map(x=>
      '<tr><td><b>'+esc(x.app_name||"Unknown")+'</b></td><td>'+esc(x.category_name||"Unknown")+'</td><td>'+esc(bytes(x.rx_bytes||0))+'</td><td>'+esc(bytes(x.tx_bytes||0))+'</td><td><b>'+esc(bytes(x.total_bytes||0))+'</b></td></tr>'
    ).join(""):'<tr><td colspan="5"><div class="empty">UniFi DPI application history is still learning or DPI did not return classified traffic.</div></td></tr>';
  }
}

async function loadTrafficDiagnostics(){
  const panel=document.getElementById("trafficDiagnosticsPanel");
  const content=document.getElementById("trafficDiagnosticsContent");
  if(panel)panel.style.display="block";
  if(content)content.innerHTML='<div><span>Status</span><b>Reading collector structure…</b></div>';
  try{
    const r=await fetch("/api/traffic/diagnostics",{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Unable to load diagnostics");
    const coverage=Object.entries(d.counterCoverage||{}).map(([k,v])=>k+" "+v.nonzero+"/"+v.present+" nonzero").join(" · ")||"No supported counter fields found";
    const stationKeys=(d.stationKeys||[]).join(", ")||"None";
    const dpiKeys=(d.dpiKeys||[]).join(", ")||"None";
    const stationDpiKeys=(d.stationDpiKeys||[]).join(", ")||"None";
    if(content)content.innerHTML=
      '<div><span>Classic/private API</span><b>'+(d.privateConfigured?"Configured":"Not configured")+'</b></div>'+
      '<div><span>Stations returned</span><b>'+esc(d.stationCount||0)+'</b></div>'+
      '<div><span>Counter coverage</span><b>'+esc(coverage)+'</b></div>'+
      '<div><span>Stored clients / 24h</span><b>'+esc(d.databaseClientCount||0)+'</b></div>'+
      '<div><span>Stored traffic / 24h</span><b>RX '+esc(bytes(d.databaseRxBytes||0))+' · TX '+esc(bytes(d.databaseTxBytes||0))+'</b></div>'+
      '<div><span>DPI tables</span><b>'+esc(d.dpiTableCount||0)+' · apps '+esc(d.dpiByAppCount||0)+' · categories '+esc(d.dpiByCategoryCount||0)+'</b></div>'+
      '<div><span>Station DPI rows</span><b>'+esc(d.stationDpiCount||0)+'</b></div>'+
      '<div><span>Station keys</span><b class="diagnostic-keys">'+esc(stationKeys)+'</b></div>'+
      '<div><span>Site DPI keys</span><b class="diagnostic-keys">'+esc(dpiKeys)+'</b></div>'+
      '<div><span>Station DPI keys</span><b class="diagnostic-keys">'+esc(stationDpiKeys)+'</b></div>'+
      '<div><span>Last sample</span><b>'+esc(d.lastSampleAt?fmtDateTime(d.lastSampleAt):"Never")+'</b></div>'+
      '<div><span>Last error</span><b>'+esc(d.lastError||d.dpiError||"None")+'</b></div>';
  }catch(e){
    if(content)content.innerHTML='<div><span>Diagnostics error</span><b class="bad">'+esc(e.message||e)+'</b></div>';
  }
}

async function sampleTrafficNow(){
  const btn=document.getElementById("trafficSampleNowBtn");
  const notice=document.getElementById("trafficNotice");
  if(btn){btn.disabled=true;btn.textContent="Sampling…";}
  try{
    const r=await fetch("/api/traffic/sample",{method:"POST"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Traffic sample failed");
    if(notice)notice.innerHTML='<b class="good">Manual traffic sample completed</b><br><span class="muted">Historical byte usage needs two counter samples with traffic between them. Run another sample after a few minutes of network activity if totals are still zero.</span>';
    await loadTraffic();
    if(document.getElementById("trafficDiagnosticsPanel")?.style.display!=="none")await loadTrafficDiagnostics();
  }catch(e){
    if(notice)notice.innerHTML='<b class="warn">Traffic sample failed</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Sample now";}
  }
}

async function loadTraffic(){
  const hours=Number(document.getElementById("trafficRange")?.value||24);
  try{
    const r=await fetch("/api/traffic?hours="+encodeURIComponent(hours),{cache:"no-store"});
    const d=await r.json();
    if(d.ok)renderTraffic(d);
  }catch(e){
    const notice=document.getElementById("trafficNotice");
    if(notice)notice.innerHTML='<b class="warn">Unable to load traffic analytics</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}

document.getElementById("trafficRange")?.addEventListener("change",loadTraffic);
document.getElementById("trafficSampleNowBtn")?.addEventListener("click",sampleTrafficNow);
document.getElementById("trafficDiagnosticsBtn")?.addEventListener("click",loadTrafficDiagnostics);
document.getElementById("trafficDiagnosticsCloseBtn")?.addEventListener("click",()=>{
  const panel=document.getElementById("trafficDiagnosticsPanel");
  if(panel)panel.style.display="none";
});
["trafficClientSearch","trafficApFilter","trafficVlanFilter","trafficNetworkFilter","trafficClientSort"].forEach(id=>{
  const el=document.getElementById(id);
  if(!el)return;
  el.addEventListener(id==="trafficClientSearch"?"input":"change",renderTrafficClients);
});
setInterval(()=>{
  if(document.querySelector("#traffic.page.active"))loadTraffic();
},30000);


function fmtMbps(v){
  return v==null?"—":Number(v).toFixed(Number(v)>=1000?0:1)+" Mbps";
}
function fmtMs(v){
  return v==null?"—":Number(v).toFixed(1)+" ms";
}
function fmtShortDate(v){
  try{
    if(!v)return "—";
    return new Date(v).toLocaleString([],{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
  }catch{return "—"}
}
function speedtestClass(download,ping){
  if(download==null)return "";
  if(ping!=null&&ping>=100)return "bad";
  if(ping!=null&&ping>=50)return "warn";
  return "good";
}
function renderSpeedtest(d){
  const latest=d.latestSuccess||null;
  const stats=d.stats||{};
  const hist=(d.history||[]);

  const dl=document.getElementById("speedtestDownload");
  const ul=document.getElementById("speedtestUpload");
  const pg=document.getElementById("speedtestPing");
  const jit=document.getElementById("speedtestJitter");
  const loss=document.getElementById("speedtestPacketLoss");
  const srv=document.getElementById("speedtestServer");
  const srvDetail=document.getElementById("speedtestServerDetail");
  const last=document.getElementById("speedtestLastRun");
  const dur=document.getElementById("speedtestLastDuration");
  const next=document.getElementById("speedtestNextRun");
  const notice=document.getElementById("speedtestNotice");
  const toggle=document.getElementById("speedtestAutoToggle");
  const interval=document.getElementById("speedtestInterval");

  if(dl)dl.textContent=latest?fmtMbps(latest.download_mbps):"—";
  if(ul)ul.textContent=latest?fmtMbps(latest.upload_mbps):"—";
  if(pg)pg.textContent=latest?fmtMs(latest.ping_ms):"—";
  if(jit)jit.textContent=latest&&latest.jitter_ms!=null?fmtMs(latest.jitter_ms):"—";
  if(loss)loss.textContent=latest&&latest.packet_loss_pct!=null?Number(latest.packet_loss_pct).toFixed(2)+"%":"—";
  if(srv)srv.textContent=latest?(latest.server_sponsor||latest.server_name||"—"):"—";
  if(srvDetail)srvDetail.textContent=latest?([
    latest.server_location||latest.server_name,
    latest.server_country,
    latest.server_id?"ID "+latest.server_id:null
  ].filter(Boolean).join(" · ")||"—"):"—";
  if(last)last.textContent=d.latest?fmtShortDate(d.latest.ts):"Never";
  if(dur)dur.textContent=d.latest?.duration_sec!=null?"Completed in "+Number(d.latest.duration_sec).toFixed(0)+" sec":"—";
  if(next)next.textContent=d.enabled?(d.nextDue?fmtShortDate(d.nextDue):"Due now"):"Disabled";
  if(toggle)toggle.checked=!!d.enabled;
  if(interval)interval.value=String(d.intervalHours||6);
  const preferred=document.getElementById("speedtestPreferredServer");
  if(preferred){
    const value=String(d.preferredServerId||"");
    if(value && ![...preferred.options].some(o=>o.value===value)){
      preferred.insertAdjacentHTML("beforeend",'<option value="'+esc(value)+'">Preferred server ID '+esc(value)+'</option>');
    }
    preferred.value=value;
  }
  const selectionStatus=document.getElementById("speedtestServerSelectionStatus");
  if(selectionStatus){
    selectionStatus.textContent=(d.engine==="OOKLA_OFFICIAL"?"Official Ookla CLI":"Speedtest engine")+
      " · "+(d.preferredServerId?"locked to server ID "+d.preferredServerId:"automatic nearby selection")+
      (d.engineAvailable===false?" · CLI unavailable":"");
  }

  if(notice){
    if(d.running){
      notice.innerHTML='<b class="info">Speed test running…</b><br><span class="muted">This can take about a minute. Results will appear automatically when complete.</span>';
    }else if(d.deferredByRfTest){
      notice.innerHTML='<b class="warn">Automatic speed test paused during active RF testing</b><br><span class="muted">It will resume after the A/B/A RF test finishes so WAN traffic does not interfere with RF measurements.</span>';
    }else if(d.latest && !d.latest.success){
      notice.innerHTML='<b class="warn">Last speed test failed</b><br><span class="muted">'+esc(d.latest.error||d.lastError||"Unknown speed test error")+'</span>';
    }else if(latest){
      notice.innerHTML='<b class="good">Automatic speed testing active</b><br><span class="muted">Every '+esc(d.intervalHours)+' hour'+(Number(d.intervalHours)===1?"":"s")+' · '+esc(stats.successful_runs||0)+' successful runs in the last 30 days.</span>';
    }else{
      notice.innerHTML='<b class="info">Waiting for first speed test</b><br><span class="muted">Automatic testing is '+(d.enabled?"enabled":"disabled")+'.</span>';
    }
  }

  const success=hist.filter(x=>x.success);
  const downloads=success.map(x=>typeof x.download_mbps==="number"?x.download_mbps:null);
  const uploads=success.map(x=>typeof x.upload_mbps==="number"?x.upload_mbps:null);
  const pings=success.map(x=>typeof x.ping_ms==="number"?x.ping_ms:null);
  const maxSpeed=Math.max(10,...downloads.filter(Number.isFinite),...uploads.filter(Number.isFinite));
  const maxPing=Math.max(20,...pings.filter(Number.isFinite));

  const speedChart=document.getElementById("speedtestSpeedChart");
  if(speedChart)speedChart.innerHTML=chartGrid()+svgLine(downloads,maxSpeed,"chart-line-rx")+svgLine(uploads,maxSpeed,"chart-line-tx");
  const pingChart=document.getElementById("speedtestPingChart");
  if(pingChart)pingChart.innerHTML=chartGrid()+svgLine(pings,maxPing,"chart-line-latency");

  const speedSummary=document.getElementById("speedtestSpeedSummary");
  if(speedSummary)speedSummary.textContent=success.length?"Avg "+fmtMbps(stats.avg_download)+" down · "+fmtMbps(stats.avg_upload)+" up":"No history yet";
  const pingSummary=document.getElementById("speedtestPingSummary");
  if(pingSummary)pingSummary.textContent=success.length?"Avg "+fmtMs(stats.avg_ping)+" · Best "+fmtMs(stats.min_ping):"No history yet";

  const table=document.getElementById("speedtestHistoryTable");
  if(table){
    const rows=[...hist].reverse();
    table.innerHTML=rows.length?rows.map(x=>{
      const status=x.success?'<span class="status-tag SUCCESS">SUCCESS</span>':'<span class="status-tag FAILED">FAILED</span>';
      const server=x.success?([
        x.server_sponsor,
        x.server_location||x.server_name,
        x.server_country,
        x.server_id?"ID "+x.server_id:null
      ].filter(Boolean).join(" · ")||"—"):"—";
      return '<tr>'+
        '<td>'+esc(fmtDateTime(x.ts))+'</td>'+
        '<td>'+esc(x.success?fmtMbps(x.download_mbps):"—")+'</td>'+
        '<td>'+esc(x.success?fmtMbps(x.upload_mbps):"—")+'</td>'+
        '<td>'+esc(x.success?fmtMs(x.ping_ms):"—")+'</td>'+
        '<td>'+esc(x.success&&x.jitter_ms!=null?fmtMs(x.jitter_ms):"—")+'</td>'+
        '<td>'+esc(x.success&&x.packet_loss_pct!=null?Number(x.packet_loss_pct).toFixed(2)+"%":"—")+'</td>'+
        '<td>'+esc(server)+'</td>'+
        '<td>'+esc(x.duration_sec==null?"—":Number(x.duration_sec).toFixed(0)+" sec")+'</td>'+
        '<td>'+status+(x.error?'<div class="muted">'+esc(x.error)+'</div>':"")+'</td>'+
      '</tr>';
    }).join(""):'<tr><td colspan="9"><div class="empty">No speed test history yet.</div></td></tr>';
  }

  const btn=document.getElementById("runSpeedtestBtn");
  if(btn){
    btn.disabled=!!d.running||!!d.deferredByRfTest;
    btn.textContent=d.running?"Speed Test Running…":"Run Speed Test Now";
  }
}

async function loadSpeedtest(){
  try{
    const r=await fetch("/api/speedtest",{cache:"no-store"});
    const d=await r.json();
    if(d.ok)renderSpeedtest(d);
  }catch{}
}

async function loadSpeedtestServers(){
  const btn=document.getElementById("loadSpeedtestServersBtn");
  const select=document.getElementById("speedtestPreferredServer");
  const status=document.getElementById("speedtestServerSelectionStatus");
  if(btn){btn.disabled=true;btn.textContent="Loading…";}
  if(status)status.textContent="Asking Ookla for nearby servers…";
  try{
    const r=await fetch("/api/speedtest/servers",{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Unable to list servers");
    const current=String(report?.speedtestPreferredServerId||select?.value||"");
    if(select){
      select.innerHTML='<option value="">Automatic · Ookla nearby selection</option>'+
        (d.servers||[]).map(s=>
          '<option value="'+esc(s.id)+'">'+esc(s.name)+' · '+esc(s.location)+' · '+esc(s.country)+' · ID '+esc(s.id)+'</option>'
        ).join("");
      if(current && [...select.options].some(o=>o.value===current))select.value=current;
    }
    if(status)status.textContent=(d.servers||[]).length+" nearby server"+((d.servers||[]).length===1?"":"s")+" returned by official Ookla CLI";
  }catch(e){
    if(status)status.textContent="Server list error: "+(e.message||e);
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Load nearby servers";}
  }
}

async function runSpeedtestNow(){
  const btn=document.getElementById("runSpeedtestBtn");
  if(btn){btn.disabled=true;btn.textContent="Starting…";}
  try{
    const r=await fetch("/api/speedtest/run",{method:"POST"});
    const d=await r.json();
    if(!d.ok){
      const notice=document.getElementById("speedtestNotice");
      if(notice)notice.innerHTML='<b class="warn">'+esc(d.error||"Unable to start speed test")+'</b>';
    }
    await loadSpeedtest();
  }finally{
    setTimeout(loadSpeedtest,1500);
  }
}

document.getElementById("runSpeedtestBtn")?.addEventListener("click",runSpeedtestNow);
document.getElementById("loadSpeedtestServersBtn")?.addEventListener("click",loadSpeedtestServers);
document.getElementById("speedtestPreferredServer")?.addEventListener("change",async e=>{
  await fetch("/api/speedtest/settings",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({preferredServerId:e.target.value})
  });
  await loadSpeedtest();
});
document.getElementById("speedtestAutoToggle")?.addEventListener("change",async e=>{
  await fetch("/api/speedtest/settings",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({enabled:e.target.checked})
  });
  await loadSpeedtest();
});
document.getElementById("speedtestInterval")?.addEventListener("change",async e=>{
  await fetch("/api/speedtest/settings",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({intervalHours:Number(e.target.value)})
  });
  await loadSpeedtest();
});

setInterval(()=>{
  if(document.querySelector("#speedtest.page.active"))loadSpeedtest();
},10000);


let rfEnvironmentData=null;

function rfPct(v){
  return v==null?"—":Number(v).toFixed(1)+"%";
}
function rfDbm(v){
  return v==null?"—":Number(v).toFixed(0)+" dBm";
}
function rfNeighborSummary(neighbors,rssiTrusted=false){
  const dedup=new Map();
  for(const n of neighbors||[]){
    const band=n.band==null?"?":String(n.band);
    const channel=n.channel==null?"?":String(n.channel);
    const identity=(n.bssid||((n.ssid||"unknown")+"@"+channel+"@"+band)).toLowerCase();
    const key=band+"|"+channel+"|"+identity;
    const existing=dedup.get(key);
    const rssi=Number.isFinite(Number(n.rssi))?Number(n.rssi):null;
    if(!existing || (rssi!=null && (existing.rssi==null || rssi>existing.rssi))){
      dedup.set(key,{...n,rssi});
    }
  }

  const groups=new Map();
  for(const n of dedup.values()){
    const band=n.band==null?"?":String(n.band);
    const channel=n.channel==null?"?":String(n.channel);
    const key=band+"|"+channel;
    if(!groups.has(key))groups.set(key,{band,channel,count:0,strongest:null,strongestSsid:null,strongestNormalized:false});
    const g=groups.get(key);
    g.count++;
    if(n.rssi!=null && (g.strongest==null || n.rssi>g.strongest)){
      g.strongest=n.rssi;
      g.strongestSsid=n.ssid||"Hidden / unknown";
      g.strongestNormalized=!!n.rssiNormalizedPositiveMagnitude;
    }
  }

  const classify=g=>{
    if(g.count>=15)return {label:"HIGH",cls:"high"};
    if(g.count>=8)return {label:"MODERATE",cls:"moderate"};
    if(rssiTrusted&&g.strongest!=null&&g.strongest>=-65)return {label:"HIGH",cls:"high"};
    if(rssiTrusted&&g.strongest!=null&&g.strongest>=-75)return {label:"MODERATE",cls:"moderate"};
    return {label:"LOW",cls:"low"};
  };

  const rows=[...groups.values()].sort((a,b)=>{
    const bandOrder=v=>v==="2.4"?0:v==="5"?1:v==="6"?2:9;
    return bandOrder(a.band)-bandOrder(b.band) || Number(a.channel||999)-Number(b.channel||999);
  });
  return {rows,uniqueCount:dedup.size,classify,rssiTrusted};
}

function renderRfEnvironment(d){
  rfEnvironmentData=d;
  const rows=(d.liveRadios&&d.liveRadios.length?d.liveRadios:d.latest)||[];
  const neighbors=d.neighbors||[];
  const neighborRssiTrusted=!!d.neighborRssiValidated;
  const neighborSummary=rfNeighborSummary(neighbors,neighborRssiTrusted);
  const historical=d.historical||[];
  const set=(id,val)=>{const el=document.getElementById(id);if(el)el.textContent=val};

  set("rfRadioCount",rows.length);
  set("rfNeighborCount",neighborSummary.uniqueCount);
  const utilRows=rows.filter(x=>x.channelUtilizationPct!=null||x.channel_utilization_pct!=null);
  const extRows=rows.filter(x=>x.externalBusyPct!=null||x.external_busy_pct!=null);
  const noiseRows=rows.filter(x=>x.noiseDbm!=null||x.noise_dbm!=null);
  const utilValue=x=>Number(x.channelUtilizationPct??x.channel_utilization_pct);
  const extValue=x=>Number(x.externalBusyPct??x.external_busy_pct);
  const noiseValue=x=>Number(x.noiseDbm??x.noise_dbm);
  const hiUtil=utilRows.length?[...utilRows].sort((a,b)=>utilValue(b)-utilValue(a))[0]:null;
  const hiExt=extRows.length?[...extRows].sort((a,b)=>extValue(b)-extValue(a))[0]:null;
  const quiet=noiseRows.length?[...noiseRows].sort((a,b)=>noiseValue(a)-noiseValue(b))[0]:null;
  set("rfHighestUtil",hiUtil?rfPct(utilValue(hiUtil)):"—");
  set("rfHighestUtilDetail",hiUtil?(hiUtil.apName||hiUtil.ap_name||"AP")+" · "+(hiUtil.band||"—")+" GHz":"Not exposed");
  set("rfHighestExternal",hiExt?rfPct(extValue(hiExt)):"—");
  set("rfHighestExternalDetail",hiExt?(hiExt.apName||hiExt.ap_name||"AP")+" · "+(hiExt.band||"—")+" GHz":"Not exposed");
  set("rfNoiseFloor",quiet?rfDbm(noiseValue(quiet)):"—");
  set("rfLastSample",d.lastSampleAt?fmtShortDate(d.lastSampleAt):"Learning…");

  const rangeLabels={1:"Last hour",24:"Last 24 hours",168:"Last 7 days",720:"Last 30 days"};
  set("rfHistoricalRangeLabel",(rangeLabels[Number(d.hours)]||("Last "+Number(d.hours||24)+" hours"))+" stored-sample summary");
  set("rfHistoricalSamples",historical.reduce((sum,x)=>sum+Number(x.sampleCount||0),0));
  const histAvg=historical.filter(x=>x.avgUtilizationPct!=null);
  const histP95=historical.filter(x=>x.p95UtilizationPct!=null);
  const highAvg=histAvg.length?[...histAvg].sort((a,b)=>Number(b.avgUtilizationPct)-Number(a.avgUtilizationPct))[0]:null;
  const highP95=histP95.length?[...histP95].sort((a,b)=>Number(b.p95UtilizationPct)-Number(a.p95UtilizationPct))[0]:null;
  set("rfHistoricalAvg",highAvg?rfPct(highAvg.avgUtilizationPct):"—");
  set("rfHistoricalAvgDetail",highAvg?(highAvg.apName||"AP")+" · "+highAvg.band+" GHz":"No stored samples");
  set("rfHistoricalP95",highP95?rfPct(highP95.p95UtilizationPct):"—");
  set("rfHistoricalP95Detail",highP95?(highP95.apName||"AP")+" · "+highP95.band+" GHz":"No stored samples");

  const notice=document.getElementById("rfEnvironmentNotice");
  if(notice){
    if(!d.privateConfigured){
      notice.innerHTML='<b class="warn">Private/classic telemetry is not configured</b><br><span class="muted">RF environment data needs the local read-only classic API connection.</span>';
    }else if(d.lastError&&!rows.length){
      notice.innerHTML='<b class="warn">RF telemetry is not available yet</b><br><span class="muted">'+esc(d.lastError)+'</span>';
    }else{
      const trustNote=neighborRssiTrusted
        ?" Neighbor RSSI semantics are validated for pressure scoring."
        :" Neighbor RSSI is normalized for display when needed but excluded from pressure/channel decisions until the controller field semantics are independently validated.";
      notice.innerHTML='<b class="good">Passive RF monitoring active</b><br><span class="muted">Read-only sample every '+Math.round(Number(d.sampleIntervalSeconds||300)/60)+' minutes. Neighbor observations are shown only when the controller exposes them. No active/off-channel scan is being triggered.'+esc(trustNote)+'</span>';
    }
  }

  const table=document.getElementById("rfRadioTable");
  if(table){
    table.innerHTML=rows.length?rows.map(x=>{
      const name=x.apName||x.ap_name||"—";
      const channel=x.channel??"—";
      const width=x.widthMHz??x.width_mhz;
      const util=x.channelUtilizationPct??x.channel_utilization_pct;
      const selfRx=x.selfRxPct??x.self_rx_pct;
      const selfTx=x.selfTxPct??x.self_tx_pct;
      const external=x.externalBusyPct??x.external_busy_pct;
      const noise=x.noiseDbm??x.noise_dbm;
      const txp=x.txPowerDbm??x.tx_power_dbm;
      const retry=x.txRetriesPct??x.tx_retries_pct;
      const neighbor=x.neighborCount??x.neighbor_count;
      return '<tr>'+
        '<td><b>'+esc(name)+'</b><div class="muted">'+esc(x.radioName||x.radio_name||"")+'</div></td>'+
        '<td>'+esc(x.band)+' GHz</td>'+
        '<td>'+esc(channel)+(width!=null?' / '+esc(width)+' MHz':'')+'</td>'+
        '<td>'+esc(rfPct(util))+'</td>'+
        '<td>'+esc(rfPct(selfRx))+'</td>'+
        '<td>'+esc(rfPct(selfTx))+'</td>'+
        '<td>'+esc(rfPct(external))+'</td>'+
        '<td>'+esc(rfDbm(noise))+'</td>'+
        '<td>'+esc(txp==null?"—":Number(txp).toFixed(0)+" dBm")+'</td>'+
        '<td class="'+retryClass(retry)+'">'+esc(retry==null?"—":Number(retry).toFixed(1)+"%")+'</td>'+
        '<td>'+esc(neighbor??"—")+'</td>'+
      '</tr>';
    }).join(""):'<tr><td colspan="11"><div class="empty">No passive radio statistics have been exposed yet. Use Refresh passive RF and inspect diagnostics.</div></td></tr>';
  }

  const histTable=document.getElementById("rfHistoricalTable");
  if(histTable){
    histTable.innerHTML=historical.length?historical.map(x=>
      '<tr>'+
        '<td><b>'+esc(x.apName||"—")+'</b></td>'+
        '<td>'+esc(x.band==null?"—":x.band+" GHz")+'</td>'+
        '<td>'+esc(x.sampleCount??0)+'</td>'+
        '<td>'+esc(rfPct(x.avgUtilizationPct))+'</td>'+
        '<td>'+esc(rfPct(x.medianUtilizationPct))+'</td>'+
        '<td>'+esc(rfPct(x.p95UtilizationPct))+'</td>'+
        '<td>'+esc(rfPct(x.maxUtilizationPct))+'</td>'+
        '<td>'+esc(rfPct(x.avgExternalBusyPct))+'</td>'+
        '<td class="'+retryClass(x.avgRetriesPct)+'">'+esc(x.avgRetriesPct==null?"—":Number(x.avgRetriesPct).toFixed(1)+"%")+'</td>'+
        '<td>'+esc(x.maxClientCount??"—")+'</td>'+
      '</tr>'
    ).join(""):'<tr><td colspan="10"><div class="empty">No stored RF samples exist in this selected range yet.</div></td></tr>';
  }

  const summaryTable=document.getElementById("rfNeighborChannelSummary");
  if(summaryTable){
    summaryTable.innerHTML=neighborSummary.rows.length?neighborSummary.rows.map(g=>{
      const pressure=neighborSummary.classify(g);
      const strongest=g.strongest==null?"—":rfDbm(g.strongest)+" · "+(g.strongestSsid||"")+(g.strongestNormalized?" · normalized sign":"");
      return '<tr>'+
        '<td>'+esc(g.band==="?"?"Unknown":g.band+" GHz")+'</td>'+
        '<td><b>'+esc(g.channel)+'</b></td>'+
        '<td>'+esc(g.count)+'</td>'+
        '<td>'+esc(strongest)+'</td>'+
        '<td><span class="rf-pressure '+pressure.cls+'"><span class="rf-pressure-dot"></span>'+pressure.label+'</span><div class="muted">'+(neighborRssiTrusted?"count + RSSI":"count only")+'</div></td>'+
      '</tr>';
    }).join(""):'<tr><td colspan="5"><div class="empty">No neighboring BSS observations are available yet.</div></td></tr>';
  }

  const rawCount=document.getElementById("rfNeighborRawCount");
  if(rawCount)rawCount.textContent="("+neighborSummary.uniqueCount+" unique / "+neighbors.length+" observations)";

  const nt=document.getElementById("rfNeighborTable");
  if(nt){
    const sorted=[...neighbors].sort((a,b)=>Number(b.rssi??-999)-Number(a.rssi??-999));
    nt.innerHTML=sorted.length?sorted.slice(0,250).map(x=>
      '<tr><td><b>'+esc(x.ssid||"Hidden / unknown")+'</b></td><td class="client-ip">'+esc(x.bssid||"—")+'</td><td>'+esc(x.band==null?"—":x.band+" GHz")+'</td><td>'+esc(x.channel??"—")+'</td><td>'+esc(rfDbm(x.rssi))+'</td><td>'+esc(rfDbm(x.noiseDbm))+'</td><td>'+esc(x.sourceApMac||"Site-wide")+'</td></tr>'
    ).join(""):'<tr><td colspan="7"><div class="empty">The controller did not return neighboring BSS observations from the read-only classic endpoint.</div></td></tr>';
  }

  const diag=document.getElementById("rfDiagnostics");
  if(diag){
    const ds=d.diagnostics||[];
    const quality=d.dataQuality||{};
    const discovered=ds.length?ds.map(x=>
      '<div><span>'+esc(x.apName||"AP")+'</span><b class="diagnostic-keys">radio stats: '+esc((x.radioStatKeys||[]).join(", ")||"none")+' · config: '+esc((x.radioConfigKeys||[]).join(", ")||"none")+'</b></div>'
    ).join(""):'<div><span>RF field discovery</span><b>No AP diagnostic structure returned yet.</b></div>';
    const qualityRows=
      '<div><span>Neighbor RSSI decision use</span><b>'+(neighborRssiTrusted?"Validated / enabled":"Validation pending · excluded from decisions")+'</b></div>'+
      '<div><span>Positive RSSI magnitudes normalized</span><b>'+esc(quality.neighborRssiPositiveMagnitudeNormalized??0)+'</b></div>'+
      '<div><span>Missing / invalid neighbor RSSI</span><b>'+esc(quality.neighborRssiMissingOrInvalid??0)+'</b></div>';
    diag.innerHTML=discovered+qualityRows;
  }
}

async function loadRfEnvironment(){
  const hours=Number(document.getElementById("rfEnvironmentRange")?.value||24);
  try{
    const r=await fetch("/api/rf-environment?hours="+encodeURIComponent(hours),{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Unable to load RF environment");
    renderRfEnvironment(d);
  }catch(e){
    const notice=document.getElementById("rfEnvironmentNotice");
    if(notice)notice.innerHTML='<b class="warn">Unable to load RF environment</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }
}

async function sampleRfEnvironmentNow(){
  const btn=document.getElementById("rfSampleNowBtn");
  if(btn){btn.disabled=true;btn.textContent="Refreshing…";}
  try{
    const r=await fetch("/api/rf-environment/sample",{method:"POST"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"Passive RF sample failed");
    await loadRfEnvironment();
  }catch(e){
    const notice=document.getElementById("rfEnvironmentNotice");
    if(notice)notice.innerHTML='<b class="warn">Passive RF refresh failed</b><br><span class="muted">'+esc(e.message||e)+'</span>';
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Refresh passive RF";}
  }
}

document.getElementById("rfEnvironmentRange")?.addEventListener("change",loadRfEnvironment);
document.getElementById("rfSampleNowBtn")?.addEventListener("click",sampleRfEnvironmentNow);
setInterval(()=>{
  if(document.querySelector("#rfenvironment.page.active"))loadRfEnvironment();
},60000);


function renderChannelPlan(plan){
  if(!plan)return;
  window.channelPlanData=plan;
  const items=plan.items||[];
  const conflicts=plan.conflicts||[];
  const keep=items.filter(x=>x.status==="KEEP").length;
  const change=items.filter(x=>x.status==="CONSIDER_CHANGE").length;
  const summary=document.getElementById("channelSummaryCards");
  if(summary){
    summary.innerHTML=
      '<div class="summary-card"><h3>Radios analyzed</h3><div class="big">'+items.length+'</div></div>'+
      '<div class="summary-card"><h3>Keep</h3><div class="big good">'+keep+'</div></div>'+
      '<div class="summary-card"><h3>Consider change</h3><div class="big '+(change?"warn":"good")+'">'+change+'</div></div>'+
      '<div class="summary-card"><h3>Own-AP conflicts</h3><div class="big '+(conflicts.length?"warn":"good")+'">'+conflicts.length+'</div></div>';
  }

  const box=document.getElementById("channelPlanCards");
  if(box){
    box.innerHTML="";
    items.forEach(x=>{
      const retry=x.retryPct==null?"—":x.retryPct.toFixed(1)+"%";
      const actions=(x.actions||[]).map(a=>'<li>'+esc(a)+'</li>').join("");
      const rec=(x.recommendedChannel==null?"—":x.recommendedChannel)+" / "+(x.recommendedWidthMHz==null?"—":x.recommendedWidthMHz+" MHz");
      const current=(x.channel==null?"—":x.channel)+" / "+(x.widthMHz==null?"—":x.widthMHz+" MHz");
      const rfEvidence=[
        x.rfUtilizationPct!=null?"Util "+Number(x.rfUtilizationPct).toFixed(1)+"%":null,
        x.rfExternalBusyPct!=null?"External "+Number(x.rfExternalBusyPct).toFixed(1)+"%":null,
        x.rfNoiseDbm!=null?"Noise "+Number(x.rfNoiseDbm).toFixed(0)+" dBm":null,
        x.rfNeighborCount!=null?"Neighbors "+x.rfNeighborCount:null
      ].filter(Boolean);
      box.insertAdjacentHTML("beforeend",
        '<div class="channel-card">'+
          '<div class="channel-head"><div><h3>'+esc(x.apName)+'</h3><span class="muted">'+esc(x.band)+' GHz · '+esc(x.model)+'</span></div>'+
          '<span class="status-tag '+(x.status==="KEEP"?"ALREADY_OPTIMIZED":x.status==="INVESTIGATE"?"PROTECTED":"NEEDS_ATTENTION")+'">'+esc(x.status)+'</span></div>'+
          '<div class="channel-metrics">'+
            '<div><span>Current</span><b>'+esc(current)+'</b></div>'+
            '<div><span>Recommended</span><b>'+esc(rec)+'</b></div>'+
            '<div><span>Block</span><b>'+esc(x.channelBlock||"—")+'</b></div>'+
            '<div><span>Retries</span><b class="'+retryClass(x.retryPct)+'">'+esc(retry)+'</b><small>'+esc(x.retryBasis||"")+'</small></div>'+
          '</div>'+
          (rfEvidence.length?'<div class="channel-rf-evidence"><span>Passive RF</span><b>'+esc(rfEvidence.join(" · "))+'</b></div>':'')+
          '<ul class="channel-actions">'+actions+'</ul>'+
          (x.testableChange
            ?'<div class="channel-test-action"><button class="start-test-btn" data-test-index="'+items.indexOf(x)+'">Create '+esc(x.band)+' GHz A/B/A test</button></div>'
            :'<div class="channel-test-action">'+
               (x.status==="INVESTIGATE"?'<span class="muted">Monitoring only — no new channel/width change is proposed.</span> ':'')+
               '<button class="secondary recover-test-btn" data-test-index="'+items.indexOf(x)+'">Recover applied change</button>'+
             '</div>')+
        '</div>');
    });
  }

  const coordinated=document.getElementById("coordinatedRfPlan");
  if(coordinated){
    const byAp={};
    items.forEach(x=>{
      if(!byAp[x.apId])byAp[x.apId]={name:x.apName,model:x.model,bands:{}};
      byAp[x.apId].bands[String(x.band)]=x;
    });
    let rows="";
    Object.values(byAp).forEach(ap=>{
      const fmtBand=(band)=>{
        const x=ap.bands[String(band)];
        if(!x)return "—";
        const useRecommended=x.status==="CONSIDER_CHANGE";
        const ch=useRecommended && x.recommendedChannel!=null?x.recommendedChannel:x.channel;
        const w=useRecommended && x.recommendedWidthMHz!=null?x.recommendedWidthMHz:x.widthMHz;
        return (ch==null?"—":ch)+" / "+(w==null?"—":w+" MHz");
      };
      rows+='<tr><td><b>'+esc(ap.name)+'</b><div class="muted">'+esc(ap.model)+'</div></td><td>'+esc(fmtBand(2.4))+'</td><td>'+esc(fmtBand(5))+'</td><td>'+esc(fmtBand(6))+'</td></tr>';
    });
    coordinated.innerHTML='<table><thead><tr><th>Access point</th><th>2.4 GHz target</th><th>5 GHz target</th><th>6 GHz target</th></tr></thead><tbody>'+rows+'</tbody></table>';
  }

  const cb=document.getElementById("channelConflicts");
  if(cb){
    cb.innerHTML=conflicts.length?conflicts.map(x=>
      '<div class="recommendation MEDIUM"><div class="rec-top"><span class="badge">'+esc(x.band)+' GHz</span><b>'+esc((x.aps||[]).join(" ↔ "))+'</b></div><div class="rec-message">'+esc(x.detail)+'</div></div>'
    ).join(""):'<div class="empty">No channel-block conflicts detected between your own APs.</div>';
  }

  const notes=document.getElementById("channelNotes");
  if(notes){
    notes.innerHTML=(plan.notes||[]).map(x=>'<div>• '+esc(x)+'</div>').join("");
  }
}
async function loadChannelPlan(){
  const r=await fetch("/api/channel-plan",{cache:"no-store"});
  const d=await r.json();
  if(d.ok)renderChannelPlan(d);
}


async function startOptimizationTest(index){
  const plan=window.channelPlanData||{};
  const x=(plan.items||[])[index];
  if(!x)return;
  const actualChange=(x.recommendedChannel!==x.channel || x.recommendedWidthMHz!==x.widthMHz);
  if(!x.testableChange || !actualChange){
    alert("No channel or width change is proposed for this radio. This item should be monitored/investigated instead of A/B/A tested.");
    return;
  }
  const body={
    apId:x.apId,
    apName:x.apName,
    band:x.band,
    proposedChannel:x.recommendedChannel,
    proposedWidthMHz:x.recommendedWidthMHz,
    description:(x.actions||[]).join("; ")
  };
  const r=await fetch("/api/optimization-tests",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)
  });
  const d=await r.json();
  if(d.ok){
    await loadOptimizationTests();
  }else{
    alert(d.error||"Unable to create RF test.");
  }
}

async function recoverOptimizationTest(index){
  const plan=window.channelPlanData||{};
  const x=(plan.items||[])[index];
  if(!x)return;

  const baseBody={apId:x.apId,apName:x.apName,band:x.band};
  let r=await fetch("/api/optimization-tests/recover",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(baseBody)
  });
  let d=await r.json();

  if(!d.ok && d.needsManual){
    const prevChannel=prompt("Previous "+x.band+" GHz channel before the change:");
    if(prevChannel===null)return;
    const prevWidth=prompt("Previous "+x.band+" GHz channel width in MHz:");
    if(prevWidth===null)return;
    const minutesAgo=prompt("About how many minutes ago did you apply the change?","15");
    if(minutesAgo===null)return;

    r=await fetch("/api/optimization-tests/recover",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        ...baseBody,
        originalChannel:Number(prevChannel),
        originalWidthMHz:Number(prevWidth),
        minutesAgo:Number(minutesAgo)
      })
    });
    d=await r.json();
  }

  if(d.ok){
    await loadOptimizationTests();
    alert("Recovered "+x.band+" GHz change and started A/B/A monitoring.");
  }else{
    alert(d.error||"Unable to recover the applied RF change.");
  }
}

document.addEventListener("click",e=>{
  const b=e.target.closest(".start-test-btn");
  if(b){
    startOptimizationTest(Number(b.dataset.testIndex));
    return;
  }
  const recover=e.target.closest(".recover-test-btn");
  if(recover)recoverOptimizationTest(Number(recover.dataset.testIndex));
});

function testStatusClass(status){
  if(["IMPROVED","IMPROVED_CONFIRMED","IMPROVED_TOPOLOGY"].includes(status))return "ALREADY_OPTIMIZED";
  if(["WORSE","WORSE_CONFIRMED","WORSE_TOPOLOGY"].includes(status))return "FAILED";
  if(["MONITORING","ROLLBACK_MONITORING","ROLLBACK_REQUIRED"].includes(status))return "PROTECTED";
  if(["NO_CHANGE","NO_MEANINGFUL_CHANGE","INCONCLUSIVE","INCONCLUSIVE_LOAD_CHANGED","INCONCLUSIVE_ENVIRONMENT_CHANGED","INVALID_NO_CHANGE"].includes(status))return "NEEDS_ATTENTION";
  if(status==="CANCELLED")return "SKIPPED";
  return "PROTECTED";
}
function fmtRetry(v){return v==null?"—":Number(v).toFixed(1)+"%"}
function fmtClients(v){return v==null?"—":Number(v).toFixed(1)}

function phaseTiming(t){
  if(t.status==="PROPOSED"){
    return {label:"Waiting for new setting",detail:"Auto-detect enabled",pct:0};
  }
  if(t.status==="MONITORING" && t.applied_at){
    const elapsed=Math.max(0,(Date.now()-new Date(t.applied_at).getTime())/60000);
    if(elapsed<15){
      return {label:"Settling after new setting",detail:Math.floor(elapsed)+"m elapsed · "+Math.ceil(15-elapsed)+"m settling remaining",pct:(elapsed/75)*100};
    }
    return {label:"Observing new setting",detail:Math.floor(elapsed)+"m elapsed · "+Math.max(0,Math.ceil(75-elapsed))+"m until rollback decision",pct:(elapsed/75)*100};
  }
  if(t.status==="ROLLBACK_REQUIRED"){
    return {label:"Rollback verification required",detail:"Restore the original radio settings; detection is automatic.",pct:100};
  }
  if(t.status==="ROLLBACK_MONITORING" && t.rollback_started_at){
    const elapsed=Math.max(0,(Date.now()-new Date(t.rollback_started_at).getTime())/60000);
    if(elapsed<15){
      return {label:"Settling after rollback",detail:Math.floor(elapsed)+"m elapsed · "+Math.ceil(15-elapsed)+"m settling remaining",pct:(elapsed/75)*100};
    }
    return {label:"Verifying original setting",detail:Math.floor(elapsed)+"m elapsed · "+Math.max(0,Math.ceil(75-elapsed))+"m until final A/B/A result",pct:(elapsed/75)*100};
  }
  return null;
}

function renderOptimizationTests(items){
  const box=document.getElementById("optimizationTests");
  if(!box)return;
  if(!items.length){
    box.innerHTML='<div class="empty">No optimization tests yet. Create one from a CONSIDER_CHANGE recommendation before changing the AP in UniFi.</div>';
    return;
  }
  box.innerHTML="";
  items.forEach(t=>{
    const proposed=(t.proposed_channel==null?"—":t.proposed_channel)+" / "+(t.proposed_width_mhz==null?"—":t.proposed_width_mhz+" MHz");
    const original=(t.original_channel==null?"—":t.original_channel)+" / "+(t.original_width_mhz==null?"—":t.original_width_mhz+" MHz");
    const baseline60=t.baseline_retry_60!=null?t.baseline_retry_60:t.baseline_retry;
    let controls="";
    let timing="";
    const pt=phaseTiming(t);

    if(t.status==="PROPOSED"){
      controls='<button class="mark-applied-btn" data-id="'+t.id+'">I made this change</button> <button class="secondary cancel-test-btn" data-id="'+t.id+'">Cancel</button>';
    }else if(t.status==="MONITORING"){
      controls='<span class="muted">A/B/A monitoring is automatic.</span> <button class="secondary cancel-test-btn" data-id="'+t.id+'">Cancel test</button>';
    }else if(t.status==="ROLLBACK_REQUIRED"){
      controls='<span class="muted">Restore original '+esc(original)+'. The optimizer will detect it automatically.</span> <button class="secondary cancel-test-btn" data-id="'+t.id+'">Cancel test</button>';
    }else if(t.status==="ROLLBACK_MONITORING"){
      controls='<span class="muted">Rollback verification is running automatically.</span> <button class="secondary cancel-test-btn" data-id="'+t.id+'">Cancel test</button>';
    }else if(t.status==="CANCELLED"){
      controls='<button class="retest-cancelled-btn" data-id="'+t.id+'">Retest cancelled change</button> <span class="muted">Creates a fresh baseline and a new A/B/A test using the same proposed B setting.</span>';
    }

    if(pt){
      timing='<div class="test-timing"><span>'+esc(pt.label)+'</span><b>'+esc(pt.detail)+'</b><div class="progress-track"><div class="progress-fill" style="width:'+Math.min(100,Math.max(0,pt.pct))+'%"></div></div></div>';
    }else if(t.completed_at){
      timing='<div class="test-timing"><span>Completed '+esc(fmtDateTime(t.completed_at))+'</span><b>'+esc(t.result||t.status)+'</b></div>';
    }

    const postDelta=(baseline60!=null&&t.post_retry_avg!=null)?Number(t.post_retry_avg)-Number(baseline60):null;
    const rollbackDelta=(baseline60!=null&&t.rollback_retry_avg!=null)?Number(t.rollback_retry_avg)-Number(baseline60):null;
    const topo=t.topology||null;
    const topologyHtml=topo
      ? '<div class="topology-result">'+
          '<span>Own-AP conflicts</span>'+
          '<b>'+esc(topo.originalTargetConflicts)+' → '+esc(topo.proposedTargetConflicts)+'</b>'+
          '<small>'+(topo.proposedTargetConflicts<topo.originalTargetConflicts?'B removes overlap':topo.proposedTargetConflicts>topo.originalTargetConflicts?'B adds overlap':'No topology change')+'</small>'+
        '</div>'
      : '';

    box.insertAdjacentHTML("beforeend",
      '<div class="test-card">'+
        '<div class="channel-head"><div><h3>'+esc(t.ap_name)+'</h3><span class="muted">'+esc(t.band)+' GHz A/B/A RF test</span></div>'+
        '<span class="status-tag '+testStatusClass(t.status)+'">'+esc(t.status)+'</span></div>'+
        '<div class="aba-strip">'+
          '<div><span>A · Original</span><b>'+esc(original)+'</b><small>'+esc(fmtRetry(baseline60))+' · '+esc(fmtClients(t.baseline_client_count))+' clients</small></div>'+
          '<div><span>B · New</span><b>'+esc(proposed)+'</b><small>'+esc(fmtRetry(t.post_retry_avg))+(postDelta==null?"":" · "+(postDelta>0?"+":"")+postDelta.toFixed(1)+" pts")+'</small></div>'+
          '<div><span>A · Rollback</span><b>'+esc(original)+'</b><small>'+esc(fmtRetry(t.rollback_retry_avg))+(rollbackDelta==null?"":" · "+(rollbackDelta>0?"+":"")+rollbackDelta.toFixed(1)+" pts")+'</small></div>'+
        '</div>'+
        '<div class="channel-metrics">'+
          '<div><span>Baseline samples</span><b>'+esc(t.baseline_sample_count??"—")+'</b></div>'+
          '<div><span>New-setting samples</span><b>'+esc(t.post_sample_count??"—")+'</b></div>'+
          '<div><span>Rollback samples</span><b>'+esc(t.rollback_sample_count??"—")+'</b></div>'+
          '<div><span>Preliminary</span><b>'+esc(t.preliminary_result||"—")+'</b></div>'+
        '</div>'+
        topologyHtml+
        '<div class="test-description">'+esc(t.description||"")+'</div>'+
        timing+
        '<div class="test-controls">'+controls+'</div>'+
      '</div>');
  });
}

async function retestCancelledOptimizationTest(testId){
  const btn=document.querySelector('.retest-cancelled-btn[data-id="'+testId+'"]');
  if(btn){btn.disabled=true;btn.textContent="Creating retest…";}
  try{
    const r=await fetch("/api/optimization-tests/"+testId+"/retest",{method:"POST"});
    const d=await r.json();
    if(!d.ok){
      let message=d.error||"Unable to create retest.";
      if(d.needsRestore&&d.original){
        message+="\n\nRestore the radio to "+d.original.channel+" / "+d.original.widthMHz+" MHz first, allow a fresh baseline to collect, then retest.";
      }
      alert(message);
      return;
    }
    await loadOptimizationTests();
    await loadChannelPlan();
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Retest cancelled change";}
  }
}

async function loadOptimizationTests(){
  const r=await fetch("/api/optimization-tests",{cache:"no-store"});
  const d=await r.json();
  if(d.ok)renderOptimizationTests(d.items||[]);
}

document.addEventListener("click",async e=>{
  const apply=e.target.closest(".mark-applied-btn");
  if(apply){
    await fetch("/api/optimization-tests/"+apply.dataset.id+"/mark-applied",{method:"POST"});
    await loadOptimizationTests();
    return;
  }
  const cancel=e.target.closest(".cancel-test-btn");
  if(cancel){
    if(!confirm("Cancel this RF test? The collected history will remain, but the test will stop monitoring."))return;
    await fetch("/api/optimization-tests/"+cancel.dataset.id+"/cancel",{method:"POST"});
    await loadOptimizationTests();
    await loadChannelPlan();
    return;
  }
  const retest=e.target.closest(".retest-cancelled-btn");
  if(retest){
    await retestCancelledOptimizationTest(Number(retest.dataset.id));
  }
});

setInterval(()=>{
  if(document.querySelector("#channels.page.active") && report){
    renderOptimizationTests(report.optimizationTests||[]);
  }
},30000);


function notificationsEnabled(){
  return localStorage.getItem("uho.notifications")==="1" && "Notification" in window && Notification.permission==="granted";
}
function maybeNotify(title,body){
  if(!notificationsEnabled())return;
  try{new Notification(title,{body,icon:"/static/icon.svg"})}catch{}
}
function processAlerts(d){
  const inet=d.internet?.latest;
  if(inet){
    const online=!!inet.online;
    if(previousAlertState.internet!==null && previousAlertState.internet!==online){
      maybeNotify(online?"Internet restored":"Internet outage detected",online?"Connectivity probe is responding again.":"The optimizer cannot reach the Internet from Unraid.");
    }
    previousAlertState.internet=online;
  }

  const nowOffline=new Set((d.accessPoints||[]).filter(x=>x.state!=="ONLINE").map(x=>x.id));
  for(const ap of (d.accessPoints||[])){
    if(ap.state!=="ONLINE" && !previousAlertState.offlineAps.has(ap.id)){
      maybeNotify("Access point offline",ap.name+" is not reporting ONLINE.");
    }
  }
  previousAlertState.offlineAps=nowOffline;

  for(const t of (d.optimizationTests||[])){
    const old=previousAlertState.testResults.get(t.id);
    const cur=t.result||t.status;
    if(old && old!==cur && ["IMPROVED_CONFIRMED","IMPROVED_TOPOLOGY","WORSE_CONFIRMED","WORSE_TOPOLOGY","NO_MEANINGFUL_CHANGE","INCONCLUSIVE","INCONCLUSIVE_LOAD_CHANGED","INCONCLUSIVE_ENVIRONMENT_CHANGED"].includes(cur)){
      maybeNotify("Wi-Fi optimization test complete",t.ap_name+" "+t.band+" GHz: "+cur);
    }
    previousAlertState.testResults.set(t.id,cur);
  }
}

async function loadSystem(){
  const r=await fetch("/api/system",{cache:"no-store"});
  const d=await r.json();
  if(!d.ok)return;
  const set=(id,val,cls)=>{
    const el=document.getElementById(id);
    if(!el)return;
    el.textContent=val;
    if(cls)el.className="big "+cls;
  };
  set("sysVersion","v"+d.version,"");
  set("sysMonitor",d.monitorStarted?"RUNNING":"STOPPED",d.monitorStarted?"good":"bad");
  document.getElementById("sysMonitorDetail").textContent=d.lastMonitorError?"Last error: "+d.lastMonitorError:"Background monitor active";
  set("sysController",d.lastControllerSuccess?"CONNECTED":"WAITING",d.lastControllerSuccess?"good":"warn");
  document.getElementById("sysControllerDetail").textContent=d.controller||"—";
  set("sysDbSize",bytes(d.database?.sizeBytes),"");
  const counts=d.database?.rowCounts||{};
  document.getElementById("sysDbRows").textContent=Object.entries(counts).map(([k,v])=>k+": "+(v??"—")).join(" · ");
  document.getElementById("sysPoll").textContent=(d.pollIntervalSeconds??"—")+" seconds";
  document.getElementById("sysRetention").textContent=(d.retentionDays??"—")+" days";
  document.getElementById("sysLastController").textContent=fmtDateTime(d.lastControllerSuccess);
  document.getElementById("sysLastCycle").textContent=fmtDateTime(d.lastMonitorCycle);
  document.getElementById("sysLastError").textContent=d.lastMonitorError||"None";
  const pr=d.privateRf||{};
  const prStatus=document.getElementById("privateRfStatus");
  const prDetail=document.getElementById("privateRfDetail");
  const prCreds=document.getElementById("privateRfCreds");
  const prToggle=document.getElementById("privateRfAutoToggle");
  if(prStatus)prStatus.textContent=pr.status||"—";
  if(prDetail)prDetail.textContent=pr.detail||"—";
  if(prCreds)prCreds.textContent=pr.configured?"Configured in Unraid environment":"Missing UNIFI_PRIVATE_USERNAME / UNIFI_PRIVATE_PASSWORD";
  if(prToggle){
    prToggle.checked=!!pr.autoEnabled;
    prToggle.disabled=!pr.writeVerified;
    prToggle.title=pr.writeVerified?"":"Validate the private RF write path first";
  }
  updateNotificationButton();
}

function showPrivateRfResult(message,good=false){
  const box=document.getElementById("privateRfResult");
  if(!box)return;
  box.style.display="block";
  box.innerHTML='<b class="'+(good?"good":"warn")+'">'+esc(message)+'</b>';
}

async function runPrivateRfDiscovery(){
  const btn=document.getElementById("privateRfDiscoverBtn");
  if(btn){btn.disabled=true;btn.textContent="Discovering…";}
  try{
    const r=await fetch("/api/private-rf/discover",{method:"POST"});
    const d=await r.json();
    if(!d.ok){
      showPrivateRfResult(d.error||"Private RF discovery failed.");
      return;
    }
    const select=document.getElementById("privateRfApSelect");
    const verify=document.getElementById("privateRfVerifyBtn");
    if(select){
      select.innerHTML='<option value="">Select an AP for no-op validation</option>'+
        (d.accessPoints||[]).map(ap=>
          '<option value="'+esc(ap.id)+'">'+esc(ap.name)+' · '+esc(ap.model||"AP")+'</option>'
        ).join("");
    }
    if(verify)verify.disabled=false;
    showPrivateRfResult("Read-only discovery succeeded: "+(d.accessPoints||[]).length+" access points exposed radio_table.",true);
    await loadSystem();
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Run read-only discovery";}
  }
}

async function verifyPrivateRfWrite(){
  const select=document.getElementById("privateRfApSelect");
  const classicId=select?.value;
  if(!classicId){
    showPrivateRfResult("Select an AP first.");
    return;
  }
  if(!confirm("Validate the private RF write path on this AP? The payload uses the AP's existing radio settings, but UniFi may briefly reprovision the access point."))return;
  const btn=document.getElementById("privateRfVerifyBtn");
  if(btn){btn.disabled=true;btn.textContent="Validating…";}
  try{
    const r=await fetch("/api/private-rf/verify-write",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({classicId})
    });
    const d=await r.json();
    if(d.ok){
      showPrivateRfResult("Private RF write path validated. Auto RF can now be enabled.",true);
    }else{
      showPrivateRfResult("Write validation failed: "+(d.error||"unknown error"));
    }
    await loadSystem();
  }finally{
    if(btn){btn.disabled=false;btn.textContent="Validate no-op write";}
  }
}

async function togglePrivateRfAuto(enabled){
  const r=await fetch("/api/private-rf/auto",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({enabled})
  });
  const d=await r.json();
  if(!d.ok){
    showPrivateRfResult(d.error||"Unable to change Auto RF state.");
  }else{
    showPrivateRfResult(enabled?"Experimental Auto RF enabled.":"Experimental Auto RF disabled.",true);
  }
  await loadSystem();
}

function updateNotificationButton(){
  const btn=document.getElementById("notificationBtn");
  if(!btn)return;
  if(!("Notification" in window)){
    btn.textContent="Notifications unavailable";
    btn.disabled=true;
    return;
  }
  const enabled=notificationsEnabled();
  btn.textContent=enabled?"Browser alerts enabled":"Enable browser alerts";
  btn.className=enabled?"":"secondary";
}

document.addEventListener("click",async e=>{
  if(e.target.id!=="notificationBtn")return;
  if(!("Notification" in window))return;
  const permission=await Notification.requestPermission();
  if(permission==="granted"){
    localStorage.setItem("uho.notifications","1");
    maybeNotify("UniFi Home Optimizer","Browser alerts are now enabled.");
  }else{
    localStorage.setItem("uho.notifications","0");
  }
  updateNotificationButton();
});


document.addEventListener("click",async e=>{
  if(e.target.id==="privateRfDiscoverBtn"){
    await runPrivateRfDiscovery();
    return;
  }
  if(e.target.id==="privateRfVerifyBtn"){
    await verifyPrivateRfWrite();
    return;
  }
});

document.addEventListener("change",async e=>{
  if(e.target.id==="privateRfAutoToggle"){
    await togglePrivateRfAuto(!!e.target.checked);
  }
});
