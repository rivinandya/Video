# Video

A workspace for video and film projects, with [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills)
that cover the production pipeline from idea to finished video.

## Skills

| Skill | Use it for |
|---|---|
| [`scriptwriter`](.claude/skills/scriptwriter/SKILL.md) | Loglines, treatments, beat sheets, screenplays (Fountain format), A/V scripts for ads, explainers and social video, script notes |
| [`producer`](.claude/skills/producer/SKILL.md) | Script breakdowns, budgets, schedules, call sheets, crew/equipment lists, clearances, delivery specs |
| [`movie-maker`](.claude/skills/movie-maker/SKILL.md) | Director's vision and treatments, shot lists, coverage, camera and lighting, directing actors, post-production, building videos with ffmpeg |
| [`storyboard`](.claude/skills/storyboard/SKILL.md) | Panel-by-panel storyboards, HTML/SVG storyboard sheets, image-generation prompts, animatic timing |
| [`graphify`](.claude/skills/graphify/SKILL.md) | Turns the project folder (scripts, notes, references, images, video/audio) into a knowledge graph you can query: characters, locations, themes and how they connect. Third-party ([Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify)) |

Claude picks these up automatically when you work in this repo. You can also call one
directly, e.g. `/scriptwriter write a 30-second ad for a reusable water bottle`.

## Typical workflow

1. **scriptwriter** → idea → logline → beat sheet → script
2. **movie-maker** → director's vision → shot list
3. **storyboard** → panels / animatic
4. **producer** → breakdown → schedule → budget → call sheets
5. **movie-maker** → edit, sound, color, export

Any time: `/graphify .` builds a graph of everything in the repo; then ask things like
`/graphify query "which scenes feature Maya and the drone?"`. Output goes to `graphify-out/` (git-ignored).
Text documents, images and transcripts are processed by the AI model, so graph builds use tokens; code is parsed locally.

## Suggested layout

```
scripts/       # .fountain screenplays and A/V scripts
storyboards/   # storyboard markdown/HTML
production/    # breakdowns, schedules, budgets, shot lists, call sheets
footage/ audio/ music/ gfx/   # source media (consider git-ignoring large files)
exports/       # rendered videos
```
