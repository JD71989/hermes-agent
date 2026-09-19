import { useMemo, useState } from "react";
import { ArrowRight, BadgeCheck, CircleDollarSign, FlaskConical, Gauge, Lightbulb, LockKeyhole, ShieldCheck, Target, TrendingUp } from "lucide-react";

const checks = [
  ["customer", "Clear paying customer", "Who pays, and what painful problem are they already trying to solve?"],
  ["offer", "Specific offer", "Can the first version be explained in one sentence with a concrete outcome?"],
  ["acquisition", "Acquisition path", "Is there a realistic channel to reach the first 10 customers/users?"],
  ["economics", "Unit economics", "Can revenue, gross margin, acquisition cost and delivery cost be estimated?"],
  ["advantage", "Defensibility / edge", "Is there a reason this can survive beyond a copyable landing page?"],
  ["execution", "Execution feasibility", "Can Guardian build a testable MVP with the available capabilities and credentials?"],
  ["risk", "Risk / compliance", "Are legal, platform, privacy and operational risks understood before launch?"],
] as const;

const defaultState = Object.fromEntries(checks.map(([id]) => [id, 0])) as Record<string, number>;

export default function GuardianIdeaLabPage() {
  const [idea, setIdea] = useState("");
  const [customer, setCustomer] = useState("");
  const [price, setPrice] = useState("");
  const [cost, setCost] = useState("");
  const [answers, setAnswers] = useState<Record<string, number>>(defaultState);
  const [tested, setTested] = useState(false);

  const economics = useMemo(() => {
    const p = Number(price);
    const c = Number(cost);
    if (!p || !Number.isFinite(p) || !Number.isFinite(c)) return null;
    return { margin: p - c, marginPct: p > 0 ? ((p - c) / p) * 100 : 0 };
  }, [price, cost]);

  const result = useMemo(() => {
    const total = Object.values(answers).reduce((a, b) => a + b, 0);
    const economicsPenalty = economics && economics.marginPct < 20 ? 2 : 0;
    const score = total - economicsPenalty;
    const verdict = score >= 17 ? "READY_TO_VALIDATE" : score >= 10 ? "REVISE" : "DO_NOT_BUILD_YET";
    return { total, score, verdict };
  }, [answers, economics]);

  const setAnswer = (id: string, value: number) => setAnswers((prev) => ({ ...prev, [id]: value }));

  return (
    <div className="min-h-full bg-[#03070b] text-white">
      <div className="mx-auto max-w-[1500px] px-4 py-6 md:px-8 md:py-8">
        <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.32em] text-cyan-300/65"><FlaskConical className="h-3.5 w-3.5" /> Guardian Idea Lab</div>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] md:text-5xl">Idea → evidence → business case.</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-white/45">Capture an idea, pressure-test the customer, acquisition path and economics, then decide whether it earns a place in the build pipeline. This page validates; it does not deploy.</p>
          </div>
          <div className="rounded-2xl border border-amber-300/15 bg-amber-300/[0.04] px-4 py-3 text-[9px] font-bold uppercase tracking-[0.2em] text-amber-200/65"><LockKeyhole className="mr-2 inline h-3.5 w-3.5" /> External actions gated</div>
        </header>

        <div className="grid gap-5 lg:grid-cols-[1.05fr_.95fr]">
          <section className="rounded-3xl border border-white/[0.08] bg-white/[0.025] p-5 md:p-6">
            <div className="mb-5 flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.25em] text-cyan-300/60"><Lightbulb className="h-4 w-4" /> New idea</div>
            <label className="text-[10px] font-bold uppercase tracking-widest text-white/35">Idea</label>
            <textarea value={idea} onChange={(e) => setIdea(e.target.value)} placeholder="e.g. Automated lead qualification service for a specific niche..." className="mt-2 min-h-28 w-full rounded-2xl border border-white/10 bg-black/25 p-4 text-sm text-white outline-none transition placeholder:text-white/20 focus:border-cyan-300/35" />
            <label className="mt-5 block text-[10px] font-bold uppercase tracking-widest text-white/35">Target customer</label>
            <input value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="Who pays?" className="mt-2 w-full rounded-xl border border-white/10 bg-black/25 p-3 text-sm outline-none placeholder:text-white/20 focus:border-cyan-300/35" />
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div><label className="text-[10px] font-bold uppercase tracking-widest text-white/35">Expected price / sale</label><div className="mt-2 flex items-center rounded-xl border border-white/10 bg-black/25"><span className="pl-3 text-white/25">$</span><input value={price} onChange={(e) => setPrice(e.target.value)} inputMode="decimal" className="w-full bg-transparent p-3 text-sm outline-none" /></div></div>
              <div><label className="text-[10px] font-bold uppercase tracking-widest text-white/35">Variable delivery cost</label><div className="mt-2 flex items-center rounded-xl border border-white/10 bg-black/25"><span className="pl-3 text-white/25">$</span><input value={cost} onChange={(e) => setCost(e.target.value)} inputMode="decimal" className="w-full bg-transparent p-3 text-sm outline-none" /></div></div>
            </div>
            <button onClick={() => setTested(true)} disabled={!idea.trim() || !customer.trim()} className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-300/25 bg-cyan-300/[0.08] px-4 py-3 text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-100 transition hover:bg-cyan-300/[0.13] disabled:cursor-not-allowed disabled:opacity-30">Run validation gate <ArrowRight className="h-4 w-4" /></button>
          </section>

          <section className="rounded-3xl border border-white/[0.08] bg-white/[0.025] p-5 md:p-6">
            <div className="mb-5 flex items-center justify-between"><div className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.25em] text-cyan-300/60"><Gauge className="h-4 w-4" /> Validation gate</div><span className="text-[9px] uppercase tracking-widest text-white/25">7 checks</span></div>
            <div className="space-y-3">
              {checks.map(([id, title, description]) => (
                <div key={id} className="rounded-2xl border border-white/[0.07] bg-black/15 p-3">
                  <div className="flex items-start justify-between gap-3"><div><div className="text-xs font-semibold text-white/80">{title}</div><div className="mt-1 text-[10px] leading-4 text-white/30">{description}</div></div><div className="flex shrink-0 gap-1">{[0,1,2,3].map((v) => <button key={v} onClick={() => setAnswer(id, v)} className={"h-7 w-7 rounded-lg border text-[9px] font-bold transition " + (answers[id] === v ? "border-cyan-300/40 bg-cyan-300/15 text-cyan-100" : "border-white/10 text-white/25 hover:border-white/20")}>{v}</button>)}</div></div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <section className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4"><Target className="h-4 w-4 text-cyan-300" /><div className="mt-3 text-[9px] uppercase tracking-widest text-white/30">Evidence score</div><div className="mt-1 text-2xl font-semibold">{tested ? result.score : "—"}<span className="text-xs text-white/25"> / 21</span></div></div>
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4"><CircleDollarSign className="h-4 w-4 text-cyan-300" /><div className="mt-3 text-[9px] uppercase tracking-widest text-white/30">Gross contribution</div><div className="mt-1 text-2xl font-semibold">{economics ? economics.margin.toFixed(2) : "—"}</div><div className="text-[10px] text-white/25">{economics ? economics.marginPct.toFixed(1) + "% before acquisition/overhead" : "Enter price and cost"}</div></div>
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4"><TrendingUp className="h-4 w-4 text-cyan-300" /><div className="mt-3 text-[9px] uppercase tracking-widest text-white/30">Pipeline state</div><div className="mt-1 text-sm font-semibold">{tested ? result.verdict.replaceAll("_", " ") : "NOT TESTED"}</div></div>
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4"><ShieldCheck className="h-4 w-4 text-cyan-300" /><div className="mt-3 text-[9px] uppercase tracking-widest text-white/30">Deployment</div><div className="mt-1 text-sm font-semibold">LOCKED</div><div className="text-[10px] text-white/25">Approval + build + test required</div></div>
        </section>

        <section className="mt-5 rounded-3xl border border-cyan-300/10 bg-cyan-300/[0.025] p-5 md:p-6">
          <div className="flex items-start gap-3"><BadgeCheck className="mt-0.5 h-5 w-5 shrink-0 text-cyan-300" /><div><h2 className="text-sm font-semibold">Guardian pipeline</h2><p className="mt-2 text-xs leading-5 text-white/40">IDEA → VALIDATE → BUSINESS MODEL → CAPABILITY MAP → PLUGIN SPEC → BUILD → TEST → DEPLOY → OPERATE → MEASURE → LEARN → SCALE.</p><p className="mt-2 text-[10px] leading-4 text-white/25">The current gate is intentionally deterministic and conservative. External research, competitor checks, market sizing and actual revenue validation are separate evidence steps and are not claimed by this local form.</p></div></div>
        </section>
      </div>
    </div>
  );
}
