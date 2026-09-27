let previousAlertState={internet:null,offlineAps:new Set(),testResults:new Map()};
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
    if(btn.dataset.page==="channels") loadChannelPlan();
    if(btn.dataset.page==="system") loadSystem();
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
  const units=["B","KB","MB","GB"];let n=Number(v),i=0;
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
    renderOverview();renderAPs();renderBroadcasts();renderClients();renderSwitches();renderRoamingSummary(d.roaming||[]);renderInternet(d.internet,d.gateway);renderChannelPlan(d.channelPlan);renderOptimizationTests(d.optimizationTests||[]);
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
      box.insertAdjacentHTML("beforeend",
        '<div class="channel-card">'+
          '<div class="channel-head"><div><h3>'+esc(x.apName)+'</h3><span class="muted">'+esc(x.band)+' GHz · '+esc(x.model)+'</span></div>'+
          '<span class="status-tag '+(x.status==="KEEP"?"ALREADY_OPTIMIZED":"NEEDS_ATTENTION")+'">'+esc(x.status)+'</span></div>'+
          '<div class="channel-metrics">'+
            '<div><span>Current</span><b>'+esc(current)+'</b></div>'+
            '<div><span>Recommended</span><b>'+esc(rec)+'</b></div>'+
            '<div><span>Block</span><b>'+esc(x.channelBlock||"—")+'</b></div>'+
            '<div><span>Retries</span><b class="'+retryClass(x.retryPct)+'">'+esc(retry)+'</b><small>'+esc(x.retryBasis||"")+'</small></div>'+
          '</div>'+
          '<ul class="channel-actions">'+actions+'</ul>'+
          (x.status==="CONSIDER_CHANGE"?'<div class="channel-test-action"><button class="start-test-btn" data-test-index="'+items.indexOf(x)+'">Create before/after test</button></div>':'')+
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
  if(d.ok)await loadOptimizationTests();
}

document.addEventListener("click",e=>{
  const b=e.target.closest(".start-test-btn");
  if(b)startOptimizationTest(Number(b.dataset.testIndex));
});

function testStatusClass(status){
  if(["IMPROVED","IMPROVED_CONFIRMED"].includes(status))return "ALREADY_OPTIMIZED";
  if(["WORSE","WORSE_CONFIRMED"].includes(status))return "FAILED";
  if(["MONITORING","ROLLBACK_MONITORING","ROLLBACK_REQUIRED"].includes(status))return "PROTECTED";
  if(["NO_CHANGE","NO_MEANINGFUL_CHANGE","INCONCLUSIVE","INCONCLUSIVE_LOAD_CHANGED","INCONCLUSIVE_ENVIRONMENT_CHANGED"].includes(status))return "NEEDS_ATTENTION";
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
      controls='<span class="muted">A/B/A monitoring is automatic.</span>';
    }else if(t.status==="ROLLBACK_REQUIRED"){
      controls='<span class="muted">Restore original '+esc(original)+'. The optimizer will detect it automatically.</span>';
    }else if(t.status==="ROLLBACK_MONITORING"){
      controls='<span class="muted">Rollback verification is running automatically.</span>';
    }

    if(pt){
      timing='<div class="test-timing"><span>'+esc(pt.label)+'</span><b>'+esc(pt.detail)+'</b><div class="progress-track"><div class="progress-fill" style="width:'+Math.min(100,Math.max(0,pt.pct))+'%"></div></div></div>';
    }else if(t.completed_at){
      timing='<div class="test-timing"><span>Completed '+esc(fmtDateTime(t.completed_at))+'</span><b>'+esc(t.result||t.status)+'</b></div>';
    }

    const postDelta=(baseline60!=null&&t.post_retry_avg!=null)?Number(t.post_retry_avg)-Number(baseline60):null;
    const rollbackDelta=(baseline60!=null&&t.rollback_retry_avg!=null)?Number(t.rollback_retry_avg)-Number(baseline60):null;

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
        '<div class="test-description">'+esc(t.description||"")+'</div>'+
        timing+
        '<div class="test-controls">'+controls+'</div>'+
      '</div>');
  });
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
    await fetch("/api/optimization-tests/"+cancel.dataset.id+"/cancel",{method:"POST"});
    await loadOptimizationTests();
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
    if(old && old!==cur && ["IMPROVED_CONFIRMED","WORSE_CONFIRMED","NO_MEANINGFUL_CHANGE","INCONCLUSIVE","INCONCLUSIVE_LOAD_CHANGED","INCONCLUSIVE_ENVIRONMENT_CHANGED"].includes(cur)){
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
  document.getElementById("privateRfStatus").textContent=d.privateRf?.status==="NOT_CONFIGURED"?"Read-only discovery not configured":d.privateRf?.status||"—";
  document.getElementById("privateRfDetail").textContent=d.privateRf?.detail||"—";
  updateNotificationButton();
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
