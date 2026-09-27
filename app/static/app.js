let report=null;

document.querySelectorAll(".nav").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".nav").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".page").forEach(x=>x.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.page).classList.add("active");
    if(btn.dataset.page==="history") loadHistory();
    if(btn.dataset.page==="roaming") loadRoaming();
    if(btn.dataset.page==="internet") loadInternet();
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

async function loadReport(){
  try{
    const r=await fetch("/api/report",{cache:"no-store"});
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"API error");
    report=d;
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
    renderOverview();renderAPs();renderBroadcasts();renderClients();renderSwitches();renderRoamingSummary(d.roaming||[]);renderInternet(d.internet,d.gateway);
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
  const apBox=document.getElementById("overviewApCards");apBox.innerHTML="";
  report.accessPoints.forEach(ap=>{
    const r=maxRetry(ap);
    const cls=retryClass(r);
    apBox.insertAdjacentHTML("beforeend",`<div class="summary-card"><h3>${esc(ap.name)}</h3><div class="muted">${esc(ap.clientCount)} clients · ${esc(ap.state)}</div><div class="big ${cls}">${r==null?"—":r.toFixed(1)+"%"}</div><div class="muted">highest TX retry · ${esc(retryBasis(ap))}</div></div>`);
  });
  const wifiBox=document.getElementById("overviewWifiCards");wifiBox.innerHTML="";
  report.wifiBroadcasts.forEach(w=>{
    const st=w.optimizerStatus||{};
    wifiBox.insertAdjacentHTML("beforeend",`<div class="summary-card"><h3>${esc(w.name)}</h3><div class="muted">${esc(w.type)}</div><div class="status-row"><span>${esc(st.detail)}</span><span class="status-tag ${esc(st.status)}">${esc(st.status)}</span></div></div>`);
  });
  renderFindingList("wifiFindings",report.analysis.wifiFindings||[],"No current Wi-Fi findings.");
  renderFindingList("wiredFindings",report.analysis.wiredFindings||[],"No wired observations.");
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

function renderClients(){
  const q=(document.getElementById("clientSearch")?.value||"").toLowerCase();
  const t=document.getElementById("clientTable");t.innerHTML="";
  report.clients.filter(c=>[c.name,c.ipAddress,c.type,c.uplinkDeviceName,c.uplinkDeviceModel].some(v=>String(v||"").toLowerCase().includes(q)))
  .forEach(c=>t.insertAdjacentHTML("beforeend",`<tr><td>${esc(c.name)}</td><td>${esc(c.ipAddress)}</td><td>${esc(c.type)}</td><td>${esc(c.uplinkDeviceName)}</td><td>${esc(c.uplinkDeviceModel)}</td></tr>`));
}
document.getElementById("clientSearch").addEventListener("input",()=>report&&renderClients());

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
