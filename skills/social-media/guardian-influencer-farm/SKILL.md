---
name: guardian-influencer-farm
description: "Influencer discovery, scoring, outreach, and ROI tracking."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [influencer, creator, outreach, campaigns, guardian, marketing]
    category: social-media
    related_skills: [guardian-social-farm, guardian-marketing-connection, xurl]
---

# Guardian Influencer Farm Skill

Complete influencer marketing lifecycle: discover creators, research audiences, score relevance, match to campaigns, manage outreach, track responses, manage deliverables, and measure ROI. All tracked in the `media_farm` database.

## When to Use

- Finding and evaluating influencers for brand campaigns
- Scoring influencer relevance and audience fit
- Managing outreach and negotiation workflows
- Tracking influencer campaign deliverables and costs
- Measuring influencer ROI and attribution

## Prerequisites

- `media_farm` tool available (core Hermes tool)
- `web_search` and `x_search` for influencer discovery
- `vision_analyze` for evaluating influencer content quality

## How to Run

Load this skill when the user wants to find, evaluate, or manage influencers. The pipeline is:

```
DISCOVER → RESEARCH → SCORE → MATCH → OUTREACH → RESPONSE → CAMPAIGN → CONTENT → ATTRIBUTION → ROI
```

## Quick Reference

| Phase | Actions | Output |
|-------|---------|--------|
| Discover | `web_search`, `x_search`, social platform search | Candidate list |
| Research | `web_extract`, profile analysis | Audience/brand data |
| Score | Relevance scoring algorithm | Scored influencer entries |
| Match | Campaign alignment analysis | Matched pairs in DB |
| Outreach | `x_search` DM or email | Outreach records |
| Response | Track responses | Response timestamps |
| Campaign | Create deliverable agreements | Campaign terms |
| Content | Track produced content | Content IDs linked |
| Attribution | `media_farm(action="record_attribution")` | Attribution data |
| ROI | `media_farm(action="influencer_roi")` | ROI reports |

## Procedure

### 1. Discover

1. Define the influencer criteria:
   - Niche/industry
   - Platform(s)
   - Follower range (micro: 10K-100K, mid: 100K-500K, macro: 500K+)
   - Engagement rate threshold
   - Geographic focus
2. Search using `x_search` for relevant creators:
   - Search hashtags, keywords, and topic areas
   - Look at who creates high-quality content in the niche
3. Use `web_search` for "top [niche] influencers [year]" lists.
4. For each candidate, create a database entry:
   ```
   media_farm(action="create_influencer", handle=..., platform=..., name=..., niche=..., status="discovered")
   ```

### 2. Research

1. For each discovered influencer, gather:
   - Follower count and growth trajectory
   - Engagement metrics (likes, comments, shares per post average)
   - Content themes and style
   - Audience demographics (age, location, interests)
   - Brand partnerships history
   - Content quality assessment
2. Use `web_extract` on their profile/about pages.
3. Use `vision_analyze` on recent content to assess production quality.
4. Update influencer: `media_farm(action="update_influencer", influencer_id=..., audience_demo=..., notes=..., status="researched")`.

### 3. Score

Score each influencer on 5 dimensions (0-100 each):

| Dimension | Weight | Criteria |
|-----------|--------|----------|
| Audience Fit | 30% | Demographics match target audience |
| Engagement Quality | 25% | Real engagement rate, comment quality |
| Content Quality | 20% | Production value, creativity, consistency |
| Brand Alignment | 15% | Values, tone, previous partnerships |
| Cost Efficiency | 10% | CPE (cost per engagement) estimate |

Calculate weighted relevance score:
```
score = (audience_fit * 0.30) + (engagement_quality * 0.25) + (content_quality * 0.20) + (brand_alignment * 0.15) + (cost_efficiency * 0.10)
```

Update: `media_farm(action="update_influencer", influencer_id=..., relevance_score=..., status="scored")`.

### 4. Match

1. For each active campaign, identify top-scoring influencers.
2. Consider: niche overlap, audience demographics, platform alignment, budget.
3. Create influencer-campaign pairs:
   ```
   media_farm(action="create_influencer_campaign", influencer_id=..., campaign_id=..., status="matched")
   ```
4. Prioritise by relevance score.

### 5. Outreach

1. Draft personalised outreach messages per influencer.
2. Reference their content, explain the campaign, outline deliverables.
3. Send via appropriate channel:
   - DM via `xurl` skill for X/Twitter
   - Email for other platforms
4. Record: `media_farm(action="update_influencer_campaign", id=..., outreach_sent=epoch, status="outreach_sent")`.

### 6. Response

1. Monitor for responses.
2. When received, record: `media_farm(action="update_influencer_campaign", id=..., response_received=epoch, status="responded")`.
3. Negotiate terms if needed (deliverables, timeline, compensation).
4. Update status: `media_farm(action="update_influencer_campaign", id=..., status="active")`.

### 7. Campaign Management

1. Define deliverables per influencer:
   - Number and type of posts
   - Platform(s)
   - Timeline
   - Creative guidelines
   - Disclosure requirements (#ad, #sponsored)
2. Track deliverables in the `deliverables` field.
3. Monitor content submission and review.

### 8. Content Tracking

1. When influencer submits content, review for:
   - Brand guidelines compliance
   - Disclosure requirements
   - Quality standards
2. Create content entries: `media_farm(action="create_content", title=..., platform=..., campaign_id=..., status="approved")`.
3. Link to influencer campaign: `media_farm(action="update_influencer_campaign", id=..., content_ids=[...])`.

### 9. Attribution

1. Track conversions driven by influencer content:
   ```
   media_farm(action="record_conversion", content_id=..., campaign_id=..., influencer_id=..., conversion_type="lead", revenue=...)
   ```
2. Record attribution: `media_farm(action="record_attribution", campaign_id=..., influencer_id=..., channel=..., impressions=..., clicks=..., leads=..., conversions=..., revenue=..., cost=...)`.

### 10. ROI Calculation

1. Use `media_farm(action="influencer_roi", influencer_id=...)` for per-influencer ROI.
2. Use `media_farm(action="campaign_summary", campaign_id=...)` for campaign-level ROI.
3. Calculate key metrics:
   - **ROI%** = ((revenue - cost) / cost) * 100
   - **CPE** (cost per engagement) = total_cost / total_engagements
   - **CPL** (cost per lead) = total_cost / total_leads
   - **CPA** (cost per acquisition) = total_cost / total_conversions
4. Identify top-performing influencers for future campaigns.

## Rules

- **No fake followers or engagement.** Only evaluate real, organic audiences.
- **No impersonation.** Outreach represents the actual brand.
- **Disclosure compliance.** Ensure all sponsored content includes proper disclosures per FTC/ASA guidelines.
- **No fabricated testimonials.** Influencer content must be genuine.
- **Platform ToS compliance.** Follow each platform's rules on sponsored content.

## Pitfalls

- Matching influencers purely on follower count ignores real reach — check engagement rate.
- Forgetting disclosure on sponsored posts risks FTC/ASA violations.
- Over-indexing on one influencer concentrates risk — keep a diversified roster.
- Chasing creators with purchased followers wastes budget — verify audience authenticity.

## Verification

After running the pipeline:
1. `media_farm(action="list_influencers", status="active")` shows matched influencers.
2. `media_farm(action="list_influencer_campaigns", campaign_id=...)` shows campaign pairs.
3. `media_farm(action="influencer_roi", influencer_id=...)` shows ROI metrics.
4. `media_farm(action="campaign_summary", campaign_id=...)` shows overall campaign performance.
