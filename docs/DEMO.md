# 🎬 Demo recording guide

The single highest-impact thing you can add to the README is a ~25-second screen
recording of the **capture → graph → inject** loop. This guide is the storyboard and the
mechanics so you can record it in one take.

## The money shot (what to show, in order)

| # | Beat | On screen | Duration |
|---|------|-----------|----------|
| 1 | **Hook** | A fresh ChatGPT/Claude chat. Type: *"We're using Next.js and Supabase, and let's go with Stripe for payments."* Send. | 4s |
| 2 | **Capture** | The "🧠 Saved this turn to memory" toast pops in the corner. | 2s |
| 3 | **Proof** | Open the dashboard (toolbar → Memory Audit). Show the new nodes: a Decision ("use Stripe"), Tech facts (Next.js, Supabase). | 5s |
| 4 | **Graph** | Switch to the Graph tab — nodes connected, color-coded by type. Click one to show the detail drawer (Edit / Boost / Delete). | 6s |
| 5 | **Payoff** | Open a **brand-new** chat. Before typing, the context bar shows *"N items · M tokens"*. Expand it — your stack + decision are right there. | 6s |
| 6 | **Tagline** | Type *"help me design the checkout"* — the AI already knows the stack. End. | 3s |

Total ≈ 26s. Keep it tight; no dead air.

## Setup for a clean recording

1. Start the engine: `mnemosyne-engine` (confirm the green dot on the extension icon).
2. Create a fresh workspace ("Demo") so the graph isn't cluttered.
3. Make sure **incognito is off** and **capture is on** (toolbar popup).
4. Hide bookmarks bar and personal tabs; zoom the page to ~110% so text reads on small screens.

## Recording

- **macOS:** `Cmd+Shift+5` (record a region) → export, then convert to GIF.
- **Windows:** Xbox Game Bar (`Win+G`) or [ScreenToGif](https://www.screentogif.com/) (records straight to GIF).
- **Linux:** [Peek](https://github.com/phw/peek) or `wf-recorder` + ffmpeg.

## Convert MP4 → optimized GIF (small + crisp)

```bash
ffmpeg -i demo.mp4 -vf "fps=12,scale=900:-1:flags=lanczos,palettegen" palette.png
ffmpeg -i demo.mp4 -i palette.png -lavfi "fps=12,scale=900:-1:flags=lanczos[x];[x][1:v]paletteuse" docs/demo.gif
```

Aim for **< 8 MB** so it loads fast on the README.

## Embed it

Save as `docs/demo.gif`, then add near the top of `README.md`:

```markdown
<div align="center">
  <img src="docs/demo.gif" alt="Mnemosyne in action — capture, graph, and context injection" width="720">
</div>
```

> Tip: also drop 2–3 still screenshots (graph view, dashboard, the context bar) into
> `docs/` — a static image renders even where GIFs are blocked, and looks great in a
> "Screenshots" section.
