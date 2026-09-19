from __future__ import annotations

import argparse
import json

from agent.guardian import workflow_engine as store
from agent.guardian.native_executor import execute_stage


def main() -> int:
    parser = argparse.ArgumentParser(description="Guardian native workflow stage runner")
    parser.add_argument("workflow_id")
    args = parser.parse_args()

    workflow = store.get_workflow(args.workflow_id)
    if not workflow:
        print(json.dumps({
            "status": "failed",
            "summary": "Guardian workflow not found.",
            "blocker": "WORKFLOW_NOT_FOUND",
        }))
        return 42

    result = execute_stage(workflow)
    step = store.get_current_step(args.workflow_id)
    if not step:
        print(json.dumps(result.payload(), ensure_ascii=False))
        return 0 if result.status != "failed" else 42

    idx = int(step["step_index"])
    now = store._now()
    store.set_step(
        workflow_id=args.workflow_id,
        step_index=idx,
        status=result.status,
        started_at=step.get("started_at") or now,
        finished_at=now,
        error=result.summary if result.status == "failed" else "",
    )
    store.add_event(
        args.workflow_id,
        result.status,
        f"Stage {step['name']} native executor: {result.summary[:500]}",
    )
    payload = json.dumps(result.payload(), ensure_ascii=False)
    with store._LOCK:
        conn = store._db()
        try:
            conn.execute(
                "UPDATE workflow_steps SET executor=?, result_json=?, result_summary=?, blocker=? "
                "WHERE workflow_id=? AND step_index=?",
                ("native", payload[:12000], result.summary[:2000], result.blocker, args.workflow_id, idx),
            )
            conn.commit()
        finally:
            conn.close()
    print(payload)
    return 42 if result.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
