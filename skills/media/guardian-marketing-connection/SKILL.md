---
name: guardian-marketing-connection
description: "Connect media outputs to business leads and ROI."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [marketing, attribution, ROI, leads, revenue, analytics, guardian]
    category: media
    related_skills: [guardian-social-farm, guardian-influencer-farm, guardian-creative-farm, guardian-video-farm]
---

# Guardian Marketing Connection Skill

Connects media production (social, influencer, creative, video) with business outcomes: leads, sales, revenue, and ROI attribution. Determines which content produces measurable business results and enables data-driven investment decisions. All tracked in the `media_farm` database.

## When to Use

- Measuring which content drives leads and revenue
- Setting up conversion tracking across campaigns
- Building attribution models for multi-channel marketing
- Creating ROI reports for campaigns and influencers
- Optimising spend based on performance data
- Connecting media efforts to business KPIs

## Prerequisites

- `media_farm` tool available (core Hermes tool)
- At least one media farm skill (social, influencer, creative, or video) producing content
- Conversion tracking setup (UTM parameters, pixel tracking, or manual entry)

## How to Run

Load this skill when the user wants to measure business impact of media activities. This skill reads data from all other Guardian farm skills and produces attribution and ROI analysis.

## Attribution Models

| Model | How It Works | Best For |
|-------|-------------|----------|
| Last Touch | 100% credit to final touchpoint | Simple campaigns |
| First Touch | 100% credit to first touchpoint | Awareness measurement |
| Linear | Equal credit across all touchpoints | Multi-channel campaigns |
| Position-Based | 40% first, 40% last, 20% middle | Balanced view |
| Time Decay | More credit to recent touchpoints | Sales-driven campaigns |

## Quick Reference

| Action | Database Function | Purpose |
|--------|------------------|---------|
| Record conversion | `media_farm(action="record_conversion")` | Track a conversion event |
| Record attribution | `media_farm(action="record_attribution")` | Channel-level attribution |
| Campaign summary | `media_farm(action="campaign_summary")` | Campaign ROI overview |
| Content performance | `media_farm(action="content_performance")` | Per-content metrics |
| Influencer ROI | `media_farm(action="influencer_roi")` | Per-influencer ROI |
| Top content | `media_farm(action="top_content")` | Best performers |

## Procedure

### 1. Define Conversion Events

Work with the user to define what counts as a conversion:

| Event Type | Description | Typical Value |
|------------|-------------|---------------|
| lead | Form fill, email signup | Variable |
| sale | Completed purchase | Order value |
| signup | Account creation | Variable |
| demo_request | Demo booking | Variable |
| download | Resource download | Variable |
| click | CTA click (micro-conversion) | Variable |

### 2. Set Up Tracking

#### UTM Parameters

Ensure all published content uses consistent UTM parameters:
```
utm_source={platform}
utm_medium={content_type}
utm_campaign={campaign_name}
utm_content={content_id}
```

#### Manual Conversion Recording

When a conversion is identified (from CRM, analytics, or manual tracking):
```
media_farm(action="record_conversion",
    content_id=...,
    campaign_id=...,
    influencer_id=...,
    conversion_type="lead",
    value=0,
    revenue=0,
    source="organic",
    attribution_model="last_touch",
    tracking_id="external_id"
)
```

### 3. Collect Channel Metrics

Periodically gather metrics from each platform and record them:

```
media_farm(action="record_attribution",
    campaign_id=...,
    channel="x",
    impressions=50000,
    clicks=1200,
    leads=45,
    conversions=12,
    revenue=2400.00,
    cost=500.00,
    model="last_touch",
    period_start="2026-09-01",
    period_end="2026-09-07"
)
```

### 4. Campaign-Level Analysis

Use `media_farm(action="campaign_summary", campaign_id=...)` to get:
- Total content published
- Total impressions, reach, engagement
- Total conversions and revenue
- Total cost
- ROI percentage

### 5. Content-Level Analysis

Use `media_farm(action="top_content", limit=10)` to identify:
- Highest-engagement content
- Content driving the most clicks
- Content with best conversion rates

Use `media_farm(action="content_performance", content_id=...)` for detailed per-content metrics.

