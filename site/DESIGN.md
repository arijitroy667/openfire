# EngBrain site — design system

The marketing site and docs are static: two HTML pages, one stylesheet, one script, one vendored animation engine. No build step, no framework, no runtime CDN dependency.

## Intent

A light, warm-neutral glass surface with near-black display type, in the spirit of modern product sites (soft blue and cream fields, floating white cards, pill controls). The chrome stays quiet so the terminal, the evidence panels, and the product video carry the weight. One accent (deep teal), one supporting hue (steel blue), generous space, and motion that clarifies state instead of performing.

## Tokens

Defined in `assets/theme.css` under `:root`.

| Role | Value | Use |
| --- | --- | --- |
| Background | `#f3f4f2` | Page base under fixed radial tints |
| Surface | `#ffffff` | Code blocks, active pills, table rows |
| Ink | `#0a0d12` | Display type, primary buttons |
| Text | `#0c1015` | Headings and body |
| Muted | `#5b6472` | Body copy, secondary labels |
| Dim | `#8b939f` | Captions, metadata, legend text |
| Accent | `#0f8f74` | Verified state, freshness, icons, focus |
| Accent deep | `#0a705c` | Accent text on light fills (AA at body size) |
| Support | `#1f7fc4` | Gradient partner, informational chips |
| Warning | `#a9680f` | Asserted evidence, drifted state |
| Danger | `#c0392f` | Stale state, failures |
| Glass fill | `rgba(255,255,255,.66)` | Card and nav surfaces |
| Hairline | `rgba(12,20,35,.09)` | Borders, dividers |

Radii: 10 / 20 / 26 / 34 / 999 px. Spacing follows a 4 px base, section padding 112 px desktop and 72 px mobile.

## Type

- **Inter Tight** for display: `letter-spacing: -0.045em` on h1, `-0.035em` on h2/h3, weight 600. The tight tracking is what keeps the large light-mode headlines from feeling soft.
- **Inter** for body and UI.
- **JetBrains Mono** for commands, IDs, status fields, eyebrows, and any value a user would copy.
- Scale: `clamp(2.6rem, 5.4vw, 4.6rem)` h1, `clamp(1.85rem, 3.2vw, 2.85rem)` h2, `1.06rem` h3, `1.04rem` lede, `0.94rem` body, `0.76rem` chips.
- Eyebrows are 0.7 rem mono, 0.2 em tracking, uppercase, preceded by a 26 px rule.

## Glass recipe

1. Translucent white fill with a vertical gradient (`.82` to `.50`) over the tinted page.
2. `backdrop-filter: blur(18-22px) saturate(160%)` for the frost.
3. A 1 px white border at 75-95% opacity to catch the light, plus a layered soft shadow (`--shadow-sm` / `--shadow-md`).
4. Where a surface needs separation from the page, add a hairline ring instead of darkening the fill.

Dark surfaces (terminal, command panel, video poster) are the deliberate contrast anchors: `#0a0d12` base, `#5fe0bd` prompt, `#ff8f8a` failure, `#f4c877` warning.

Cards add a pointer-tracked radial highlight via `--mx` / `--my`, set in `app.js` and consumed by `.card::before`.

## Motion

Motion is [Framer's `motion` engine](https://motion.dev) in its vanilla build, bundled to `assets/vendor/motion.js` (135 KB, self-contained ESM, no CDN at runtime). `app.js` imports it dynamically so a failed load falls back to a static page rather than a blank one.

| Element | Behaviour |
| --- | --- |
| Hero | Sequenced entrance: 22 px rise, 8 px blur clear, 75 ms apart |
| Section entries | 26 px rise + 9 px blur, 950 ms, `cubic-bezier(.16,1,.3,1)`, staggered by `--delay` |
| Cards | 5 px lift, brighter border, pointer spotlight |
| Hero terminal | Spring-damped perspective tilt driven by `motionValue` |
| Floating badges | 7-9 s ease-in-out drift |
| Command tabs | Indicator width/x animated to the active tab, pane crossfade |
| Staleness demo | Pane fades up 6 px on switch |
| Press feedback | `press()` scales to 0.965, springs back |
| Counters | 1.25 s ease-out integer count-up when in view |
| Orbs / headings | Scroll-linked parallax, ±24-60 px, linear |
| Progress rail | Scroll-linked `scaleX(0 → 1)` |
| Marquee | 46 s linear loop, paused on hover |
| Page changes | `@view-transition` cross-document fade, where supported |

Under `prefers-reduced-motion: reduce` the script returns before the motion layer: nothing is hidden, no scroll-linked work runs, and the tab/active states fall back to solid pill backgrounds via `html:not(.js-anim)`.

## Layout

- Container: `min(100% - 48px, 1180px)`, 32 px gutters under 720 px.
- Nav: floating glass pill, fixed, tightening its fill on scroll.
- Hero: two columns (1.02 / 0.98) collapsing at 1080 px.
- Problem: 4 → 2 → 1 columns. Agents: 3 → 2 → 1. Stats: 4 → 2 → 1.
- Docs: 236 px sticky rail + fluid article. Under 900 px the rail becomes a sticky horizontal chip row so navigation survives on phones.
- Steps: 3-column rows (number / copy / annotation), annotation drops under the copy at 1080 px.

## Component inventory

Floating nav, hero terminal with status badges, marquee, problem cards, numbered step rows, SVG architecture diagram with animated connectors, evidence panel, staleness tab demo, video frame with a real still poster and chapter strip, agent cards, command tabs with a sliding indicator and copy, stat strip, CTA panel, sticky docs rail with scroll spy, doc tables, callouts, snippet blocks.

## Accessibility

- Visible focus rings on every interactive element (`:focus-visible`, teal at 65%).
- Skip link to `#main`.
- Tabs expose `role="tab"` and `aria-selected`, and support arrow keys.
- Decorative SVG is `aria-hidden`; the architecture diagram carries a descriptive label.
- Body copy is `#3c4654` on light surfaces (≈8:1); muted `#5b6472` on `#f3f4f2` is ≈5.4:1.
- Every animation collapses under reduced motion, and the layout never depends on JS to reveal content.
