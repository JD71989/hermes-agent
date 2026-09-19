import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Activity, ArrowUpRight, Bot, BriefcaseBusiness, ChevronRight,
  CircleDashed, Clock3, Code2, Database, Globe2, Layers3, LockKeyhole,
  Cpu, Network, Pause, Play, Radar, RefreshCw, Rocket, Server, ShieldCheck,
  Terminal, Workflow, Zap, type LucideIcon,
} from "lucide-react";
import { api, type CronJob, type EnvVarInfo, type GuardianWorkflow, type StatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type NodeStats = {
  host: string; cpu: number; ramUsed: number; cores: number;
  diskFreeGB: number | string; hermes: boolean; colibri: boolean;
  networkInterfaces: number; uptime: string; node: string;
};
type HubRow = {
  name: string; version: string; description: string; source: string;
  runtime_status: "disabled" | "enabled" | "inactive";
  can_remove: boolean; can_update_git: boolean; has_dashboard_manifest: boolean;
};
type EnvMap = Record<string, EnvVarInfo>;
type FeedEvent = { id: string; at: string; text: string; tone: "live" | "info" | "warn" };
type TabKey = "mission" | "engines" | "agents" | "automation" | "tools" | "security";

const tabs: Array<[TabKey, string, LucideIcon]> = [
  ["mission", "MISSION", Radar], ["engines", "BUSINESS", BriefcaseBusiness],
  ["agents", "AGENTS", Bot], ["automation", "AUTOMATION", Workflow],
  ["tools", "TOOL FABRIC", Layers3], ["security", "SECURITY", ShieldCheck],
];
const departments: Array<[string, string, LucideIcon]> = [
  ["INTELLIGENCE", "Research, web intelligence, forensics and opportunity discovery.", Radar],
  ["ENGINEERING", "Build, test, deploy, repair and maintain.", Code2],
  ["MARKETING", "Content, creative, campaigns and distribution.", Globe2],
  ["SECURITY", "Gates, permissions, audit and safe execution.", ShieldCheck],
  ["SALES & LEADS", "Lead acquisition, qualification, routing and follow-up.", BriefcaseBusiness],
  ["FINANCE", "Economics, attribution, revenue and risk controls.", Database],
  ["OPERATIONS", "Scheduling, services, communications and execution.", Workflow],
];
const engines = [
  ["news", "News Media", "Research → original content → traffic → monetisation", null],
  ["bond", "Bond Lead Generation", "HNW / sophisticated-investor acquisition and qualification", "BOND_API_KEY"],
  ["recovery", "Scam Recovery Leads", "Acquisition → qualification → routing → follow-up", null],
  ["crypto", "Crypto Intelligence", "Market data → opportunities → scoring → tracking", null],
  ["polymarket", "Polymarket Forensics", "Wallet feed → fingerprinting → market intelligence", null],
  ["pumpfun", "Pump.fun Intelligence", "Discovery → economics → replay → paper execution", null],
  ["pionex", "Pionex Quant", "Research → backtest → paper trading", null],
  ["media", "AI Media Farm", "Brief → assets → video → scheduling → attribution", null],
  ["voice", "Telephone / Voice Agent", "Inbound/outbound call workflows and handoff", null],
  ["web", "Website Factory", "Idea → build → deploy → iterate", null],
] as const;
const toolCards: Array<[string, string, LucideIcon]> = [
  ["Browser Use", "Browser automation", Globe2], ["BrowserAct", "Browser automation", Globe2],
  ["Remote Desktop Commander", "Local execution", Terminal], ["OpenArt", "Image / video creation", Activity],
  ["Meshy", "3D generation", Layers3], ["Higgsfield", "Cinematic media", Zap],
  ["Visualize", "Visual workflows", Radar], ["GitHub", "Source and deployment", Code2],
];

function timeNow() { return new Date().toLocaleTimeString([], { hour12: false }); }
function clamp(v: unknown) {
  const n = Number(v); return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : 0;
}
function hasKey(env: EnvMap | null, key: string) {
  const v = env?.[key]; return Boolean(v?.is_set);
}

export default function GuardianCommandCentre() {
  const [tab, setTab] = useState<TabKey>("mission");
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [node, setNode] = useState<NodeStats | null>(null);
  const [hub, setHub] = useState<HubRow[]>([]);
  const [catalog, setCatalog] = useState<any>(null);
  const [jobs, setJobs] = useState<CronJob[]>([]);
  const [workflows, setWorkflows] = useState<GuardianWorkflow[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [skills, setSkills] = useState<any[]>([]);
  const [toolsets, setToolsets] = useState<any[]>([]);
  const [env, setEnv] = useState<EnvMap | null>(null);
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [cpuHistory, setCpuHistory] = useState<number[]>([]);
  const [ramHistory, setRamHistory] = useState<number[]>([]);
  const [command, setCommand] = useState("");
  const [busy, setBusy] = useState(false);
  const lastSignature = useRef("");

  function event(text: string, tone: FeedEvent["tone"] = "info") {
    setEvents(old => [{ id: crypto.randomUUID(), at: timeNow(), text, tone }, ...old].slice(0, 16));
  }

  async function refresh() {
    const results = await Promise.allSettled([
      api.getStatus(),
      fetch("http://127.0.0.1:8781/api/stats", { cache: "no-store" }).then(async r => {
        if (!r.ok) throw new Error(String(r.status)); return r.json() as Promise<NodeStats>;
      }),
      api.getPluginsHub(), api.getPluginsCatalog(), api.getCronJobs("all"), api.getGuardianWorkflows(40),
      api.getSessions(30, 0, { order: "recent" }), api.getEnvVars(), api.getSkills(), api.getToolsets(),
    ]);
    const [s, n, h, c, j, wf, ss, e, sk, ts] = results;
    if (s.status === "fulfilled") setStatus(s.value);
    if (n.status === "fulfilled") {
      setNode(n.value);
      setCpuHistory(old => [...old, clamp(n.value.cpu)].slice(-24));
      setRamHistory(old => [...old, clamp(n.value.ramUsed)].slice(-24));
    }
    if (h.status === "fulfilled") setHub(h.value.plugins ?? []);
    if (c.status === "fulfilled") setCatalog(c.value);
    if (j.status === "fulfilled") setJobs(j.value);
    if (wf.status === "fulfilled") setWorkflows(wf.value.workflows ?? []);
    if (ss.status === "fulfilled") setSessions(ss.value.sessions ?? []);
    if (e.status === "fulfilled") setEnv(e.value as unknown as EnvMap);
    if (sk.status === "fulfilled") setSkills(sk.value);
    if (ts.status === "fulfilled") setToolsets(ts.value);
  }

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(id);
  }, []);

  const live = Boolean(status && node);
  const gateway = Boolean(status?.gateway_running);
  const pluginCount = hub.filter(p => p.runtime_status === "enabled").length;
  const activeJobs = jobs.filter(j => j.enabled !== false).length;
  const sessionsCount = status?.active_sessions ?? sessions.length;
  const signature = [node?.cpu, node?.ramUsed, node?.diskFreeGB, gateway, node?.colibri, sessionsCount, pluginCount].join("|");

  useEffect(() => {
    if (!signature || signature === lastSignature.current) return;
    lastSignature.current = signature;
    event("Heartbeat · CPU " + String(node?.cpu ?? "—") + "% · RAM " + String(node?.ramUsed ?? "—") + "%", "live");
  }, [signature]);

  async function runCommand(value = command) {
    const v = value.trim();
    if (!v) return;
    setBusy(true);
    const key = v.toLowerCase();
    try {
      if (key === "start-it" || key === "start") {
        const workflow = await api.launchGuardianWorkflow({ engine: "general", name: "Guardian START-IT", mission: "Execute the approved Guardian START-IT mission using the unified workflow controller: " + v, profile: "default" });
        setTab("automation");
        event("START-IT workflow launched · " + workflow.id, "live");
      }
      else if (key === "status" || key === "refresh") { await refresh(); event("Guardian telemetry refreshed"); }
      else if (key === "plugins" || key === "tools") setTab("tools");
      else if (key === "revenue" || key === "engines") setTab("engines");
      else if (key === "automation" || key === "cron") setTab("automation");
      else if (key === "security") setTab("security");
      else {
        const workflow = await api.launchGuardianWorkflow({ engine: "general", name: "Guardian Mission · " + v.slice(0, 42), mission: v, profile: "default" });
        setTab("automation");
        event("Mission workflow launched · " + workflow.id, "live");
      }
    } finally { setCommand(""); setBusy(false); }
  }

  async function runEngine(engineId: string, engineName: string, description: string) {
    setBusy(true);
    try {
      const workflow = await api.launchGuardianWorkflow({ engine: engineId, name: "Guardian Engine · " + engineName, mission: description, profile: "default" });
      setTab("automation");
      event("Workflow launched · " + engineName + " · " + workflow.id, "live");
    } catch {
      event("Workflow launch failed · " + engineName, "warn");
    } finally { setBusy(false); }
  }

  async function runJob(job: CronJob) {
    if (job.enabled === false) return;
    setBusy(true);
    try { await api.triggerCronJob(job.id); event("Automation fired · " + String(job.name ?? job.id), "live"); await refresh(); }
    catch { event("Automation failed · " + String(job.name ?? job.id), "warn"); }
    finally { setBusy(false); }
  }

  async function workflowAction(id: string, action: "pause" | "resume" | "retry" | "cancel") {
    setBusy(true);
    try {
      if (action === "pause") await api.pauseGuardianWorkflow(id);
      if (action === "resume") await api.resumeGuardianWorkflow(id);
      if (action === "retry") await api.retryGuardianWorkflow(id);
      if (action === "cancel") await api.cancelGuardianWorkflow(id);
      event("Workflow " + action + " · " + id, action === "cancel" ? "warn" : "live");
      await refresh();
    } catch { event("Workflow " + action + " failed · " + id, "warn"); }
    finally { setBusy(false); }
  }

  async function pluginToggle(name: string, enabled: boolean) {
    setBusy(true);
    try {
      if (enabled) await api.disableAgentPlugin(name); else await api.enableAgentPlugin(name);
      event((enabled ? "Disabled " : "Enabled ") + name, "live"); await refresh();
    } catch { event("Plugin action failed · " + name, "warn"); }
    finally { setBusy(false); }
  }

  async function pluginInstall(entry: any) {
    setBusy(true);
    try {
      const result = await api.installAgentPlugin({ identifier: entry.repo, catalog_name: entry.name, enable: true });
      event(result.ok ? "Installed · " + entry.name : "Install blocked · " + entry.name, result.ok ? "live" : "warn");
      await refresh();
    } catch { event("Plugin install failed · " + entry.name, "warn"); }
    finally { setBusy(false); }
  }

  const engineRows = useMemo(() => engines.map(e => {
    const ready = !e[3] || hasKey(env, e[3]);
    return { id: e[0], name: e[1], desc: e[2], gate: e[3], ready };
  }), [env]);

  return (
    <main className="guardian-os">
      <style>{css}</style>
      <div className="guardian-ambient" aria-hidden />
      <div className="guardian-grid" aria-hidden />
      <div className="guardian-scan" aria-hidden />
      <div className="guardian-wrap">
        <Header live={live} gateway={gateway} colibri={Boolean(node?.colibri)} busy={busy} onRefresh={refresh} />
        <Hero command={command} setCommand={setCommand} busy={busy} onRun={runCommand} onTab={setTab} node={node} status={status} sessions={sessionsCount} />
        <div className="guardian-body">
          <Rail tab={tab} setTab={setTab} />
          <section className="guardian-main">
            {tab === "mission" && <Mission node={node} status={status} jobs={jobs} events={events} sessions={sessionsCount} activeJobs={activeJobs} cpuHistory={cpuHistory} ramHistory={ramHistory} />}
            {tab === "engines" && <Engines rows={engineRows} env={env} busy={busy} onLaunch={runEngine} />}
            {tab === "agents" && <Agents sessions={sessions} skills={skills} />}
            {tab === "automation" && <Automation jobs={jobs} workflows={workflows} busy={busy} onRun={runJob} onWorkflowAction={workflowAction} />}
            {tab === "tools" && <Tools hub={hub} catalog={catalog} toolsets={toolsets} busy={busy} onToggle={pluginToggle} onInstall={pluginInstall} />}
            {tab === "security" && <Security status={status} node={node} env={env} />}
          </section>
        </div>
      </div>
    </main>
  );
}
function Header({ live, gateway, colibri, busy, onRefresh }: { live:boolean; gateway:boolean; colibri:boolean; busy:boolean; onRefresh:()=>void }) {
  return <header className="g-header">
    <div className="g-brand"><div className="g-mark"><ShieldCheck/></div><div>
      <div className="g-kicker">GUARDIAN OS // AUTONOMOUS COMMAND FABRIC</div>
      <h1>GUARDIAN <span>OS</span><small>COMMAND CENTRE / SUPER BUILD</small></h1>
      <p>Guardian01 · live control plane · Hermes + local runtime</p>
    </div></div>
    <div className="g-head-actions">
      <Badge text={live ? "LIVE" : "WAITING"} good={live}/><Badge text={gateway ? "HERMES ONLINE" : "HERMES OFFLINE"} good={gateway}/><Badge text={colibri ? "COLIBRÌ ONLINE" : "COLIBRÌ OFFLINE"} good={colibri}/>
      <a href="/guardian/vault" className="g-icon" title="Guardian Vault"><LockKeyhole/></a>
      <button className="g-icon" onClick={onRefresh} disabled={busy}><RefreshCw className={cn(busy && "spin")}/></button>
    </div>
  </header>;
}
function Badge({text,good}:{text:string;good:boolean}) { return <span className={cn("g-badge",good&&"good")}><i/>{text}</span>; }

