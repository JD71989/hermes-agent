import { useEffect, useState } from "react";
import { Copy, Eye, EyeOff, KeyRound, LockKeyhole, Plus, RefreshCw, ShieldCheck, Trash2, Unlock, WalletCards, UserRound } from "lucide-react";
import { api, type GuardianVaultAuditRow, type GuardianVaultCredential, type GuardianVaultStatus, type GuardianVaultWithdrawn, type GuardianWallet, type GuardianWalletCreated, type GuardianWalletWithdrawn, type GuardianIdentity } from "@/lib/api";

type Form = {
  label: string; kind: string; environment: string; username: string; secret: string;
  url: string; notes: string; allowed_consumers: string; approval: string; rotated: boolean;
};

const EMPTY: Form = {
  label: "", kind: "login", environment: "sandbox", username: "", secret: "",
  url: "", notes: "", allowed_consumers: "guardian", approval: "sandbox_auto", rotated: false,
};

function time(ts?: number | null) { return ts ? new Date(ts * 1000).toLocaleString() : "—"; }

export default function GuardianVaultPage() {
  const [status, setStatus] = useState<GuardianVaultStatus | null>(null);
  const [token, setToken] = useState("");
  const [elevated, setElevated] = useState(false);
  const [passphrase, setPassphrase] = useState("");
  const [confirm, setConfirm] = useState("");
  const [form, setForm] = useState<Form>(EMPTY);
  const [credentials, setCredentials] = useState<GuardianVaultCredential[]>([]);
  const [audit, setAudit] = useState<GuardianVaultAuditRow[]>([]);
  const [wallets, setWallets] = useState<GuardianWallet[]>([]);
  const [identities, setIdentities] = useState<GuardianIdentity[]>([]);
  const [walletSecret, setWalletSecret] = useState<GuardianWalletCreated | null>(null);
  const [walletLease, setWalletLease] = useState<GuardianWalletWithdrawn | null>(null);
  const [withdrawn, setWithdrawn] = useState<GuardianVaultWithdrawn | null>(null);
  const [walletForm, setWalletForm] = useState({ label:"", provider:"native", wallet_type:"evm", chain:"ethereum", network:"sepolia", environment:"sandbox", purpose:"Guardian crypto wallet", approval:"sandbox_auto", allowed_consumers:"guardian", spend_limit:"0" });
  const [identityForm, setIdentityForm] = useState({ label:"", email:"", username:"", provider:"operator-controlled", mode:"mailbox", purpose:"Guardian identity", business_engine:"", agent_id:"", associated_wallet_id:"", recovery_email:"", status:"planned" });
  const [workspaceStatus, setWorkspaceStatus] = useState<"READY" | "CONNECTOR REQUIRED">("CONNECTOR REQUIRED");
  const [showSecret, setShowSecret] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function refresh(t = token) {
    if (!t) return;
    const [c, a, w, i] = await Promise.all([api.guardianVaultCredentials(t), api.guardianVaultAudit(t), api.guardianVaultWallets(t), api.guardianVaultIdentities(t)]);
    setCredentials(c.credentials); setAudit(a.audit); setWallets(w.wallets); setIdentities(i.identities);
  }

  useEffect(() => {
    void api.guardianVaultStatus().then(setStatus);
    void api.guardianVaultWorkspaceStatus().then(r => setWorkspaceStatus(r.supported ? "READY" : "CONNECTOR REQUIRED")).catch(() => setWorkspaceStatus("CONNECTOR REQUIRED"));
  }, []);

  async function initialize() {
    if (passphrase !== confirm) return setMessage("Master passphrases do not match.");
    setBusy(true);
    try {
      const r = await api.guardianVaultSetup(passphrase, true);
      setToken(r.token); setElevated(true); setPassphrase(""); setConfirm(""); setStatus(r.status);
      setMessage("Guardian Vault created. Approved sandbox credentials can be device-sealed for Guardian runtime access.");
      await refresh(r.token);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Vault setup failed."); }
    finally { setBusy(false); }
  }

  async function unlock(elev = false) {
    setBusy(true);
    try {
      const r = await api.guardianVaultUnlock(passphrase, elev);
      setToken(r.token); setElevated(r.elevated); setPassphrase(""); setStatus(r.status);
      setMessage(r.elevated ? "Elevated vault session active." : "Vault unlocked.");
      await refresh(r.token);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Vault unlock failed."); }
    finally { setBusy(false); }
  }

  async function lock() {
    if (!token) return;
    setBusy(true);
    try {
      await api.guardianVaultLock(token);
      setToken(""); setElevated(false); setCredentials([]); setAudit([]); setWallets([]); setIdentities([]); setWithdrawn(null); setWalletSecret(null); setWalletLease(null);
      setStatus(await api.guardianVaultStatus()); setMessage("Vault locked.");
    } finally { setBusy(false); }
  }

  async function storeCredential() {
    if (!token) return;
    setBusy(true);
    try {
      await api.guardianVaultCreate(token, {
        label: form.label, kind: form.kind, environment: form.environment,
        username: form.username, secret: form.secret, url: form.url, notes: form.notes,
        allowed_consumers: form.allowed_consumers.split(",").map(x => x.trim()).filter(Boolean),
        approval: form.approval, rotated: form.rotated,
      });
      setForm(EMPTY); setShowSecret(false); setMessage("Credential stored encrypted.");
      await refresh(); setStatus(await api.guardianVaultStatus());
    } catch (e) { setMessage(e instanceof Error ? e.message : "Credential save failed."); }
    finally { setBusy(false); }
  }

  async function createWallet() {
    if (!token) return;
    setBusy(true);
    try {
      const r = await api.guardianVaultCreateWallet(token, { ...walletForm, allowed_consumers: walletForm.allowed_consumers.split(",").map(x=>x.trim()).filter(Boolean) });
      setWalletSecret(r); setWalletForm(v=>({...v,label:""})); await refresh(); setMessage("Wallet created and encrypted. Save the recovery phrase offline; Guardian will not display it again after this window.");
      window.setTimeout(()=>setWalletSecret(null), 60000);
    } catch(e) { setMessage(e instanceof Error ? e.message : "Wallet creation failed."); }
    finally { setBusy(false); }
  }

  async function withdrawWallet(w: GuardianWallet, recovery=false) {
    if (!token) return;
    setBusy(true);
    try { const r = await api.guardianVaultWithdrawWallet(token, w.id, { consumer:"guardian", purpose:"Guardian-approved wallet signing/export", environment:w.environment, ttl_seconds:300, export_recovery:recovery }); setWalletLease(r); setMessage(recovery ? "Elevated recovery export issued for 5 minutes." : "Signing key lease issued for 5 minutes."); window.setTimeout(()=>setWalletLease(null), 30000); }
    catch(e) { setMessage(e instanceof Error ? e.message : "Wallet withdrawal denied."); }
    finally { setBusy(false); }
  }

  async function disableWallet(id:string) {
    if (!token || !window.confirm("Deactivate this wallet?")) return;
    setBusy(true); try { await api.guardianVaultDeleteWallet(token,id); await refresh(); setMessage("Wallet deactivated."); } catch(e) { setMessage(e instanceof Error ? e.message : "Wallet deactivation failed."); } finally { setBusy(false); }
  }

  async function createIdentity() {
    if (!token) return;
    setBusy(true);
    try { await api.guardianVaultCreateIdentity(token, { ...identityForm, associated_wallet_id: identityForm.associated_wallet_id || null }); setIdentityForm(v=>({...v,label:"",email:"",username:""})); await refresh(); setMessage("Identity registered. External mailbox provisioning remains connector-gated."); }
    catch(e) { setMessage(e instanceof Error ? e.message : "Identity registration failed."); }
    finally { setBusy(false); }
  }

  async function withdraw(c: GuardianVaultCredential) {
    if (!token) return;
    setBusy(true);
    try {
      const r = await api.guardianVaultWithdraw(token, c.id, {
        consumer: "guardian",
        purpose: "Guardian-approved " + c.environment + " operation",
        environment: c.environment,
        ttl_seconds: 300,
      });
      setWithdrawn(r);
      setMessage("Lease issued for 5 minutes. Raw secrets are not exposed in the credential list.");
      window.setTimeout(() => setWithdrawn(null), 30000);
    } catch (e) { setMessage(e instanceof Error ? e.message : "Credential withdrawal denied."); }
    finally { setBusy(false); }
  }

  async function disable(id: string) {
    if (!token || !window.confirm("Deactivate this credential?")) return;
    setBusy(true);
    try { await api.guardianVaultDelete(token, id); await refresh(); setMessage("Credential deactivated."); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Deactivation failed."); }
    finally { setBusy(false); }
  }

  async function generate() {
    const r = await api.guardianVaultGeneratePassword(24);
    setForm(v => ({ ...v, secret: r.password })); setShowSecret(true);
  }

  async function copy(value: string) {
    try { await navigator.clipboard.writeText(value); setMessage("Copied."); }
    catch { setMessage("Clipboard unavailable."); }
  }

  const configured = Boolean(status?.configured);
  const unlocked = Boolean(status?.unlocked && token);

  return (
    <div className="min-h-full p-6 md:p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="rounded-2xl border border-white/10 bg-black/40 p-6 backdrop-blur-xl">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="rounded-xl border border-white/10 bg-white/5 p-3"><KeyRound size={24}/></div>
              <div><h1 className="text-2xl font-semibold tracking-tight">GUARDIAN VAULT</h1><p className="text-sm text-white/50">Credentials · approvals · audited withdrawals</p></div>
            </div>
            <div className="flex gap-2 text-xs">
              <Badge text={configured ? (unlocked ? "UNLOCKED" : "LOCKED") : "NOT CONFIGURED"}/>
              {status?.runtime_auto_unlock && <Badge text="DEVICE SEALED"/>}
              {unlocked && <button onClick={lock} className="rounded-lg border border-white/10 px-3 py-2"><LockKeyhole size={15}/></button>}
            </div>
          </div>
          {message && <div className="mt-4 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/65">{message}</div>}
        </header>

        {!configured && (
          <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
            <div className="mb-4 flex items-center gap-2"><ShieldCheck size={19}/><h2 className="font-semibold">Initialize master vault</h2></div>
            <p className="mb-5 text-sm text-white/50">The vault encrypts usernames, passwords, API keys and other secrets. The master passphrase protects the vault key; Windows can additionally seal that key to this machine for approved sandbox automation.</p>
            <div className="grid gap-3 md:grid-cols-2">
              <Input type="password" value={passphrase} onChange={setPassphrase} placeholder="Master passphrase (14+ chars)"/>
              <Input type="password" value={confirm} onChange={setConfirm} placeholder="Confirm master passphrase"/>
            </div>
            <button disabled={busy || passphrase.length < 14} onClick={initialize} className="mt-4 inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm disabled:opacity-40"><Unlock size={16}/> CREATE VAULT</button>
          </section>
        )}

        {configured && !unlocked && (
          <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
            <div className="mb-4 flex items-center gap-2"><LockKeyhole size={19}/><h2 className="font-semibold">Open management vault</h2></div>
            <div className="grid gap-3 md:grid-cols-[1fr_auto_auto]">
              <Input type="password" value={passphrase} onChange={setPassphrase} placeholder="Master passphrase"/>
              <button disabled={busy || !passphrase} onClick={() => unlock(false)} className="rounded-xl border border-white/10 px-4 py-3 text-sm">UNLOCK</button>
              <button disabled={busy || !passphrase} onClick={() => unlock(true)} className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm">ELEVATED</button>
            </div>
            {status?.runtime_auto_unlock && <p className="mt-3 text-xs text-white/40">Guardian runtime may use device-sealed sandbox credentials without exposing them to the browser. Management access still requires the master passphrase.</p>}
          </section>
        )}

        {unlocked && (
          <>
            <div className="grid gap-4 md:grid-cols-5">
              <Metric label="CREDENTIALS" value={String(credentials.length)}/>
              <Metric label="WALLETS" value={String(wallets.length)}/>
              <Metric label="IDENTITIES" value={String(identities.length)}/>
              <Metric label="SESSION" value={elevated ? "ELEVATED" : "STANDARD"}/>
              <Metric label="LEASE" value="5 MIN MAX"/>
            </div>

            <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
              <div className="mb-5 flex items-center justify-between"><div className="flex items-center gap-3"><div className="rounded-xl border border-white/10 bg-white/5 p-3"><WalletCards size={20}/></div><div><h2 className="text-lg font-semibold">Wallet Control</h2><p className="text-xs text-white/40">BIP39/BIP44-compatible EVM and Solana wallet factory. Private material stays encrypted in Guardian Vault.</p></div></div><Badge text="LIVE CONTROL PLANE"/></div>
              <div className="grid gap-5 xl:grid-cols-[1.1fr_.9fr]">
                <div className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-2"><Input value={walletForm.label} onChange={v=>setWalletForm(f=>({...f,label:v}))} placeholder="Wallet label — e.g. Research 01"/><Select value={walletForm.wallet_type} onChange={v=>setWalletForm(f=>({...f,wallet_type:v,chain:v==="solana"?"solana":"ethereum",network:v==="solana"?"devnet":"sepolia"}))} options={["evm","solana"]}/></div>
                  <div className="grid gap-3 sm:grid-cols-2"><Input value={walletForm.provider} onChange={v=>setWalletForm(f=>({...f,provider:v}))} placeholder="Provider compatibility — native / MetaMask / Trust Wallet / Phantom"/><Input value={walletForm.chain} onChange={v=>setWalletForm(f=>({...f,chain:v}))} placeholder="Chain"/></div>
                  <div className="grid gap-3 sm:grid-cols-3"><Input value={walletForm.network} onChange={v=>setWalletForm(f=>({...f,network:v}))} placeholder="Network"/><Select value={walletForm.environment} onChange={v=>setWalletForm(f=>({...f,environment:v}))} options={["sandbox","production","other"]}/><Select value={walletForm.approval} onChange={v=>setWalletForm(f=>({...f,approval:v}))} options={["sandbox_auto","operator","master"]}/></div>
                  <div className="grid gap-3 sm:grid-cols-2"><Input value={walletForm.purpose} onChange={v=>setWalletForm(f=>({...f,purpose:v}))} placeholder="Purpose"/><Input value={walletForm.spend_limit} onChange={v=>setWalletForm(f=>({...f,spend_limit:v}))} placeholder="Spend limit metadata — e.g. 25 USDC/day"/></div>
                  <Input value={walletForm.allowed_consumers} onChange={v=>setWalletForm(f=>({...f,allowed_consumers:v}))} placeholder="Approved consumers: guardian, crypto, research"/>
                  <button disabled={busy || !walletForm.label} onClick={createWallet} className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm disabled:opacity-40"><Plus size={16}/> CREATE ENCRYPTED WALLET</button>
                </div>
                <div className="space-y-3">{wallets.map(w=><div key={w.id} className="rounded-xl border border-white/10 bg-white/[.03] p-4"><div className="flex items-start justify-between gap-3"><div><div className="flex flex-wrap gap-2"><b>{w.label}</b><Badge text={w.wallet_type}/><Badge text={w.environment}/></div><p className="mt-1 text-xs text-white/50 break-all">{w.address}</p><p className="mt-1 text-xs text-white/30">{w.chain} · {w.network} · {w.provider} · path {w.derivation_path}</p></div><button onClick={()=>disableWallet(w.id)} className="rounded-lg border border-white/10 px-2 py-1 text-xs">DISABLE</button></div><div className="mt-3 flex flex-wrap gap-2"><button disabled={busy} onClick={()=>withdrawWallet(w,false)} className="rounded-lg border border-white/10 px-3 py-2 text-xs">SIGNING LEASE</button><button disabled={busy || !elevated} onClick={()=>withdrawWallet(w,true)} className="rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs">RECOVERY EXPORT</button></div></div>)}{!wallets.length && <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-sm text-white/35">No wallets registered.</div>}</div>
              </div>
            </section>

            {walletSecret && <section className="rounded-2xl border border-white/10 bg-black/40 p-6"><h2 className="font-semibold">New Wallet — One-Time Recovery Window</h2><p className="mt-1 text-xs text-white/40">Store this recovery phrase offline. It will disappear automatically.</p><div className="mt-4 grid gap-3 md:grid-cols-2"><Secret label="RECOVERY PHRASE" value={walletSecret.recovery_phrase} onCopy={copy}/><Secret label="PRIVATE KEY" value={walletSecret.private_key} secret onCopy={copy}/></div></section>}
            {walletLease && <section className="rounded-2xl border border-white/10 bg-black/40 p-6"><div className="flex items-center justify-between"><div><h2 className="font-semibold">Wallet Signing Lease</h2><p className="text-xs text-white/35">{walletLease.address} · expires {time(walletLease.expires_at)}</p></div><Badge text={walletLease.recovery_phrase ? "ELEVATED EXPORT" : "SIGNING ACCESS"}/></div><div className="mt-4 grid gap-3 md:grid-cols-2"><Secret label="PRIVATE KEY" value={walletLease.private_key} secret onCopy={copy}/>{walletLease.recovery_phrase && <Secret label="RECOVERY PHRASE" value={walletLease.recovery_phrase} onCopy={copy}/>}</div></section>}

            <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div><h2 className="text-lg font-semibold">Google Workspace Mailbox Adapter</h2><p className="text-xs text-white/40">Controlled provisioning for a Google Workspace domain you own. Requires a Vault-held service credential with the Directory user scope; consumer Gmail automation, anti-detection and verification bypass are not enabled.</p></div>
                <Badge text={workspaceStatus}/>
              </div>
              <div className="mt-4 rounded-xl border border-white/10 bg-white/[.03] p-4 text-xs text-white/45">The linked Gmail Creator project is useful as a reference for automation concepts, but Guardian is not importing its bulk-account, anti-detection, proxy-rotation or phone-verification-bypass implementation. The supported path here is admin-controlled Workspace identity provisioning.</div>
            </section>

            <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
              <div className="mb-5 flex items-center gap-3"><div className="rounded-xl border border-white/10 bg-white/5 p-3"><UserRound size={20}/></div><div><h2 className="text-lg font-semibold">Identity Factory</h2><p className="text-xs text-white/40">Register legitimate mailboxes, aliases and service identities; external provider account creation stays connector-gated.</p></div></div>
              <div className="grid gap-5 xl:grid-cols-[1fr_1fr]"><div className="grid gap-3"><div className="grid gap-3 sm:grid-cols-2"><Input value={identityForm.label} onChange={v=>setIdentityForm(f=>({...f,label:v}))} placeholder="Identity label"/><Input value={identityForm.email} onChange={v=>setIdentityForm(f=>({...f,email:v}))} placeholder="Email / alias"/></div><div className="grid gap-3 sm:grid-cols-2"><Input value={identityForm.username} onChange={v=>setIdentityForm(f=>({...f,username:v}))} placeholder="Username"/><Input value={identityForm.provider} onChange={v=>setIdentityForm(f=>({...f,provider:v}))} placeholder="Provider / domain you control"/></div><div className="grid gap-3 sm:grid-cols-2"><Select value={identityForm.mode} onChange={v=>setIdentityForm(f=>({...f,mode:v}))} options={["mailbox","alias","external"]}/><Select value={identityForm.status} onChange={v=>setIdentityForm(f=>({...f,status:v}))} options={["planned","provisioning","active","paused"]}/></div><Input value={identityForm.business_engine} onChange={v=>setIdentityForm(f=>({...f,business_engine:v}))} placeholder="Business engine — e.g. Sales / Media / Research"/><Input value={identityForm.agent_id} onChange={v=>setIdentityForm(f=>({...f,agent_id:v}))} placeholder="Agent ID (optional)"/><Select value={identityForm.associated_wallet_id} onChange={v=>setIdentityForm(f=>({...f,associated_wallet_id:v}))} options={["",...wallets.map(w=>w.id)]}/><Input value={identityForm.recovery_email} onChange={v=>setIdentityForm(f=>({...f,recovery_email:v}))} placeholder="Recovery email"/><button disabled={busy || !identityForm.label || !identityForm.email || !identityForm.username} onClick={createIdentity} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm disabled:opacity-40"><UserRound size={16}/> REGISTER IDENTITY</button></div><div className="space-y-3">{identities.map(i=><div key={i.id} className="rounded-xl border border-white/10 bg-white/[.03] p-4"><div className="flex items-center justify-between gap-3"><div><b>{i.label}</b><p className="text-xs text-white/55">{i.email} · {i.username}</p><p className="mt-1 text-xs text-white/30">{i.provider} · {i.mode} · {i.business_engine || "unassigned"} · {i.status}</p></div><Badge text={i.status}/></div></div>)}{!identities.length && <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-sm text-white/35">No identities registered.</div>}</div></div>
            </section>

            <div className="grid gap-6 xl:grid-cols-[1.2fr_.8fr]">
              <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
                <div className="mb-5 flex items-center justify-between"><div><h2 className="text-lg font-semibold">Credential Store</h2><p className="text-xs text-white/40">Secrets remain encrypted until an approved withdrawal.</p></div><button onClick={generate} className="rounded-lg border border-white/10 px-3 py-2 text-xs">GENERATE</button></div>
                <div className="space-y-3">
                  {credentials.map(c => <div key={c.id} className="rounded-xl border border-white/10 bg-white/[.03] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div><div className="flex flex-wrap gap-2"><b>{c.label}</b><Badge text={c.environment}/><Badge text={c.approval}/></div><p className="mt-1 text-xs text-white/40">{c.kind} · consumers: {c.allowed_consumers.join(", ") || "none"} · last used: {time(c.last_used_at)}</p>{c.url && <p className="mt-1 text-xs text-white/30">{c.url}</p>}</div>
                      <div className="flex gap-2"><button onClick={() => withdraw(c)} disabled={busy} className="rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs">WITHDRAW</button><button onClick={() => disable(c.id)} disabled={busy} className="rounded-lg border border-white/10 px-3 py-2"><Trash2 size={14}/></button></div>
                    </div>
                  </div>)}
                  {!credentials.length && <div className="rounded-xl border border-dashed border-white/10 p-10 text-center text-sm text-white/35">No credentials stored.</div>}
                </div>
              </section>

              <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
                <div className="mb-5 flex items-center gap-2"><Plus size={18}/><div><h2 className="text-lg font-semibold">Add Credential</h2><p className="text-xs text-white/40">Username/password, token, API key or master key.</p></div></div>
                <div className="grid gap-3">
                  <Input value={form.label} onChange={v=>setForm(f=>({...f,label:v}))} placeholder="Label — e.g. TikTok Creator"/>
                  <div className="grid gap-3 sm:grid-cols-2"><Select value={form.kind} onChange={v=>setForm(f=>({...f,kind:v}))} options={["login","api_key","token","ssh_key","certificate","master_key","other"]}/><Select value={form.environment} onChange={v=>setForm(f=>({...f,environment:v}))} options={["sandbox","production","other"]}/></div>
                  <Input value={form.username} onChange={v=>setForm(f=>({...f,username:v}))} placeholder="Username / email"/>
                  <div className="flex gap-2"><Input type={showSecret ? "text" : "password"} value={form.secret} onChange={v=>setForm(f=>({...f,secret:v}))} placeholder="Password / API key / secret"/><button onClick={()=>setShowSecret(v=>!v)} className="rounded-xl border border-white/10 px-3">{showSecret?<EyeOff size={15}/>:<Eye size={15}/>}</button></div>
                  <div className="flex gap-2"><button onClick={generate} className="rounded-lg border border-white/10 px-3 py-2 text-xs"><RefreshCw size={13}/> GENERATE PASSWORD</button></div>
                  <Input value={form.url} onChange={v=>setForm(f=>({...f,url:v}))} placeholder="Service URL"/>
                  <Input value={form.allowed_consumers} onChange={v=>setForm(f=>({...f,allowed_consumers:v}))} placeholder="Approved consumers: guardian, media, sales"/>
                  <Select value={form.approval} onChange={v=>setForm(f=>({...f,approval:v}))} options={["sandbox_auto","operator","master"]}/>
                  <textarea value={form.notes} onChange={e=>setForm(f=>({...f,notes:e.target.value}))} placeholder="Encrypted notes / signup context" className="field min-h-20"/>
                  <label className="flex items-center gap-2 text-xs text-white/45"><input type="checkbox" checked={form.rotated} onChange={e=>setForm(f=>({...f,rotated:e.target.checked}))}/> Mark credential as rotated</label>
                  {(form.environment==="production" || form.approval==="master") && <div className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/45">Elevated authorization is required to withdraw this credential.</div>}
                  <button onClick={storeCredential} disabled={busy || !form.label || !form.secret} className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm disabled:opacity-40"><KeyRound size={16}/> STORE ENCRYPTED</button>
                </div>
              </section>
            </div>

            {withdrawn && <section className="rounded-2xl border border-white/10 bg-black/40 p-6">
              <div className="flex flex-wrap items-center justify-between"><div><h2 className="font-semibold">Active Credential Lease</h2><p className="text-xs text-white/35">Expires {time(withdrawn.expires_at)} · {withdrawn.lease_id}</p></div><Badge text="ONE-TIME WINDOW"/></div>
              <div className="mt-4 grid gap-3 md:grid-cols-2"><Secret label="USERNAME" value={withdrawn.username} onCopy={copy}/><Secret label="SECRET" value={withdrawn.secret} secret onCopy={copy}/></div>
            </section>}

            <section className="rounded-2xl border border-white/10 bg-black/30 p-6">
              <h2 className="text-lg font-semibold">Audit Trail</h2><p className="mb-4 text-xs text-white/35">No secret values are written to the audit log.</p>
              <div className="overflow-auto"><table className="w-full text-left text-xs"><thead className="text-white/25"><tr><th className="py-2">TIME</th><th>ACTION</th><th>CREDENTIAL</th><th>CONSUMER</th><th>RESULT</th></tr></thead><tbody>{audit.slice(0,50).map((r,i)=><tr key={i} className="border-t border-white/5"><td className="py-2 text-white/40 whitespace-nowrap">{time(r.at)}</td><td>{r.action}</td><td>{r.label || "—"}</td><td>{r.consumer || "—"}</td><td>{r.result}</td></tr>)}</tbody></table></div>
            </section>
          </>
        )}
      </div>
      <style>{".field{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.04);border-radius:.75rem;padding:.75rem 1rem;outline:none;width:100%;color:inherit}.field:focus{border-color:rgba(255,255,255,.25)}select.field option{background:#111;color:#fff}"}</style>
    </div>
  );
}

function Input({value,onChange,placeholder,type="text"}:{value:string;onChange:(v:string)=>void;placeholder:string;type?:string}) {
  return <input type={type} value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder} className="field"/>;
}
function Select({value,onChange,options}:{value:string;onChange:(v:string)=>void;options:string[]}) {
  return <select value={value} onChange={e=>onChange(e.target.value)} className="field">{options.map(o=><option key={o}>{o}</option>)}</select>;
}
function Badge({text}:{text:string}) {
  return <span className="rounded-full border border-white/10 bg-white/5 px-2 py-1 text-[10px] text-white/45">{text}</span>;
}
function Metric({label,value}:{label:string;value:string}) {
  return <div className="rounded-xl border border-white/10 bg-black/30 p-4"><div className="text-[10px] tracking-[.18em] text-white/30">{label}</div><div className="mt-2 text-lg font-semibold">{value}</div></div>;
}
function Secret({label,value,secret,onCopy}:{label:string;value:string;secret?:boolean;onCopy:(v:string)=>void}) {
  return <div className="rounded-xl border border-white/10 bg-white/[.03] p-4"><div className="mb-2 text-[10px] tracking-[.16em] text-white/30">{label}</div><div className="flex items-center gap-2"><code className="flex-1 break-all text-sm">{secret?"••••••••••••••••":value || "—"}</code><button onClick={()=>onCopy(value)} className="rounded-lg border border-white/10 px-3 py-2"><Copy size={14}/></button></div></div>;
}
