import json

def call(action,**kw):
    from tools.reddit_publisher import _handle
    return json.loads(_handle({"action":action,**kw}))

def test_approval_and_publish(tmp_path,monkeypatch):
    monkeypatch.setenv("HERMES_HOME",str(tmp_path))
    r=call("create_draft",subreddit="ExampleSub",thread_url="https://www.reddit.com/r/ExampleSub/comments/abc/topic/",draft="Useful answer",rule_notes="Respect rules")
    i=r["item"]["id"]; a=call("approve",item_id=i); token=a["approval_token"]
    blocked=call("mark_published",item_id=i,approval_token=token,explicit_confirmation=False,post_url="https://www.reddit.com/r/ExampleSub/comments/def/reply/")
    assert "error" in blocked
    done=call("mark_published",item_id=i,approval_token=token,explicit_confirmation=True,post_url="https://www.reddit.com/r/ExampleSub/comments/def/reply/",platform_post_id="def")
    assert done["status"]=="published"

def test_duplicate_and_metrics(tmp_path,monkeypatch):
    monkeypatch.setenv("HERMES_HOME",str(tmp_path))
    k=dict(subreddit="ExampleSub",thread_url="https://www.reddit.com/r/ExampleSub/comments/abc/topic/",draft="Same")
    one=call("create_draft",**k); two=call("create_draft",**k)
    assert two["duplicate"] is True and two["item"]["id"]==one["item"]["id"]
    m=call("record_metrics",item_id=one["item"]["id"],clicks=3,conversions=1)
    assert m["item"]["clicks"]==3 and m["item"]["conversions"]==1

