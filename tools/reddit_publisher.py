"""Guardian Reddit human-in-the-loop publisher queue."""
from __future__ import annotations
import hashlib, json, secrets, sqlite3, time
from pathlib import Path
from typing import Any
from tools.registry import registry

SCHEMA = {
    "type":"object",
    "properties":{
        "action":{"type":"string","enum":["create_draft","list_queue","get_item","approve","mark_published","record_metrics"]},
        "item_id":{"type":"integer"},"subreddit":{"type":"string"},"thread_url":{"type":"string"},
        "thread_title":{"type":"string"},"draft":{"type":"string"},"source_urls":{"type":"array","items":{"type":"string"}},
        "rule_notes":{"type":"string"},"risk_flags":{"type":"array","items":{"type":"string"}},
        "approval_token":{"type":"string"},"explicit_confirmation":{"type":"boolean"},
        "post_url":{"type":"string"},"platform_post_id":{"type":"string"},
        "impressions":{"type":"integer"},"likes":{"type":"integer"},"comments":{"type":"integer"},
        "shares":{"type":"integer"},"clicks":{"type":"integer"},"conversions":{"type":"integer"},
    },"required":["action"],"additionalProperties":False
}

def _path():
    from hermes_constants import get_hermes_home
    p=Path(get_hermes_home())/"reddit_publisher.sqlite3"; p.parent.mkdir(parents=True,exist_ok=True); return p

def _conn():
    c=sqlite3.connect(_path()); c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS reddit_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT, subreddit TEXT NOT NULL, thread_url TEXT NOT NULL,
        thread_title TEXT DEFAULT '', draft TEXT NOT NULL, source_urls TEXT DEFAULT '[]',
        rule_notes TEXT DEFAULT '', risk_flags TEXT DEFAULT '[]', status TEXT DEFAULT 'pending_approval',
        approval_token_hash TEXT, approved_at REAL, published_at REAL, post_url TEXT,
        platform_post_id TEXT, impressions INTEGER DEFAULT 0, likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, clicks INTEGER DEFAULT 0,
        conversions INTEGER DEFAULT 0, created_at REAL NOT NULL)"""); c.commit(); return c

def _row(r):
    d=dict(r); d["source_urls"]=json.loads(d["source_urls"] or "[]"); d["risk_flags"]=json.loads(d["risk_flags"] or "[]"); return d

def _handle(a:dict[str,Any],**_kw):
    try:
        c=_conn(); act=a.get("action")
        if act=="create_draft":
            sub=str(a.get("subreddit","")).strip(); url=str(a.get("thread_url","")).strip(); draft=str(a.get("draft","")).strip()
            if not sub or not draft or not url: return json.dumps({"error":"subreddit, thread_url and draft are required"})
            if not url.startswith(("https://www.reddit.com/","https://reddit.com/")): return json.dumps({"error":"thread_url must be a Reddit URL"})
            rows=c.execute("SELECT * FROM reddit_queue WHERE thread_url=? AND status NOT IN ('rejected','expired')",(url,)).fetchall()
            digest=hashlib.sha256(draft.encode()).hexdigest()
            for r in rows:
                if hashlib.sha256(r["draft"].encode()).hexdigest()==digest: return json.dumps({"success":True,"duplicate":True,"item":_row(r)})
            cur=c.execute("INSERT INTO reddit_queue(subreddit,thread_url,thread_title,draft,source_urls,rule_notes,risk_flags,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (sub,url,str(a.get("thread_title","")),draft,json.dumps(a.get("source_urls",[])),str(a.get("rule_notes","")),json.dumps(a.get("risk_flags",[])),time.time()))
            c.commit(); return json.dumps({"success":True,"item":_row(c.execute("SELECT * FROM reddit_queue WHERE id=?",(cur.lastrowid,)).fetchone())})
        if act=="list_queue":
            status=a.get("status"); rows=c.execute("SELECT * FROM reddit_queue"+(" WHERE status=?" if status else "")+" ORDER BY created_at DESC",((status,) if status else ())).fetchall()
            return json.dumps({"success":True,"items":[_row(r) for r in rows],"count":len(rows)})
        if act=="get_item":
            r=c.execute("SELECT * FROM reddit_queue WHERE id=?",(a.get("item_id"),)).fetchone()
            return json.dumps({"success":True,"item":_row(r)}) if r else json.dumps({"error":"item not found"})
        if act=="approve":
            r=c.execute("SELECT * FROM reddit_queue WHERE id=?",(a.get("item_id"),)).fetchone()
            if not r:return json.dumps({"error":"item not found"})
            if r["status"]!="pending_approval":return json.dumps({"error":f"item is {r['status']}, not pending_approval"})
            token=secrets.token_urlsafe(24); h=hashlib.sha256(token.encode()).hexdigest()
            c.execute("UPDATE reddit_queue SET status='approved',approval_token_hash=?,approved_at=? WHERE id=?",(h,time.time(),a.get("item_id"))); c.commit()
            return json.dumps({"success":True,"item_id":a.get("item_id"),"status":"approved","approval_token":token})
        if act=="mark_published":
            if not a.get("explicit_confirmation"): return json.dumps({"error":"explicit_confirmation=true is required"})
            r=c.execute("SELECT * FROM reddit_queue WHERE id=?",(a.get("item_id"),)).fetchone()
            if not r or r["status"]!="approved": return json.dumps({"error":"item is not approved"})
            tok=str(a.get("approval_token",""))
            if not tok or not secrets.compare_digest(hashlib.sha256(tok.encode()).hexdigest(),r["approval_token_hash"] or ""): return json.dumps({"error":"invalid approval_token"})
            post=str(a.get("post_url","")).strip()
            if not post.startswith(("https://www.reddit.com/","https://reddit.com/")): return json.dumps({"error":"post_url must be a Reddit URL"})
            c.execute("UPDATE reddit_queue SET status='published',published_at=?,post_url=?,platform_post_id=? WHERE id=?",(time.time(),post,str(a.get("platform_post_id","")),a.get("item_id"))); c.commit()
            return json.dumps({"success":True,"status":"published","item_id":a.get("item_id")})
        if act=="record_metrics":
            fields=("impressions","likes","comments","shares","clicks","conversions"); vals={k:int(a[k]) for k in fields if k in a}
            if not vals:return json.dumps({"error":"at least one metric is required"})
            if not c.execute("SELECT id FROM reddit_queue WHERE id=?",(a.get("item_id"),)).fetchone():return json.dumps({"error":"item not found"})
            c.execute("UPDATE reddit_queue SET "+",".join(f"{k}=?" for k in vals)+" WHERE id=?",(*vals.values(),a.get("item_id"))); c.commit()
            return json.dumps({"success":True,"item":_row(c.execute("SELECT * FROM reddit_queue WHERE id=?",(a.get("item_id"),)).fetchone())})
        return json.dumps({"error":f"unknown action: {act}"})
    except Exception as e:return json.dumps({"error":str(e)})

registry.register(name="reddit_publisher",toolset="social_media",schema=SCHEMA,handler=_handle,emoji="")

