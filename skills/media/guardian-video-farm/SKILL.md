---
name: guardian-video-farm
description: "Video and media production pipeline from brief to measure."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [video, media, production, storyboard, guardian, marketing]
    category: media
    related_skills: [guardian-social-farm, guardian-creative-farm, guardian-marketing-connection, kanban-video-orchestrator, manim-video, hyperframes]
---

# Guardian Video Farm Skill

Video and media production pipeline: brief, script, storyboard, asset gathering, video generation, variations, export, publishing, and measurement. Uses Hermes-native tools (FFmpeg, image_generate, video_generate) and does not depend on AGPL-licensed external systems. All tracked in the `media_farm` database.

## When to Use

- Producing video content for social media campaigns
- Creating product demo or explainer videos
- Generating video ads and promotional content
- Managing video production workflows
- Tracking video performance and ROI

## Prerequisites

- `media_farm` tool available (core Hermes tool)
- `image_generate` tool for storyboard frames and thumbnails
- `video_generate` tool for AI video generation (if configured)
- `terminal` tool for FFmpeg operations
- FFmpeg installed on the system (for compositing, encoding, export)

## How to Run

Load this skill when the user needs video production. The pipeline is:

```
BRIEF → SCRIPT → STORYBOARD → ASSETS → VIDEO → VARIATIONS → EXPORT → PUBLISH → MEASURE
```

## Quick Reference

| Phase | Actions | Output |
|-------|---------|--------|
| Brief | Requirements gathering | Video brief |
| Script | Narrative structure, dialogue | Script document |
| Storyboard | Scene-by-scene visual plan | Storyboard frames |
| Assets | Gather/generate visual elements | Raw assets |
| Video | Generate or composite video | Draft video |
| Variations | Create platform/length variants | Multiple versions |
| Export | Encode for target platforms | Final files |
| Publish | Upload and distribute | Live video |
| Measure | Track views, engagement, conversions | Performance data |

## Video Formats by Platform

| Platform | Aspect Ratio | Resolution | Max Length | Format |
|----------|-------------|------------|------------|--------|
| TikTok | 9:16 | 1080x1920 | 10 min | MP4 |
| Instagram Reels | 9:16 | 1080x1920 | 90 sec | MP4 |
| Instagram Feed | 1:1 or 4:5 | 1080x1080 / 1080x1350 | 60 sec | MP4 |
| YouTube Shorts | 9:16 | 1080x1920 | 60 sec | MP4 |
| YouTube Long | 16:9 | 1920x1080 | 12 hours | MP4 |
| X (Twitter) | 16:9 or 1:1 | 1920x1080 / 1080x1080 | 140 sec | MP4 |
| LinkedIn | 16:9 or 1:1 | 1920x1080 / 1080x1080 | 10 min | MP4 |
| Facebook | 16:9 or 9:16 | 1920x1080 | 240 min | MP4 |

## Procedure

### 1. Brief

Gather video requirements:

1. **Objective**: Awareness, education, conversion, entertainment?
2. **Platform(s)**: Where will this be published?
3. **Duration**: Target length (15s, 30s, 60s, 3min, 10min?)
4. **Style**: Live-action look, motion graphics, animation, AI-generated?
5. **Audience**: Who is this for?
6. **Message**: Core message or story.
7. **Brand**: Guidelines, logo, colors, fonts.
8. **Budget**: Affects approach (AI gen vs composite vs full production).
9. **Deadline**: Timeline constraints.
10. **Call to Action**: What should viewers do after watching?

Create a video pipeline entry:
```
media_farm(action="create_video", title=..., brief="[detailed brief]", status="brief")
```

### 2. Script

1. Write the script with:
   - **Scene headings** (INT./EXT., location, time)
   - **Visual description** (what the viewer sees)
   - **Audio** (narration, dialogue, music notes)
   - **Duration** per scene
   - **Text overlays** (if any)
2. Match script to target duration (~150 words/minute for narration).
3. Include hooks in the first 3 seconds.
4. Update: `media_farm(action="update_video", video_id=..., script=..., status="script")`.

### 3. Storyboard

Create a scene-by-scene visual plan:

1. For each scene, define:
   - **Frame description**: What the viewer sees
   - **Camera angle/movement**: Static, pan, zoom, etc.
   - **Text overlay**: On-screen text
   - **Duration**: Seconds for this scene
   - **Transition**: Cut, fade, wipe, etc.
2. Generate storyboard frames using `image_generate`:
   ```
   image_generate(prompt="storyboard frame: [scene description], cinematic style, wide shot", size="landscape_16_9")
   ```
3. Save storyboard as structured data:
   ```
   media_farm(action="update_video", video_id=..., storyboard={"scenes": [{"frame": 1, "description": "...", "duration": 3, "image_url": "..."}]}, status="storyboard")
   ```

### 4. Assets

Gather or generate all visual and audio assets:

1. **Visual assets**:
   - Generate scenes via `image_generate`
   - Generate video clips via `video_generate` (if configured)
   - Source stock footage if needed (via `web_search` for free stock sites)
   - Create motion graphics elements (text animations, transitions)
2. **Audio assets**:
   - Generate or source background music
   - Generate voiceover via `text_to_speech` if needed
   - Source sound effects
