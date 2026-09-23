---
name: guardian-reddit-publisher
description: "Human-in-the-loop Reddit research, drafting, approval, publishing records, and measurement."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [Reddit, Social Media, Research, Approval, Publishing, Measurement]
    category: social-media
    related_skills: [reddit-reading, guardian-social-farm]
---

# Guardian Reddit Publisher

Research and drafting can run automatically. Posting cannot.

Pipeline:
RESEARCH -> RULE CHECK -> DRAFT -> APPROVAL QUEUE -> EXPLICIT USER APPROVAL -> HUMAN-ACTION PUBLISH -> MEASURE

Rules:
- Never post, comment, vote, message, or create accounts unattended.
- Never evade Reddit bot/AI detection or anti-spam controls.
- Never use fake personas, fabricated personal experiences, or misleading claims.
- Respect subreddit rules and self-promotion limits.
- Do not duplicate the same draft on the same thread.
- Record source URLs and rule notes for every queued item.
- Do not claim traffic, engagement, or revenue without measured data.

Use reddit_publisher actions create_draft, list_queue, get_item, approve, mark_published, and record_metrics.
The tool intentionally has no unattended Reddit posting action.

