# EngBrain site

Static frontend for the product: a landing page and the documentation, sharing one light glassmorphic design system. No build step, no npm install, no bundler — but it does ship Framer's animation engine, bundled once into a local file.

```
site/
├── index.html          landing page
├── docs.html           documentation (install, MCP connection, all commands)
├── assets/
│   ├── theme.css       tokens, glass primitives, page styles
│   ├── app.js          motion layer, tabs, copy buttons, scroll spy, video
│   ├── vendor/
│   │   └── motion.js   Framer Motion's vanilla build (motion@12), self-contained ESM
│   ├── showcase-poster.jpg  still shown before play (pulled from the mp4)
│   └── favicon.svg
└── DESIGN.md           palette, type, motion, component notes
```

## Preview

Any static server works; serve `site/` (or the repository root) and open the page:

```powershell
python -m http.server 8765
```

Then open <http://127.0.0.1:8765/site/index.html>.

Opening the files directly with `file://` mostly works, but ES module imports, the video, and clipboard copy behave better over HTTP.

## Animation

Animations come from [`motion`](https://motion.dev), the vanilla build of Framer Motion; React is not involved and nothing is fetched from a CDN at runtime.

- `assets/app.js` imports `./vendor/motion.js` with a dynamic `import()`. If that fails, the page removes `.js-anim`, reveals everything, and stays fully usable.
- `inView` drives scroll reveals, `animate` with `cubic-bezier(.16,1,.3,1)` drives entrances, `scroll()` links the orbs, headings and progress rail to scroll position, `press()` handles button feedback, and `motionValue` smooths the hero tilt.
- Everything with `data-reveal` animates in; add `style="--delay:60ms"` to stagger siblings.
- `prefers-reduced-motion: reduce` skips the whole motion layer — no hidden content, no scroll listeners.

To update the engine, rebundle it (the vendor file is a single self-contained module):

```powershell
npm install motion@12 --prefix "$env:TEMP\motionbuild"
npx esbuild "$env:TEMP\motionbuild\entry.js" --bundle --format=esm --minify --target=es2020 --outfile=site/assets/vendor/motion.js
```

where `entry.js` contains `export * from "motion";`.

## Video

The tour on the landing page points at `assets/showcase.mp4`. To swap in a different cut, replace that file or edit the `<source>` element in `index.html`. Leave `preload="none"` in place so the 70 MB file is not fetched until someone presses play.

The frame stays in place before play because `assets/showcase-poster.jpg` is the frame's CSS background (and the video's `poster`). If you swap the video, re-grab a still so the poster matches, e.g.:

```powershell
ffmpeg -ss 13 -i site/assets/showcase.mp4 -frames:v 1 -vf "crop=1800:1012:60:0,scale=1600:900" -q:v 3 site/assets/showcase-poster.jpg
```

The `crop` drops the reel's own act/timer footer, so the still reads as a clean product frame.

## Editing

- Copy lives directly in the HTML; there is no templating layer.
- Colors, radii, and type scales are CSS variables at the top of `theme.css`.
- Command blocks use `<div class="snippet">` with a `data-copy` button; the script copies the text of the nested `<pre><code>`.
- Docs sections need `id` values that match the sidebar links in `.side-links`, otherwise the scroll spy and anchors break.
- Light theme only: there is no dark mode toggle, and `color-scheme: light` is declared so form controls and scrollbars match.

## Deploying

Any static host works. The repository root ships a `vercel.json` that redirects `/` to `/site/index.html` and a `.vercelignore` that keeps virtualenvs and build artifacts out of the upload:

```powershell
vercel deploy --prod
```

The deployable root is `site/` itself: `vercel deploy ./site --prod` serves `index.html` at `/`, with the video, poster and assets beside it.