3. Track all assets:
   ```
   media_farm(action="create_asset", name=..., asset_type="video", prompt=..., campaign_id=..., video_id=...)
   ```
4. Update: `media_farm(action="update_video", video_id=..., assets=[...], status="assets")`.

### 5. Video Generation / Composition

#### Path A: AI Video Generation (for short-form)

Use `video_generate` for AI-generated video clips:
```
video_generate(prompt="[scene description]", duration=5, aspect_ratio="9:16")
```

#### Path B: FFmpeg Composition (for assembled videos)

1. Assemble storyboard frames into video sequences:
   ```bash
   # Create video from image sequence
   ffmpeg -framerate 30 -i frame_%03d.png -c:v libx264 -pix_fmt yuv420p -vf "scale=1920:1080" output.mp4
   ```
2. Add Ken Burns effect (pan/zoom) to still images:
   ```bash
   ffmpeg -loop 1 -i image.png -vf "zoompan=z='min(zoom+0.001,1.5)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=150:s=1920x1080:fps=30" -t 5 -c:v libx264 output.mp4
   ```
3. Composite scenes with transitions:
   ```bash
   ffmpeg -i scene1.mp4 -i scene2.mp4 -filter_complex "[0][1]xfade=transition=fade:duration=1:offset=4" output.mp4
   ```
4. Add text overlays:
   ```bash
   ffmpeg -i input.mp4 -vf "drawtext=text='Your Text':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2" output.mp4
   ```
5. Add audio track:
   ```bash
   ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -shortest output.mp4
   ```

Update: `media_farm(action="update_video", video_id=..., video_path="output.mp4", status="review")`.

### 6. Variations

Create platform-specific variants:

1. **Aspect ratio variants**: Reframe for different platforms.
   ```bash
   # 16:9 to 9:16 (TikTok/Reels) - crop center
   ffmpeg -i source.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920" tiktok.mp4
   # 16:9 to 1:1 (Instagram) - crop center
   ffmpeg -i source.mp4 -vf "crop=ih:ih,scale=1080:1080" instagram.mp4
   ```
2. **Duration variants**: 15s cutdown, 30s, 60s, full length.
3. **Style variants**: Different color grades, text overlays, CTAs.
4. Track each variation:
   ```
   media_farm(action="update_video", video_id=..., variations=[{"platform": "tiktok", "path": "tiktok.mp4", "aspect": "9:16"}, ...])
   ```

### 7. Export

1. Encode for each target platform with optimal settings:
   ```bash
   # H.264 for broad compatibility
   ffmpeg -i input.mp4 -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k final.mp4
   ```
2. Generate thumbnail from video:
   ```bash
   ffmpeg -i video.mp4 -ss 00:00:03 -vframes 1 thumbnail.jpg
   ```
3. Track export:
   ```
   media_farm(action="update_video", video_id=..., export_path="final.mp4", status="exported")
   ```

### 8. Publishing

1. Upload to target platforms:
   - YouTube: via YouTube API or browser upload
   - TikTok: via TikTok API or browser upload
   - Instagram: via Instagram Graph API
   - X: via `xurl post create --media` for video
   - LinkedIn: via LinkedIn API
2. Add metadata: titles, descriptions, tags, hashtags, thumbnails.
3. Create content entries: `media_farm(action="create_content", title=..., content_type="video", platform=..., status="published")`.
4. Link to video pipeline: `media_farm(action="update_video", video_id=..., content_id=..., status="published")`.

### 9. Measurement

1. After publishing, collect metrics:
   ```
   media_farm(action="record_engagement", content_id=..., platform=..., video_views=..., watch_time_secs=..., likes=..., comments=..., shares=...)
   ```
2. Track conversions: `media_farm(action="record_conversion", content_id=..., campaign_id=..., conversion_type="lead", revenue=...)`.
3. Use `media_farm(action="content_performance", content_id=...)` for per-video analysis.
4. Use `media_farm(action="campaign_summary", campaign_id=...)` for campaign-level video performance.

## Quality Checklist

Before publishing, verify:
- [ ] Audio levels balanced (-14 LUFS for social)
- [ ] No dead frames or black screens
- [ ] Text is readable at mobile resolution
- [ ] Captions/subtitles included (accessibility)
- [ ] Thumbnail is compelling
- [ ] CTAs are clear
- [ ] Platform specs match (resolution, duration, format)
- [ ] Brand guidelines followed
- [ ] No copyrighted music/content without license

## Rules

- **No copyright abuse.** Use only licensed or original music, footage, and graphics.
- **No deceptive content.** Video must represent reality accurately.
- **No fabricated testimonials.** Never create fake reviews or endorsements.
- **Accessibility.** Include captions/subtitles for all spoken content.
- **Platform compliance.** Follow each platform's content policies.

## Pitfalls

- Mismatched resolution/duration specs cause platform rejects — verify per-platform formats.
- Background audio without a license risks copyright strikes.
- Skipping captions hurts accessibility and reach.
- Rendering at incorrect aspect ratios makes thumbnails appear cropped.

## Verification

After running the pipeline:
1. `media_farm(action="get_video", video_id=...)` shows full pipeline status.
2. `media_farm(action="list_assets", campaign_id=...)` shows all video assets.
3. Video files exist at the exported paths.
4. `media_farm(action="content_performance", content_id=...)` shows view/engagement data.