function Hero({command,setCommand,busy,onRun,onTab,node,status,sessions}:{command:string;setCommand:(v:string)=>void;busy:boolean;onRun:(v?:string)=>void;onTab:(v:TabKey)=>void;node:NodeStats|null;status:StatusResponse|null;sessions:number}) {
  const metrics = [
    ["CPU", node ? String(Math.round(clamp(node.cpu)))+"%" : "—", node ? String(node.cores)+" CORES" : "WAITING"],
    ["MEMORY", node ? String(Math.round(clamp(node.ramUsed)))+"%" : "—", status?.memory?.pressure ?? "WAITING"],
    ["DISK FREE", node && typeof node.diskFreeGB === "number" ? node.diskFreeGB.toFixed(1)+" GB" : "—", "LIVE SAMPLE"],
    ["SESSIONS", String(sessions), status?.gateway_running ? "GATEWAY ONLINE" : "OFFLINE"],
  ];
  return <section className="g-hero"><div className="g-hero-art" aria-hidden/><div className="g-hero-overlay" aria-hidden/>
    <div className="g-hero-copy">
      <div className="g-chip">● AUTONOMY LAYER / ACTIVE</div>
      <h2>ONE COMMAND.<br/><span>EVERY CAPABILITY.</span></h2>
      <p>Everything discussed becomes a real Guardian surface: engines, plugins, agents, automation, creative tools, deployment, research and revenue workflows.</p>
      <div className="g-command"><Terminal/><input value={command} onChange={e=>setCommand(e.target.value)} onKeyDown={e=>e.key==="Enter"&&onRun()} placeholder="START-IT · REVENUE · PLUGINS · AUTOMATION · SECURITY"/><button onClick={()=>onRun()} disabled={busy}>RUN</button></div>
      <div className="g-quick"><Quick text="START-IT" icon={Rocket} onClick={()=>onRun("START-IT")}/><Quick text="BUSINESS" icon={BriefcaseBusiness} onClick={()=>onTab("engines")}/><Quick text="AUTOMATION" icon={Workflow} onClick={()=>onTab("automation")}/><Quick text="TOOL FABRIC" icon={Layers3} onClick={()=>onTab("tools")}/><Quick text="SECURITY" icon={ShieldCheck} onClick={()=>onTab("security")}/><Quick text="VAULT" icon={LockKeyhole} onClick={()=>{ window.location.href="/guardian/vault"; }}/></div>
    </div>
    <div className="g-metrics">{metrics.map(([label,value,detail])=><div className="g-metric" key={label}><small>{label}</small><b>{value}</b><span>{detail}</span></div>)}</div>
  </section>;
}
function Quick({text,icon:Icon,onClick}:{text:string;icon:LucideIcon;onClick:()=>void}) { return <button className="g-quick" onClick={onClick}><Icon/>{text}</button>; }

