# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

## Durable design decisions

- Product name is `心屿 XINYU`; `屿` means island.
- Brand lockup uses a crystal-heart mark with a heartbeat line and the subtitle `你的陪伴式桌面智能体`. Do not add a speech bubble to the mark.
- The current logo direction is the smaller, glossy translucent rose-purple glass heart from the user's latest first reference. It should feel jewel-like rather than milky or opaque. Keep the crystal still and animate only its internal heartbeat line with a short double beat followed by a quiet pause.
- Brand-lockup hierarchy: keep the heart compact, make the Chinese name slightly smaller, make `XINYU` larger with generous tracking, and set the subtitle as fine widely tracked type with a short trailing hairline.
- Primary surface is a 16:9 desktop companion UI with a warm, mature romantic mood.
- The woman and cozy room remain the visual focus; utility UI must stay light and avoid covering the character.
- Keep the character centered slightly left rather than pushed to the far left. Feature pages open as a substantial right-side glass workspace so the character remains present and the previously empty night-window area becomes useful.
- Top navigation is a centered capsule with `此刻 / 对话 / 回忆 / 计划 / 更多`.
- Dialogue, Memory, and Plan are real interactive views. Dialogue visibly continues from prior context; Memory exposes source, confidence, correction, starring, search/filter, and forgetting controls; Plan covers personal work/life items plus shared promises and companion suggestions.
- Right-side glass cards hold memories, tomorrow's checklist, and the evening note.
- Bottom control dock is a slim rounded capsule with music, one uncluttered voice/text input, and an animated mood orb. Do not add quick-prompt buttons below the input.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.
