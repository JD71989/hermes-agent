import { Link, useParams } from "react-router";
import { ArrowLeft, Bot, Building2, CheckCircle2, LockKeyhole, Network, ShieldCheck, Sparkles } from "lucide-react";

const DEPARTMENTS: Record<string,{name:string;capabilities:string[]}> = {
  marketing:{name:"Marketing",capabilities:["Content","Social / X","SEO","Websites","Creative","Advertising","Analytics"]},
  security:{name:"Security",capabilities:["Cybersecurity","Vulnerability Research","Monitoring","Threat Intelligence","CyberLab"]},
  "research-intelligence":{name:"Research & Intelligence",capabilities:["Web Research","Market Research","Competitive Intelligence","Data Analysis"]},
  engineering:{name:"Engineering",capabilities:["Software","Websites","APIs","Infrastructure","Deployment"]},
  "sales-leads":{name:"Sales & Leads",capabilities:["Lead Generation","Qualification","CRM","Outreach"]},
  finance:{name:"Finance",capabilities:["Revenue","Costs","P&L","Opportunity Analysis"]},
  operations:{name:"Operations",capabilities:["Workflows","Automation","Agents","Scheduling","Communications","Telephony"]},
};

const BUSINESS: Record<string,{name:string;status:string;departments:string[];agents:string[];controls:string[]}> = {
  "news-media":{name:"News Media Engine",status:"DEVELOPMENT",departments:["Research & Intelligence","Marketing","Engineering","Finance","Operations"],agents:["Trend Detector","Researcher","Cross-checker","Originality Checker","Editorial Agent","SEO Agent","Publisher","Analytics Agent"],controls:["Originality / copyright safeguards","Editorial review gate","External credentials gated","External publishing disabled"]},
};

export default function GuardianArchitecturePage(){
  const {kind,id}=useParams();
  const item = kind==="department" ? DEPARTMENTS[id||""] : BUSINESS[id||""];
  if(!item) return <div className="p-8 text-white/60">Architecture module not found.</div>;
  const isDept=kind==="department";
  return <div className="min-h-full bg-[#03070b] p-6 text-white md:p-10"><div className="mx-auto max-w-5xl">
    <Link to="/guardian" className="mb-6 inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-white/35 hover:text-cyan-200"><ArrowLeft className="h-3.5 w-3.5"/> Guardian OS</Link>
    <div className="rounded-[28px] border border-cyan-300/15 bg-white/[0.025] p-6 md:p-8"><div className="flex items-start justify-between gap-4"><div><div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.3em] text-cyan-300/65"><Sparkles className="h-3.5 w-3.5"/> {isDept?"Department":"Business Plugin"}</div><h1 className="mt-3 text-3xl font-semibold">{item.name}</h1><p className="mt-2 text-sm text-white/35">{isDept?"Capability domain inside Guardian OS.":"Business engine assembled from Guardian departments and agents."}</p></div><div className="rounded-xl border border-cyan-300/15 bg-cyan-300/[0.05] p-3"><ShieldCheck className="h-6 w-6 text-cyan-200"/></div></div>
    {isDept ? <><div className="mt-8 text-[9px] font-bold uppercase tracking-[0.25em] text-white/30">Capabilities</div><div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{(item as typeof DEPARTMENTS[string]).capabilities.map(x=><div key={x} className="rounded-xl border border-white/[0.07] bg-black/20 p-4"><Network className="h-4 w-4 text-cyan-300"/><div className="mt-3 text-sm font-medium">{x}</div><div className="mt-1 text-[9px] uppercase tracking-widest text-white/25">available to plugins</div></div>)}</div></> : <><div className="mt-8 flex items-center gap-3"><span className="rounded-full border border-cyan-300/15 bg-cyan-300/[0.05] px-3 py-1.5 text-[9px] font-bold tracking-widest text-cyan-200/70">{(item as typeof BUSINESS[string]).status}</span><span className="text-[10px] text-white/25">External actions gated</span></div><div className="mt-8 grid gap-3 md:grid-cols-2"><div><div className="text-[9px] font-bold uppercase tracking-[0.25em] text-white/30">Departments</div><div className="mt-3 space-y-2">{(item as typeof BUSINESS[string]).departments.map(x=><div key={x} className="flex items-center gap-2 rounded-xl border border-white/[0.07] bg-black/20 p-3"><Building2 className="h-4 w-4 text-cyan-300"/><span className="text-sm">{x}</span></div>)}</div></div><div><div className="text-[9px] font-bold uppercase tracking-[0.25em] text-white/30">Agents</div><div className="mt-3 space-y-2">{(item as typeof BUSINESS[string]).agents.map(x=><div key={x} className="flex items-center gap-2 rounded-xl border border-white/[0.07] bg-black/20 p-3"><Bot className="h-4 w-4 text-cyan-300"/><span className="text-sm">{x}</span></div>)}</div></div></div><div className="mt-8"><div className="text-[9px] font-bold uppercase tracking-[0.25em] text-white/30">Controls</div><div className="mt-3 grid gap-2 sm:grid-cols-2">{(item as typeof BUSINESS[string]).controls.map(x=><div key={x} className="flex items-center gap-2 text-xs text-white/55"><CheckCircle2 className="h-3.5 w-3.5 text-cyan-300/70"/>{x}</div>)}</div></div></>}</div>
    <div className="mt-4 rounded-2xl border border-white/[0.07] bg-white/[0.02] p-5"><div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.25em] text-white/30"><LockKeyhole className="h-3.5 w-3.5"/> Operating rule</div><p className="mt-2 text-xs leading-5 text-white/35">Departments provide capabilities. Agents perform capabilities. Plugins combine capabilities into businesses. Guardian Core orchestrates everything.</p></div>
  </div></div>;
}