function Rail({tab,setTab}:{tab:TabKey;setTab:(v:TabKey)=>void}) {
  return <nav className="g-rail"><div className="g-rail-label">COMMAND</div>{tabs.map(([key,label,Icon])=><button className={cn("g-nav",tab===key&&"active")} key={key} onClick={()=>setTab(key)}><Icon/><span>{label}</span><ChevronRight/></button>)}<div className="g-rail-line"/><div className="g-rail-label">DEPARTMENTS</div>{departments.map(([label,desc,Icon])=><div className="g-dept" key={label} title={desc}><Icon/><span>{label}</span></div>)}</nav>;
}

function Panel({title,sub,icon:Icon,children}:{title:string;sub?:string;icon:LucideIcon;children:ReactNode}) {
  return <section className="g-panel"><div className="g-panel-head"><div className="g-panel-icon"><Icon/></div><div><h3>{title}</h3>{sub&&<p>{sub}</p>}</div></div>{children}</section>;
}
function Stat({label,value}:{label:string;value:string}) { return <div className="g-stat"><span>{label}</span><b>{value}</b></div>; }
function State({text,good=false}:{text:string;good?:boolean}) { return <span className={cn("g-state",good?"good":"gate")}>{text}</span>; }
function Empty({text}:{text:string}) { return <div className="g-empty"><CircleDashed/><span>{text}</span></div>; }

