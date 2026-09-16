---
name: guardian-social-farm
description: "Social content pipeline from research to optimise."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [social-media, content, campaigns, guardian, marketing]
    category: social-media
    related_skills: [guardian-influencer-farm, guardian-creative-farm, guardian-marketing-connection, xurl, humanizer, social-media-content-calendar]
---

# Guardian Social Farm Skill

Full social content lifecycle: research, trend detection, content ideas, hooks, scripts, creative, variations, scheduling, publishing, measurement, and optimisation. Tracks everything in the `media_farm` database for attribution and ROI.

## When to Use

- Planning and executing social media content campaigns
- Creating content across multiple platforms (X, Instagram, TikTok, LinkedIn, YouTube)
- Tracking content performance and engagement
- Optimising content based on measured results
- Connecting content to leads and revenue

## Prerequisites

- `media_farm` tool available (core Hermes tool)
- `image_generate` tool for visual content creation
- `xurl` skill installed for X/Twitter publishing
- Platform API credentials configured in `.env` as needed

## How to Run

Load this skill when the user wants to plan, create, publish, or measure social content. The pipeline is:

```
RESEARCH → TREND DETECTION → CONTENT IDEAS → HOOK → SCRIPT → CREATIVE → VARIATIONS → SCHEDULE → PUBLISH → MEASURE → OPTIMISE
```

## Quick Reference

| Phase | Tool Actions | Output |
|-------|-------------|--------|
| Research | `web_search`, `x_search` | Market/competitor insights |
| Trend Detection | `web_search`, `x_search` | Trending topics, hashtags |
| Content Ideas | Brainstorm + `media_farm(action="create_content")` | Content entries in DB |
| Hook | Write hooks per platform | First-line engagement |
| Script | Full body/caption per platform | Complete content text |
| Creative | `image_generate` + `media_farm(action="create_asset")` | Visual assets tracked |
| Variations | Generate platform-specific variants | Multiple content entries |
| Schedule | `media_farm(action="create_schedule")` | Scheduled publications |
| Publish | Platform APIs via `xurl` or `send_message` | Live content |
| Measure | `media_farm(action="record_engagement")` | Engagement data |
| Optimise | `media_farm(action="content_performance")` + analysis | Improvement insights |

## Procedure

### 1. Research Phase

1. Research the topic using `web_search` and `x_search`.
2. Identify competitor content, gaps, and opportunities.
3. Note key facts, statistics, and angles.

### 2. Trend Detection

1. Search for trending topics in the target niche using `x_search` with trending queries.
2. Use `web_search` for industry trend reports.
3. Cross-reference trends with the brand's positioning.
4. Record trending opportunities: `media_farm(action="create_content", status="trending", title=..., tags=[...])`.

### 3. Content Ideas

1. Generate 5-10 content ideas based on research and trends.
2. For each idea, create a content entry:
   ```
   media_farm(action="create_content", title=..., content_type="post", platform=..., status="idea")
   ```
3. Link ideas to campaigns if applicable: `campaign_id`.

### 4. Hook Development

1. For each content piece, write a platform-specific hook.
2. Hooks should be attention-grabbing in the first line.
3. Update content: `media_farm(action="update_content", content_id=..., hook=..., status="hook")`.

### 5. Script / Body Writing

1. Write the full body text for each platform, respecting character limits:
   - X: 280 chars (or threads for longer)
   - Instagram: 2200 chars
   - LinkedIn: 3000 chars
   - TikTok: caption overlay or description
2. Include CTAs, hashtags, and accessibility text.
3. Update: `media_farm(action="update_content", content_id=..., script=..., body=..., status="scripted")`.

### 6. Creative Asset Generation

1. Determine visual needs per platform (dimensions, style).
2. Generate images using `image_generate`:
   - X: 1200x675 (landscape), 1080x1080 (square)
   - Instagram: 1080x1080 (post), 1080x1920 (reel/story)
   - LinkedIn: 1200x627
   - TikTok: 1080x1920
3. Track assets: `media_farm(action="create_asset", name=..., asset_type="image", prompt=..., width=..., height=..., content_id=...)`.
4. Update content status: `media_farm(action="update_content", content_id=..., status="created")`.

### 7. Variations

1. Create platform-specific variations of each content piece.
2. Adapt hook, body, and creative for each platform.
3. Create variant content entries linked to the same campaign.

### 8. Scheduling

1. Determine optimal posting times per platform.
2. Create schedules: `media_farm(action="create_schedule", content_id=..., platform=..., scheduled_at=epoch)`.
3. Update content: `media_farm(action="update_content", content_id=..., status="scheduled")`.

### 9. Publishing

1. When scheduled time arrives, publish via platform tools:
   - X: `xurl post create` (via `terminal`)
   - Other platforms: `send_message` or platform-specific APIs
2. Record platform post ID: `media_farm(action="update_content", content_id=..., platform_post_id=..., published_at=epoch, status="published")`.
3. Update schedule: `media_farm(action="update_schedule", schedule_id=..., published_at=epoch, status="published")`.

### 10. Measurement

1. After publishing, collect engagement metrics periodically.
2. Record: `media_farm(action="record_engagement", content_id=..., platform=..., impressions=..., likes=..., comments=..., shares=..., clicks=...)`.
3. Update content: `media_farm(action="update_content", content_id=..., status="measuring")`.

### 11. Optimisation

1. Use `media_farm(action="content_performance", content_id=...)` to review metrics.
2. Use `media_farm(action="top_content", limit=10)` to identify best performers.
3. Analyse patterns: which hooks, formats, topics, and times perform best.
4. Create new content based on learnings.
5. Update successful content: `media_farm(action="update_content", content_id=..., status="optimised")`.

## Rules

- **No fake accounts or engagement.** All tracking is of real, organic or paid legitimate activity.
- **No spam.** Respect platform posting limits and user experience.
- **No impersonation.** Content represents the actual brand/person.
- **No copyright abuse.** Use only licensed or original creative assets.
- **No deceptive advertising.** Disclose sponsorships and ads per platform rules.
- **Platform ToS compliance.** Follow each platform's terms of service.

## Pitfalls

- Posting too frequently across platforms can trip rate limits — stagger schedules.
- Over-optimising to a single engagement metric can distort content; track conversions too.
- Publishing before review risks violating disclosure rules — always review drafts.
- Forgetting to record engagement/conversion data makes ROI untraceable — log it.

## Verification

After running the pipeline, verify:
1. `media_farm(action="list_campaigns")` shows the campaign.
2. `media_farm(action="list_content", campaign_id=...)` shows all content.
3. `media_farm(action="campaign_summary", campaign_id=...)` shows aggregated metrics.
4. Content statuses reflect actual publication state.
