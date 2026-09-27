let report=null;

document.querySelectorAll(".nav").forEach(btn=>{
  btn.addEventListener("click",()=>{
    document.querySelectorAll(".nav").forEach(x=>x.classList.remove("active"));
    document.querySelectorAll(".page").forEach(x=>x.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.page).classList.add("active");
    if(btn.dataset.page==="history") loadHistory();
  });
});

function esc(v){return String(v??"—").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
function speed(v){if(!v)return "—";return v>=1000?(v/1000)+" Gbps":v+" Mbps"}
function retryClass(v){if(v==null)return "";if(v>=20)return "bad";if(v>=10)return "warn";return "good"}

async function loadReport(){
  try{
    const r=await fetch("/api/report");
    const d=await r.json();
    if(!d.ok)throw new Error(d.error||"API error");
    report=d;
    document.getElementById("controllerPill").textContent="Controller connected";
    document.getElementById("deviceCount").textContent=d.devices.length;
    document.getElementById("clientCount").textContent=d.clients.length;
    document.getElementById("apCount").textContent=d.accessPoints.length;
    document.getElementById("highCount").textContent=d.analysis.high;
    const healthy=d.analysis.high===0;
    document.getElementById("networkStatus").textContent=healthy?"Healthy":"Needs attention";
    document.getElementById("networkStatus").className=healthy?"good":"bad";
    document.getElementById("autoSummary").textContent=d.autoOptimizeEnabled?"ON":"OFF";
    document.getElementById("autoSummary").className=d.autoOptimizeEnabled?"good":"warn";
    document.getElementById("autoToggle").checked=d.autoOptimizeEnabled;
    renderRecommendations();renderAPs();renderBroadcasts();renderClients();renderSwitches();
  }catch(e){
    document.getElementById("controllerPill").textContent="Controller error";
    document.getElementById("controllerPill").className="pill bad";
  }
}

function renderRecommendations(){
  const box=document.getElementById("recommendations");box.innerHTML="";
  const list=report.analysis.recommendations||[];
  if(!list.length){box.innerHTML='<div class="recommendation"><b>All clear</b><div class="rec-message">No active findings.</div></div>';return}
  list.forEach(x=>box.insertAdjacentHTML("beforeend",`<div class="recommendation ${esc(x.severity)}"><div class="rec-top"><span class="badge">${esc(x.severity)}</span><b>${esc(x.device)}</b><span class="muted">${esc(x.category)}</span></div><div class="rec-message">${esc(x.message)}</div></div>`));
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
    box.insertAdjacentHTML("beforeend",`<div class="ap-card"><h3>${esc(ap.name)}</h3><div class="muted">${esc(ap.model)} · ${esc(ap.clientCount)} clients · uplink ${esc(ap.uplinkName)}</div><div class="radio-grid">${radios}</div><div class="status-row"><span>CPU ${esc(ap.statistics?.cpuUtilizationPct)}% · Memory ${esc(ap.statistics?.memoryUtilizationPct)}%</span><span class="status-tag ${ap.state==='ONLINE'?'ALREADY_OPTIMIZED':'NEEDS_ATTENTION'}">${esc(ap.state)}</span></div></div>`);
  });
}

function boolPill(v){return v===true?'<span class="status-tag ALREADY_OPTIMIZED">ON</span>':v===false?'<span class="status-tag NEEDS_ATTENTION">OFF</span>':'<span class="muted">—</span>'}
function renderBroadcasts(){
  const box=document.getElementById("wifiBroadcastCards");box.innerHTML="";
  report.wifiBroadcasts.forEach(w=>{
    const st=w.optimizerStatus||{};
    const hand=w.handoffSuggestionsConfiguration||{};
    const bands=(w.broadcastingFrequenciesGHz||[]).join(" / ")||"UniFi managed";
    box.insertAdjacentHTML("beforeend",`<div class="wifi-card"><h3>${esc(w.name)}</h3><div class="muted">${esc(w.type)} · bands ${esc(bands)}</div><div class="metric"><span>Band Steering</span><span>${boolPill(w.bandSteeringEnabled)}</span></div><div class="metric"><span>BSS Transition</span><span>${boolPill(w.bssTransitionEnabled)}</span></div><div class="metric"><span>MLO</span><span>${boolPill(w.mloEnabled)}</span></div><div class="metric"><span>5 GHz handoff</span><span>${hand.band5GHzRssiThreshold??"—"} dBm</span></div><div class="metric"><span>6 GHz handoff</span><span>${hand.band6GHzRssiThreshold??"—"} dBm</span></div><div class="status-row"><span class="muted">${esc(st.detail)}</span><span class="status-tag ${esc(st.status)}">${esc(st.status)}</span></div></div>`);
  });
}

function renderClients(){
  const t=document.getElementById("clientTable");t.innerHTML="";
  report.clients.forEach(c=>t.insertAdjacentHTML("beforeend",`<tr><td>${esc(c.name)}</td><td>${esc(c.ipAddress)}</td><td>${esc(c.type)}</td><td>${esc(c.uplinkDeviceName)}</td><td>${esc(c.uplinkDeviceModel)}</td></tr>`));
}

function renderSwitches(){
  const box=document.getElementById("switchContainer");box.innerHTML="";
  report.switches.forEach(sw=>{
    let rows="";
    (((sw.interfaces||{}).ports)||[]).forEach(p=>rows+=`<tr><td>${esc(p.idx)}</td><td>${esc(p.connector)}</td><td>${esc(p.state)}</td><td>${speed(p.speedMbps)}</td><td>${speed(p.maxSpeedMbps)}</td></tr>`);
    box.insertAdjacentHTML("beforeend",`<div class="switch-block"><h3>${esc(sw.name)}</h3><div class="muted">${esc(sw.model)} · uplink ${esc(sw.uplinkName||"Gateway")}</div><div class="panel table-wrap"><table><thead><tr><th>Port</th><th>Connector</th><th>State</th><th>Speed</th><th>Capability</th></tr></thead><tbody>${rows}</tbody></table></div></div>`);
  });
}

document.getElementById("autoToggle").addEventListener("change",async e=>{
  await fetch("/api/auto-optimize",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:e.target.checked})});
  await loadReport();
});

document.getElementById("runOptimizeBtn").addEventListener("click",async()=>{
  const out=document.getElementById("optimizeResult");out.textContent="Running…";
  const r=await fetch("/api/auto-optimize/run",{method:"POST"});
  const d=await r.json();
  if(d.ok){
    out.textContent=d.results.map(x=>x.name+": "+x.status).join(" · ");
  }else out.textContent="Optimization failed";
  await loadReport();await loadHistory();
});

async function loadHistory(){
  const r=await fetch("/api/optimization-log");const d=await r.json();
  const t=document.getElementById("historyTable");t.innerHTML="";
  (d.items||[]).forEach(x=>t.insertAdjacentHTML("beforeend",`<tr><td>${esc(x.ts)}</td><td>${esc(x.action)}</td><td>${esc(x.target)}</td><td>${esc(x.detail)}</td><td>${esc(x.result)}</td></tr>`));
}

loadReport();setInterval(loadReport,60000);