function Mission({node,status,jobs,events,sessions,activeJobs,cpuHistory,ramHistory}:{node:NodeStats|null;status:StatusResponse|null;jobs:CronJob[];events:FeedEvent[];sessions:number;activeJobs:number;cpuHistory:number[];ramHistory:number[]}) {
  return <div className="g-stack">
    <div className="g-grid-2">
      <Panel title="Guardian Network" sub="Observed runtime topology" icon={Network}>
        <div className="g-network"><div className="g-ring r1"/><div className="g-ring r2"/><div className="g-core"><ShieldCheck/><b>GUARDIAN01</b><small>{node?"ONLINE":"WAITING"}</small></div><div className="g-node n1"><Bot/>HERMES</div><div className="g-node n2"><Zap/>COLIBRÌ</div><div className="g-node n3"><Globe2/>TOOLS</div><div className="g-wire w1"/><div className="g-wire w2"/><div className="g-wire w3"/></div>
        <div className="g-four"><Stat label="NODE" value={node?"01":"—"}/><Stat label="SESSIONS" value={String(sessions)}/><Stat label="AUTOMATIONS" value={String(activeJobs)}/><Stat label="INTERFACES" value={String(node?.networkInterfaces??"—")}/></div>
        <div className="g-live-chart-row"><TelemetryChart icon={Cpu} label="CPU TELEMETRY" values={cpuHistory}/><TelemetryChart icon={Database} label="MEMORY TELEMETRY" values={ramHistory}/></div>
      </Panel>
      <Panel title="Runtime Health" sub="Live service posture" icon={Activity}>
        <Health label="Guardian OS" value={node?"OPERATIONAL":"WAITING"} good={Boolean(node)}/>
        <Health label="Hermes Gateway" value={gatewayStatus(status)} good={Boolean(status?.gateway_running)}/>
        <Health label="Colibrì" value={node?.colibri?"ONLINE":"OFFLINE"} good={Boolean(node?.colibri)}/>
        <Health label="Economic Gate" value="ENFORCED" good/>
        <Health label="Live Trading" value="LOCKED" good={false}/>
        <Health label="External Actions" value="GATED" good={false}/>
        <Bar label="CPU" value={node?.cpu??0}/><Bar label="MEMORY" value={node?.ramUsed??0}/><Bar label="DISK" value={status?.disk?.used_percent??0}/>
      </Panel>
    </div>
    <div className="g-grid-2">
      <Panel title="Live Activity" sub="Observed state transitions" icon={Radar}>{events.length ? events.map(e=><div className="g-event" key={e.id}><time>{e.at}</time><i className={e.tone}/><span>{e.text}</span></div>) : <Empty text="Waiting for telemetry events…"/>}</Panel>
      <Panel title="Automation Pulse" sub="Existing Hermes jobs" icon={Clock3}>{jobs.slice(0,10).map(j=><div className="g-row" key={j.id}><div><b>{j.name??j.id}</b><small>{j.schedule_display??j.schedule?.display??j.schedule?.expr??"event-driven"}</small></div><State text={j.enabled===false?"PAUSED":"ACTIVE"} good={j.enabled!==false}/></div>)}{!jobs.length&&<Empty text="No scheduled jobs returned."/>}</Panel>
    </div>
  </div>;
}
function TelemetryChart({icon:Icon,label,values}:{icon:LucideIcon;label:string;values:number[]}) {
  const points = values.length > 1 ? values.map((v,i)=>((i/(values.length-1))*100).toFixed(1)+","+(100-clamp(v)).toFixed(1)).join(" ") : "0,100 100,100";
  const latest = values.length ? Math.round(values[values.length-1])+"%" : "—";
  return <div className="g-chart"><div className="g-chart-head"><span><Icon/>{label}</span><b>{latest}</b></div><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden><polyline points={points}/></svg></div>;
}
function gatewayStatus(s:StatusResponse|null){return s?.gateway_state??"UNKNOWN";}
function Health({label,value,good}:{label:string;value:string;good:boolean}) { return <div className="g-health"><i className={good?"good":"gate"}/><div><b>{label}</b><small>{value}</small></div><span>{good?"READY":"GATED"}</span></div>; }
function Bar({label,value}:{label:string;value:number}) { return <div className="g-bar"><div><span>{label}</span><b>{Math.round(clamp(value))}%</b></div><i><em style={{width:Math.round(clamp(value))+"%"}}/></i></div>; }
function Engines({rows,env,busy,onLaunch}:{rows:any[];env:EnvMap|null;busy:boolean;onLaunch:(id:string,name:string,description:string)=>void}) {
  return <div className="g-stack"><Panel title="Business Engine Fabric" sub="Real workflow surfaces, with credential gates shown honestly" icon={BriefcaseBusiness}>
    <div className="g-engine-grid">{rows.map(r=><article className="g-engine" key={r.id}>
      <div className="g-engine-head"><div><b>{r.name}</b><small>{r.desc}</small></div><State text={r.ready?"READY":"GATED"} good={r.ready}/></div>
      <div className="g-flow"><span>DISCOVER</span><ChevronRight/><span>EXECUTE</span><ChevronRight/><span>MEASURE</span></div>
      {r.gate&&<code>{r.gate} · {hasKey(env,r.gate)?"configured":"required"}</code>}
      <button className="g-engine-run" onClick={()=>onLaunch(r.id,r.name,r.desc)} disabled={busy}>RUN ENGINE</button>
    </article>)}</div>
  </Panel><Panel title="Revenue Control Plane" sub="The revenue systems discussed are represented as end-to-end workflow domains" icon={Database}>
    <div className="g-four"><Stat label="LEADS" value="BOND + RECOVERY"/><Stat label="CONTENT" value="NEWS + MEDIA"/><Stat label="CRYPTO" value="INTEL + FORENSICS"/><Stat label="QUANT" value="PAPER ONLY"/></div>
    <div className="g-note">Revenue-producing external actions remain credential- and permission-gated. This surface never invents revenue numbers.</div>
  </Panel></div>;
}
function Agents({sessions,skills}:{sessions:any[];skills:any[]}) {
  return <div className="g-stack"><Panel title="Agent Mesh" sub="Live sessions and discoverable skills" icon={Bot}>
    <div className="g-agent-grid">{sessions.slice(0,14).map((s:any,i:number)=><div className="g-agent" key={String(s.id??i)}><div className="g-agent-core"/><div><b>{s.title??"Untitled session"}</b><small>{s.is_active?"ACTIVE":"IDLE"} · {s.tool_call_count??0} tool calls</small></div><ArrowUpRight/></div>)}{!sessions.length&&<Empty text="No session records returned."/>}</div>
    <div className="g-subhead"><span>SKILLS</span><b>{skills.length} discovered</b></div><div className="g-skill-cloud">{skills.slice(0,36).map((s:any)=><span key={String(s.name)}>{s.name}</span>)}</div>
  </Panel><Panel title="Idea → Business Pipeline" sub="The operating workflow behind new ventures" icon={Workflow}>
    <div className="g-pipeline">{["IDEA","VALIDATE","PLAN","BUILD","AUTOMATE","LAUNCH","MEASURE"].map((x,i)=><div key={x}><small>0{i+1}</small><b>{x}</b>{i<6&&<ChevronRight/>}</div>)}</div>
    <div className="g-note"><Rocket/> START-IT opens the orchestration layer; actual execution is backed by Hermes jobs and protected tool calls.</div>
  </Panel></div>;
}
function Automation({jobs,workflows,busy,onRun,onWorkflowAction}:{jobs:CronJob[];workflows:GuardianWorkflow[];busy:boolean;onRun:(job:CronJob)=>void;onWorkflowAction:(id:string,action:"pause"|"resume"|"retry"|"cancel")=>void}) {
  const running = workflows.filter(w=>w.state==="running").length;
  const paused = workflows.filter(w=>w.state==="paused").length;
  const failed = workflows.filter(w=>w.state==="failed").length;
  const completed = workflows.filter(w=>w.state==="completed").length;
  return <div className="g-stack">
    <Panel title="Guardian Workflow Controller" sub="Persistent multi-stage business workflows backed by the Hermes execution ledger" icon={Workflow}>
      <div className="g-four">
        <Stat label="RUNNING" value={String(running)}/>
        <Stat label="PAUSED" value={String(paused)}/>
        <Stat label="FAILED" value={String(failed)}/>
        <Stat label="COMPLETED" value={String(completed)}/>
      </div>
      <div className="g-job-list">
        {workflows.slice(0,20).map(w=>{
          const current = w.steps?.[Math.min(w.current_step, Math.max(0,(w.steps?.length??1)-1))];
          const done = w.steps?.filter(s=>s.status==="completed").length ?? 0;
          const total = w.steps?.length ?? 0;
          const pct = total ? Math.round((done/total)*100) : 0;
          const action = w.state==="paused" ? "resume" : (w.state==="failed" || w.state==="blocked") ? "retry" : w.state==="running" ? "pause" : null;
          return <div className="g-job" key={w.id}>
            <div>
              <b>{w.name}</b>
              <small>{w.engine.toUpperCase()} · {current?.name ?? "DONE"} · {done}/{total} stages · {pct}% · {(current?.executor ?? "pending").toUpperCase()}</small>
              <code>{w.id} · {w.state.toUpperCase()}{current?.result_summary ? " · " + current.result_summary.slice(0,110) : ""}{current?.blocker ? " · BLOCKER: " + current.blocker : ""}</code>
            </div>
            <div className="g-job-side">
              <State text={w.state.toUpperCase()} good={w.state==="running"||w.state==="completed"}/>
              {action && <button onClick={()=>onWorkflowAction(w.id,action)} disabled={busy}>{action==="pause"?<Pause/>:action==="resume"?<Play/>:<RefreshCw/>}</button>}
              {(w.state==="running"||w.state==="paused") && <button onClick={()=>onWorkflowAction(w.id,"cancel")} disabled={busy}><CircleDashed/></button>}
            </div>
          </div>;
        })}
        {!workflows.length&&<Empty text="No Guardian workflows launched yet. Use START-IT or RUN ENGINE."/>}
      </div>
    </Panel>
    <Panel title="Automation Centre" sub="Run existing enabled Hermes jobs directly" icon={Clock3}>
      <div className="g-four"><Stat label="ACTIVE" value={String(jobs.filter(j=>j.enabled!==false).length)}/><Stat label="PAUSED" value={String(jobs.filter(j=>j.enabled===false).length)}/><Stat label="NEXT" value={String(jobs.filter(j=>j.next_run_at).length)}/><Stat label="FAILED" value={String(jobs.filter(j=>String(j.last_status).toLowerCase()==="failed").length)}/></div>
      <div className="g-job-list">{jobs.slice(0,20).map(j=><div className="g-job" key={j.id}><div><b>{j.name??j.id}</b><small>{j.prompt??"No prompt preview"}</small><code>{j.schedule_display??j.schedule?.display??j.schedule?.expr??"event-driven"}</code></div><div className="g-job-side"><State text={j.enabled===false?"PAUSED":"ACTIVE"} good={j.enabled!==false}/><button onClick={()=>onRun(j)} disabled={busy||j.enabled===false}><Play/></button></div></div>)}{!jobs.length&&<Empty text="No jobs returned by Hermes."/>}</div>
    </Panel>
    <Panel title="Reusable Workflow Surface" sub="Promote one-off missions into durable schedules" icon={Layers3}>
      <div className="g-workflow-grid"><div><b>MISSION BUILDER</b><span>Idea → research → build → deploy → report.</span><button onClick={()=>window.location.assign("/cron")}>OPEN AUTOMATION</button></div><div><b>WATCHER BUILDER</b><span>Condition checks → event → gated action.</span><button onClick={()=>window.location.assign("/cron")}>OPEN WATCHERS</button></div></div>
    </Panel>
  </div>;
}
function Tools({hub,catalog,toolsets,busy,onToggle,onInstall}:{hub:HubRow[];catalog:any;toolsets:any[];busy:boolean;onToggle:(name:string,enabled:boolean)=>void;onInstall:(entry:any)=>void}) {
  const entries=Array.isArray(catalog?.entries)?catalog.entries:[];
  return <div className="g-stack"><Panel title="Unified Tool Fabric" sub="Connected capabilities surfaced as deployable infrastructure" icon={Layers3}>
    <div className="g-tool-grid">{toolCards.map(([name,desc,Icon])=><div className="g-tool" key={name}><div className="g-tool-icon"><Icon/></div><div><b>{name}</b><small>{desc}</small></div><State text="AVAILABLE" good/></div>)}</div>
  </Panel><div className="g-grid-2"><Panel title="Installed Plugins" sub={String(hub.length)+" live hub entries"} icon={Code2}>
    <div className="g-plugin-list">{hub.slice(0,30).map(p=><div className="g-plugin" key={p.name}><div><b>{p.name}</b><small>{p.description||"No description"} · v{p.version}</small></div><div className="g-plugin-side"><State text={p.runtime_status.toUpperCase()} good={p.runtime_status==="enabled"}/><button onClick={()=>onToggle(p.name,p.runtime_status==="enabled")} disabled={busy}>{p.runtime_status==="enabled"?<Pause/>:<Play/>}</button></div></div>)}{!hub.length&&<Empty text="No installed plugin records returned."/>}</div>
  </Panel><Panel title="Deployable Catalog" sub="Install curated plugins through the real Hermes endpoint" icon={Rocket}>
    <div className="g-plugin-list">{entries.slice(0,30).map((e:any)=><div className="g-plugin" key={e.name}><div><b>{e.name}</b><small>{e.capability_summary||e.description}</small><code>{e.tier} · {e.sha_short}</code></div><div className="g-plugin-side"><State text={e.installed?(e.update_available?"UPDATE":"INSTALLED"):"AVAILABLE"} good={e.installed&&!e.update_available}/>{!e.installed&&<button onClick={()=>onInstall(e)} disabled={busy}><Rocket/></button>}</div></div>)}{!entries.length&&<Empty text="Catalog unavailable or empty."/>}</div>
  </Panel></div><Panel title="Runtime Toolsets" sub={String(toolsets.length)+" configured bundles"} icon={Server}><div className="g-four">{toolsets.slice(0,12).map((t:any)=><Stat key={String(t.name)} label={String(t.name)} value={t.enabled===false?"OFF":"ON"}/>)}</div></Panel></div>;
}
function Security({status,node,env}:{status:StatusResponse|null;node:NodeStats|null;env:EnvMap|null}) {
  const keys=["BOND_API_KEY","BINANCE_API_KEY","COINBASE_API_KEY","KRAKEN_API_KEY","PIONEX_API_KEY"];
  return <div className="g-stack"><Panel title="Security Centre" sub="Execution gates and credential state" icon={LockKeyhole}>
    <div className="g-security"><Health label="Economic Gate" value="ENFORCED" good/><Health label="Live Trading" value="LOCKED" good={false}/><Health label="External Actions" value="GATED" good={false}/><Health label="Dashboard Auth" value={status?.auth_required?"PROTECTED":"LOOPBACK / SESSION"} good={Boolean(status)}/><Health label="Hermes" value={status?.gateway_running?"ONLINE":"OFFLINE"} good={Boolean(status?.gateway_running)}/><Health label="Colibrì" value={node?.colibri?"ONLINE":"OFFLINE"} good={Boolean(node?.colibri)}/></div>
    <div className="g-subhead"><span>CREDENTIAL PRESENCE</span><b>VALUES HIDDEN</b></div><div className="g-four">{keys.map(k=><Stat label={k} value={hasKey(env,k)?"SET":"MISSING"} key={k}/>)}</div>
  </Panel><Panel title="Audit Posture" sub="Actions are observable before side effects" icon={ShieldCheck}>
    <div className="g-audit"><p>Plugin installs/enables use protected Hermes dashboard endpoints.</p><p>Automation triggers only call existing enabled jobs.</p><p>Live trading and capital-moving execution remain locked.</p><p>Guardian02 final master is preserved outside this build target.</p></div>
  </Panel></div>;
}