### 6. Influencer Attribution

Use `media_farm(action="influencer_roi", influencer_id=...)` to measure:
- Cost per influencer
- Revenue attributed to influencer content
- ROI per influencer

Compare across influencers to identify best partners.

### 7. Multi-Channel Attribution

For campaigns running across multiple channels:

1. Record attribution data per channel per period.
2. Analyse cross-channel contribution:
   - Which channels drive awareness (impressions)?
   - Which channels drive consideration (clicks, engagement)?
   - Which channels drive conversion (leads, sales)?
3. Calculate blended ROI across all channels.

### 8. ROI Reporting

Generate reports using database queries:

#### Campaign ROI Report
```python
# Get campaign summary
campaign_summary = media_farm(action="campaign_summary", campaign_id=X)

# Key metrics:
# - ROI% = ((revenue - cost) / cost) * 100
# - CPE = cost / total_engagements
# - CPL = cost / total_leads
# - CPA = cost / total_conversions
# - ROAS = revenue / cost (Return on Ad Spend)
```

#### Content ROI Report
```python
# Get top performing content
top = media_farm(action="top_content", limit=20)

# For each, get detailed performance
for item in top:
    perf = media_farm(action="content_performance", content_id=item["id"])
    # Compare impressions -> clicks -> conversions -> revenue
```

#### Influencer ROI Report
```python
# Get influencer performance
influencers = media_farm(action="list_influencers", status="active")

# For each, get ROI
for inf in influencers:
    roi = media_farm(action="influencer_roi", influencer_id=inf["id"])
    # Compare cost vs revenue across influencers
```

### 9. Optimisation Decisions

Based on attribution data, make data-driven decisions:

1. **Double down** on channels/content with highest ROI.
2. **Reduce spend** on underperforming channels.
3. **Test new approaches** for content types with high engagement but low conversion.
4. **Reallocate influencer budget** toward highest-ROI creators.
5. **Adjust content mix** based on what drives actual business outcomes.

### 10. Continuous Tracking

Set up a regular cadence (weekly or per-campaign) to:
1. Collect fresh engagement data from platforms.
2. Record new conversions from CRM/analytics.
3. Update attribution records.
4. Generate updated ROI reports.
5. Adjust strategy based on trends.

## Reporting Templates

### Weekly Performance Summary
```
Week of {date}
Campaign: {campaign_name}

Content Published: X posts
Total Impressions: X
Total Engagements: X (likes + comments + shares)
Engagement Rate: X%
Clicks: X
Leads: X
Conversions: X
Revenue: $X
Cost: $X
ROI: X%

Top Content: [list top 3]
Underperformers: [list bottom 3]
Action Items: [recommendations]
```

### Influencer Performance Summary
```
Campaign: {campaign_name}

| Influencer | Followers | Eng. Rate | Cost | Revenue | ROI |
|------------|-----------|-----------|------|---------|-----|
| @handle1   | 50K       | 4.2%      | $500 | $2,400  | 380%|
| @handle2   | 120K      | 1.8%      | $800 | $960    | 20% |

Best ROI: @handle1
Recommendation: Increase budget for @handle1, reduce for @handle2
```

## Rules

- **No fabricated metrics.** All data must come from real platform analytics or verified tracking.
- **No inflated attribution.** Only claim credit for conversions that can be reasonably attributed.
- **Transparent reporting.** Include cost and investment data alongside revenue.
- **Privacy compliance.** Respect user privacy in tracking (GDPR, CCPA).
- **No dark patterns.** Attribution should inform, not manipulate.

## Pitfalls

- Double-counting conversions across channels inflates ROI — enforce attribution rules.
- Claiming revenue from unattributed traffic overstates marketing impact.
- Ignoring user-level privacy (IDs/PII) in tracking violates GDPR/CCPA.
- Assuming channels operate independently hides true cross-channel lift.

## Verification

After running the pipeline:
1. `media_farm(action="list_campaigns", status="active")` shows campaigns with data.
2. `media_farm(action="campaign_summary", campaign_id=...)` shows ROI metrics.
3. Attribution records exist for each channel.
4. Conversion records link to specific content/influencers.
5. ROI calculations are reproducible from the raw data.
