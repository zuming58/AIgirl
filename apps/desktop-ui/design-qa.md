**Source visual truth**

- `C:\Users\Administrator\Desktop\微信图片_20260725215220_14333_1228.jpg`
- Source pixels: 1024 × 1024, square composition, density 1.
- The source is used as composition truth rather than a literal viewport clone because the requested product canvas is 16:9.

**Rendered implementation**

- `F:\Codex\AI girl\AIgirl-repo\apps\desktop-ui\qa-reference-layout-v4.png`
- Implementation pixels and CSS viewport: 2048 × 1056, device scale factor 1.
- URL/state: `http://127.0.0.1:4173/`, “此刻” tab.
- Combined comparison: `F:\Codex\AI girl\AIgirl-repo\apps\desktop-ui\qa-reference-comparison-v4.png`

**Findings**

- No actionable P0, P1, or P2 mismatch remains.
- Character placement: the face and upper body now sit on the full-screen horizontal center while the reference's intimate hand-on-cheek pose is preserved.
- Spacing and layout rhythm: the 16:9 adaptation keeps the left photo wall, central character, right-side card column, and bottom dock clearly separated. The notebook is visually connected to the forearms instead of floating in the foreground.
- Fonts and typography: the existing Noto Sans SC interface hierarchy remains consistent and readable; no type changes were required for this composition fix.
- Colors and visual tokens: warm amber room lighting, cool rainy-window contrast, translucent dark cards, blush accent, and gold borders remain consistent with the selected direction.
- Image quality and asset fidelity: the hero is a single coherent raster asset with no duplicated person, lamp, seam, mask edge, or ghosting. The character, notebook, mug, succulent, photo wall, lamp, and rainy window are real image content rather than code-drawn substitutes.
- Copy and content: existing Chinese interface copy is unchanged.

**Focused region comparison**

- The center/desk region was checked specifically because it contains the required relationship between the character's arms and the notebook.
- The right region was checked to confirm the mug and succulent remain visible and the darker window still supports the translucent cards.
- The left region was checked to ensure the photo wall has no duplication or blend seam.

**Comparison history**

1. Initial CSS-only double-layer composition created duplicated lamps/photo-wall content and a visible ghosted character region. Classified as P1.
2. Removed the layered mask approach and replaced it with one coherent 16:9 raster composition.
3. Re-captured at 2048 × 1056. The duplication, seam, and off-center character issues are no longer present.

**Interaction and runtime checks**

- “对话”, “回忆”, “计划”, and “此刻” navigation buttons were clicked successfully and each entered its correct active state.
- Browser console errors: none.
- Build: passed.
- Sites tests: 4/4 passed.

**Follow-up polish**

- P3: the lamp is intentionally partially covered by the right card stack, matching the layered desktop-companion feeling.
- P3: the notebook's lower area is intentionally overlapped by the bottom dock while its relationship to the character's forearms remains visible.

**Implementation checklist**

- Keep the centered hero asset wired to the main scene.
- Preserve the 16:9 crop and centered object position.
- Re-check the same composition when the future animated-avatar layer replaces the static hero.

final result: passed