const css=String.raw`
.guardian-os{position:relative;isolation:isolate;min-height:100%;overflow:hidden;background:#020408;color:#edf2f4;font-family:Inter,"Segoe UI",system-ui,sans-serif}
.guardian-ambient{position:absolute;inset:-20%;background:radial-gradient(circle at 25% 25%,rgba(255,128,51,.08),transparent 24%),radial-gradient(circle at 80% 65%,rgba(92,128,160,.08),transparent 22%);animation:ambient 24s ease-in-out infinite alternate;pointer-events:none}
.guardian-grid{position:absolute;inset:0;background-image:linear-gradient(rgba(255,140,72,.10) 1px,transparent 1px),linear-gradient(90deg,rgba(255,140,72,.10) 1px,transparent 1px);background-size:56px 56px;opacity:.08;animation:gridMove 28s linear infinite;pointer-events:none}
.guardian-scan{position:absolute;left:0;right:0;top:-15%;height:16%;background:linear-gradient(transparent,rgba(255,180,115,.06),transparent);animation:scan 10s linear infinite;pointer-events:none}
.guardian-wrap{position:relative;z-index:2;max-width:1900px;margin:auto;padding:14px clamp(10px,2vw,28px) 36px}
.g-header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:16px 18px;border:1px solid rgba(255,255,255,.08);background:linear-gradient(140deg,rgba(255,255,255,.05),rgba(255,255,255,.012));backdrop-filter:blur(16px)}
.g-brand{display:flex;align-items:center;gap:13px;min-width:0}.g-mark{width:48px;height:48px;display:grid;place-items:center;border:1px solid rgba(255,160,100,.38);color:#ffbe8e;background:rgba(255,120,43,.06)}.g-mark svg{width:23px}
.g-kicker,.g-brand p,.g-title small,.g-rail-label,.g-metric small,.g-metric span,.g-panel-head h3,.g-panel-head p,.g-engine-head small,.g-skill-cloud span{text-transform:uppercase;letter-spacing:.17em}
.g-kicker{font-size:7px;color:rgba(255,255,255,.28)}.g-brand h1{margin:4px 0 0;font-size:30px;line-height:1;font-weight:760;letter-spacing:.04em}.g-brand h1 span{color:#ffb47a}.g-title small{font-size:7px;font-weight:500;color:rgba(255,255,255,.25);margin-left:9px}.g-brand p{margin-top:6px;font-size:7px;color:rgba(255,255,255,.21)}
.g-head-actions{display:flex;align-items:center;justify-content:flex-end;gap:7px;flex-wrap:wrap}.g-badge{display:inline-flex;align-items:center;gap:6px;border:1px solid rgba(255,255,255,.08);padding:8px 9px;font-size:7px;letter-spacing:.14em;color:#ffbf90}.g-badge i{width:5px;height:5px;border-radius:50%;background:#ffad6c}.g-badge.good{color:#a8f0cc}.g-badge.good i{background:#6ee7ae;box-shadow:0 0 9px rgba(110,231,174,.6)}.g-icon{width:34px;height:34px;display:grid;place-items:center;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.02);color:rgba(255,255,255,.55)}
.g-hero{position:relative;min-height:530px;margin-top:14px;overflow:hidden;border:1px solid rgba(255,255,255,.08);background:#030609;box-shadow:0 25px 100px rgba(0,0,0,.38)}.g-hero-art{position:absolute;inset:-3%;background:url("/guardian01-live.png") center/cover no-repeat;filter:brightness(.42) contrast(1.14) saturate(.72);animation:heroDrift 18s ease-in-out infinite alternate}.g-hero-overlay{position:absolute;inset:0;background:radial-gradient(circle at 52% 23%,transparent 7%,rgba(2,4,7,.22) 42%,rgba(2,4,7,.92) 100%),linear-gradient(90deg,rgba(2,4,7,.86),rgba(2,4,7,.20) 54%,rgba(2,4,7,.68))}
.g-hero-copy{position:relative;z-index:1;max-width:980px;padding:42px 42px 18px}.g-chip{display:inline-flex;padding:8px 10px;border:1px solid rgba(255,255,255,.1);background:rgba(0,0,0,.28);color:#a9ebcc;font-size:7px;letter-spacing:.18em}.g-hero-copy h2{margin-top:25px;font-size:clamp(48px,6.4vw,96px);line-height:.88;letter-spacing:-.06em;font-weight:770}.g-hero-copy h2 span{color:#ffb579}.g-hero-copy p{max-width:720px;margin-top:17px;font-size:12px;line-height:1.75;color:rgba(255,255,255,.48)}
.g-command{display:flex;align-items:center;gap:9px;max-width:760px;margin-top:22px;padding:10px;border:1px solid rgba(255,255,255,.11);background:rgba(0,0,0,.4)}.g-command svg{width:16px;color:#ffb579}.g-command input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:#fff;font:11px ui-monospace,Consolas,monospace}.g-command input::placeholder{color:rgba(255,255,255,.22)}.g-command button{border:1px solid rgba(255,156,95,.28);background:rgba(255,125,36,.10);color:#ffc294;padding:8px 13px;font-size:8px;letter-spacing:.17em}
.g-quick{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}.g-quick{display:flex}.g-quick>button{display:inline-flex;align-items:center;gap:7px;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.025);padding:9px 10px;color:rgba(255,255,255,.48);font-size:7px;letter-spacing:.15em}.g-quick svg{width:12px}
.g-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;position:relative;z-index:1;padding:0 42px 28px}.g-metric{padding:12px;border:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.28);backdrop-filter:blur(10px)}.g-metric small,.g-metric span{display:block}.g-metric small{font-size:6px;color:rgba(255,255,255,.3)}.g-metric b{display:block;margin-top:6px;font:22px ui-monospace,Consolas,monospace}.g-metric span{margin-top:4px;font-size:6px;color:rgba(255,255,255,.23)}
.guardian-body{display:grid;grid-template-columns:235px minmax(0,1fr);gap:14px;margin-top:14px}.g-rail{position:sticky;top:12px;align-self:start;padding:8px;border:1px solid rgba(255,255,255,.08);background:rgba(3,6,9,.73);backdrop-filter:blur(13px)}.g-rail-label{padding:9px 10px 7px;font-size:6px;color:rgba(255,255,255,.24)}.g-nav{display:flex;align-items:center;gap:9px;width:100%;padding:10px;border:1px solid transparent;background:transparent;color:rgba(255,255,255,.4);text-align:left;font-size:8px;letter-spacing:.13em}.g-nav svg{width:13px}.g-nav svg:last-child{margin-left:auto;width:11px;opacity:.28}.g-nav.active,.g-nav:hover{border-color:rgba(255,156,95,.2);background:rgba(255,127,35,.08);color:#ffe3d0}.g-rail-line{height:1px;margin:7px 0;background:rgba(255,255,255,.05)}.g-dept{display:flex;align-items:center;gap:8px;padding:8px 10px;color:rgba(255,255,255,.28);font-size:7px}.g-dept svg{width:12px;color:#ffb579}
.g-content,.g-stack{min-width:0}.g-stack{display:grid;gap:14px}.g-grid-2{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}.g-panel{padding:16px;border:1px solid rgba(255,255,255,.08);background:linear-gradient(145deg,rgba(255,255,255,.045),rgba(255,255,255,.012));box-shadow:inset 0 1px rgba(255,255,255,.03),0 18px 70px rgba(0,0,0,.22);backdrop-filter:blur(13px)}.g-panel-head{display:flex;gap:10px;align-items:flex-start;margin-bottom:13px}.g-panel-icon{width:29px;height:29px;display:grid;place-items:center;border:1px solid rgba(255,155,94,.2);color:#ffb579}.g-panel-icon svg{width:14px}.g-panel-head h3{margin:2px 0 0;font-size:9px}.g-panel-head p{margin-top:4px;font-size:6px;color:rgba(255,255,255,.25)}
.g-network{position:relative;min-height:280px;overflow:hidden;border:1px solid rgba(255,255,255,.05);background:radial-gradient(circle at 50% 50%,rgba(255,138,58,.07),transparent 30%)}.g-network:before{content:"";position:absolute;inset:11% 16%;border:1px solid rgba(255,255,255,.05);border-radius:50%;box-shadow:0 0 0 30px rgba(255,255,255,.009),0 0 0 65px rgba(255,255,255,.006)}.g-ring{position:absolute;border:1px dashed rgba(255,153,91,.19);border-radius:50%;left:25%;top:15%;width:50%;height:70%;animation:spin 22s linear infinite}.g-ring.r2{left:13%;top:30%;width:74%;height:40%;animation-duration:29s;animation-direction:reverse}.g-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:112px;height:112px;border:1px solid rgba(255,158,97,.28);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;background:rgba(1,4,7,.88)}.g-core svg{width:24px;color:#ffc08d}.g-core b,.g-core small{font-size:8px;letter-spacing:.13em}.g-core small{color:#71efb1}.g-node{position:absolute;display:flex;align-items:center;gap:6px;padding:7px 9px;border:1px solid rgba(255,255,255,.08);background:rgba(2,5,8,.88);font-size:7px;letter-spacing:.13em}.g-node svg{width:12px}.n1{left:18%;top:17%}.n2{right:18%;top:17%}.n3{left:50%;bottom:17%;transform:translateX(-50%)}.g-wire{position:absolute;height:1px;background:linear-gradient(90deg,transparent,rgba(255,168,107,.42),transparent);transform-origin:left}.w1{left:30%;top:40%;width:30%;transform:rotate(12deg)}.w2{left:52%;top:40%;width:30%;transform:rotate(168deg)}.w3{left:50%;top:60%;width:28%;transform:rotate(90deg)}
.g-four{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.g-stat{padding:9px;border:1px solid rgba(255,255,255,.06);background:rgba(0,0,0,.14)}.g-stat span,.g-stat b{display:block}.g-stat span{font-size:6px;letter-spacing:.15em;color:rgba(255,255,255,.25)}.g-stat b{margin-top:5px;font:9px ui-monospace,Consolas,monospace;color:#dfe6ea}
.g-health{display:flex;align-items:center;gap:8px;padding:8px 1px;border-bottom:1px solid rgba(255,255,255,.05)}.g-health>i{width:6px;height:6px;border-radius:50%;background:#71efb1}.g-health>i.gate{background:#ffb36e}.g-health>div{min-width:0;flex:1}.g-health b,.g-health small{display:block}.g-health b{font-size:8px}.g-health small{margin-top:3px;font-size:6px;color:rgba(255,255,255,.25)}.g-bar{margin-top:9px}.g-bar>div{display:flex;justify-content:space-between;font-size:6px;letter-spacing:.11em;color:rgba(255,255,255,.26)}.g-bar b{font:7px ui-monospace,Consolas,monospace;color:#ffbd8a}.g-bar>i{display:block;height:3px;margin-top:4px;overflow:hidden;background:rgba(255,255,255,.05)}.g-bar em{display:block;height:100%;background:linear-gradient(90deg,#9e5629,#ffb87f)}
.g-live-chart-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin-top:9px}.g-chart{min-width:0;padding:10px;border:1px solid rgba(255,255,255,.06);background:rgba(0,0,0,.13)}.g-chart-head{display:flex;align-items:center;justify-content:space-between;gap:8px}.g-chart-head span{display:flex;align-items:center;gap:6px;font-size:6px;letter-spacing:.14em;color:rgba(255,255,255,.27)}.g-chart-head span svg{width:11px;color:#ffb77e}.g-chart-head b{font:9px ui-monospace,Consolas,monospace;color:#ffbd8a}.g-chart svg{display:block;width:100%;height:64px;margin-top:7px;background-image:linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px);background-size:20px 20px}.g-chart polyline{fill:none;stroke:#ffb77e;stroke-width:2;vector-effect:non-scaling-stroke}\n.g-event,.g-row{display:flex;align-items:center;gap:8px;border-bottom:1px solid rgba(255,255,255,.05);padding:8px 2px}.g-event time{width:51px;font:6px ui-monospace,Consolas,monospace;color:rgba(255,255,255,.2)}.g-event i{width:5px;height:5px;border-radius:50%;background:#8da0ff}.g-event i.live{background:#71efb1;box-shadow:0 0 7px rgba(113,239,177,.5)}.g-event i.warn{background:#ffb16b}.g-event span,.g-row b,.g-row small{font-size:7px}.g-row>div{min-width:0;flex:1}.g-row b,.g-row small{display:block}.g-row small{margin-top:3px;color:rgba(255,255,255,.24)}
.g-state{font:6px ui-monospace,Consolas,monospace;letter-spacing:.11em}.g-state.good{color:#86e6ba}.g-state.gate{color:#ffbc88}
.g-engine-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.g-engine{padding:11px;border:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.13)}.g-engine-head{display:flex;justify-content:space-between;gap:7px}.g-engine-head b{display:block;font-size:8px}.g-engine-head small{display:block;margin-top:5px;font-size:6px;line-height:1.55;color:rgba(255,255,255,.28)}.g-engine code{display:block;margin-top:8px;font:6px ui-monospace,Consolas,monospace;color:#ffbd8b}.g-engine-run{margin-top:10px;border:1px solid rgba(255,156,95,.22);background:rgba(255,127,36,.07);color:#ffc08f;padding:7px 9px;font-size:6px;letter-spacing:.13em}.g-flow{display:flex;align-items:center;gap:3px;margin-top:10px;font:6px ui-monospace,Consolas,monospace;color:rgba(255,255,255,.18)}.g-flow svg{width:9px}.g-note{display:flex;gap:9px;align-items:center;margin-top:10px;padding:10px;border:1px solid rgba(255,158,99,.14);background:rgba(255,127,35,.035);font-size:7px;color:rgba(255,255,255,.28)}.g-note svg{width:14px;color:#ffb67d;flex:0 0 auto}
.g-agent-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}.g-agent{display:flex;align-items:center;gap:9px;padding:10px;border:1px solid rgba(255,255,255,.07)}.g-agent b,.g-agent small{display:block}.g-agent b{font-size:7px}.g-agent small{margin-top:3px;font-size:6px;color:rgba(255,255,255,.24)}.g-agent>svg{margin-left:auto;width:11px;color:rgba(255,255,255,.25)}.g-agent-core{width:22px;height:22px;border:1px dashed rgba(255,155,93,.36);border-radius:50%;position:relative}.g-agent-core:after{content:"";position:absolute;width:4px;height:4px;left:9px;top:-3px;border-radius:50%;background:#ffb67d;animation:orbit 2.8s linear infinite}.g-subhead{display:flex;justify-content:space-between;margin:14px 0 8px;font-size:6px;letter-spacing:.17em;color:rgba(255,255,255,.25)}.g-subhead b{color:rgba(255,255,255,.4)}.g-skill-cloud{display:flex;flex-wrap:wrap;gap:4px}.g-skill-cloud span{padding:4px 5px;border:1px solid rgba(255,255,255,.06);font-size:5px;color:rgba(255,255,255,.27)}
.g-pipeline{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}.g-pipeline>div{display:flex;align-items:center;gap:4px;padding:9px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.016)}.g-pipeline small{font:6px ui-monospace,Consolas,monospace;color:#ffb67c}.g-pipeline b{font-size:6px;letter-spacing:.11em}.g-pipeline svg{margin-left:auto;width:9px;color:rgba(255,255,255,.16)}
.g-job-list,.g-plugin-list{display:grid;gap:6px;max-height:500px;overflow:auto}.g-job,.g-plugin{display:flex;align-items:center;gap:10px;padding:9px;border:1px solid rgba(255,255,255,.06);background:rgba(0,0,0,.14)}.g-job>div:first-child,.g-plugin>div:first-child{min-width:0;flex:1}.g-job b,.g-job small,.g-job code,.g-plugin b,.g-plugin small{display:block}.g-job b,.g-plugin b{font-size:7px}.g-job small,.g-plugin small{margin-top:3px;font-size:6px;color:rgba(255,255,255,.24);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.g-job code{margin-top:3px;font:5px ui-monospace,Consolas,monospace;color:rgba(255,255,255,.17)}.g-job-side,.g-plugin-side{display:flex;align-items:center;gap:7px}.g-job-side button,.g-plugin-side button{width:28px;height:28px;display:grid;place-items:center;border:1px solid rgba(255,255,255,.08);background:rgba(255,255,255,.02);color:#ffb67d}.g-job-side svg,.g-plugin-side svg{width:11px}
.g-workflow-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.g-workflow-grid>div{padding:12px;border:1px solid rgba(255,255,255,.06)}.g-workflow-grid b,.g-workflow-grid span{display:block}.g-workflow-grid b{font-size:7px;letter-spacing:.14em}.g-workflow-grid span{margin-top:6px;font-size:6px;line-height:1.5;color:rgba(255,255,255,.25)}.g-workflow-grid button{margin-top:9px;padding:7px 9px;border:1px solid rgba(255,156,96,.22);background:rgba(255,127,36,.06);color:#ffc08f;font-size:6px;letter-spacing:.13em}
.g-tool-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.g-tool{display:flex;align-items:center;gap:8px;padding:9px;border:1px solid rgba(255,255,255,.06)}.g-tool-icon{width:27px;height:27px;display:grid;place-items:center;border:1px solid rgba(255,156,96,.18);color:#ffb77e}.g-tool-icon svg{width:12px}.g-tool b,.g-tool small{display:block}.g-tool b{font-size:7px}.g-tool small{margin-top:3px;font-size:6px;color:rgba(255,255,255,.22)}.g-security{display:grid;grid-template-columns:repeat(2,1fr);gap:2px 10px}.g-audit{display:grid;gap:6px}.g-audit p{margin:0;padding:9px;border:1px solid rgba(255,255,255,.06);font-size:7px;color:rgba(255,255,255,.27)}
.g-empty{display:flex;align-items:center;justify-content:center;gap:7px;padding:26px;color:rgba(255,255,255,.23);font-size:7px}.g-empty svg{width:13px}
button{transition:background .16s ease,border-color .16s ease,color .16s ease,transform .16s ease}.g-icon:hover,.g-command button:hover,.g-quick>button:hover,.g-job-side button:hover,.g-plugin-side button:hover{border-color:rgba(255,157,93,.24);background:rgba(255,125,35,.08);color:#fff}
button:focus-visible,input:focus-visible{outline:2px solid #ffb27e;outline-offset:2px}
@keyframes ambient{to{transform:translate3d(2%,1%,0) scale(1.05)}}@keyframes gridMove{to{background-position:56px 56px,56px 56px}}@keyframes scan{to{transform:translateY(740%)}}@keyframes heroDrift{to{transform:scale(1.07) translate3d(.5%,-.4%,0)}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes orbit{to{transform:rotate(360deg) translateX(9px) rotate(-360deg)}}
@media(max-width:1100px){.guardian-body{grid-template-columns:1fr}.g-rail{position:relative;display:flex;overflow:auto;gap:4px}.g-rail-label,.g-rail-line,.g-dept{display:none}.g-nav{min-width:136px}.g-engine-grid{grid-template-columns:repeat(2,1fr)}.g-tool-grid{grid-template-columns:repeat(2,1fr)}}
@media(max-width:760px){.g-header{align-items:flex-start;flex-direction:column}.g-hero-copy{padding:28px 20px 12px}.g-metrics{grid-template-columns:repeat(2,1fr);padding:0 20px 20px}.g-grid-2,.g-security,.g-agent-grid,.g-workflow-grid{grid-template-columns:1fr}.g-engine-grid,.g-tool-grid,.g-live-chart-row{grid-template-columns:1fr}.g-four{grid-template-columns:repeat(2,1fr)}.g-pipeline{grid-template-columns:repeat(2,1fr)}.g-pipeline svg{display:none}.g-hero-copy h2{font-size:44px}.g-command{flex-wrap:wrap}.g-command input{min-width:180px}}
@media(prefers-reduced-motion:reduce){.guardian-ambient,.guardian-grid,.guardian-scan,.g-hero-art,.g-ring,.g-agent-core:after{animation:none}}
`;
