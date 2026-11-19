# TP-Link ATP Automation Platform — User Journey Storyboard & Emotional Arc

> **Purpose**: Document the end-to-end QA engineer workflow for the ATP dashboard. This serves as the design rationale for UI decisions and the acceptance criteria for future iterations.

---

## Core Flow — 7 Steps

| Step | Time Window | User Action | System Response | Key UI Elements |
|------|-------------|-------------|-----------------|-----------------|
| **1. Land** | 0–5 s | Opens `http://host:5000` | Dashboard renders: topology hero, network status pill, quick-start CTA buttons | Topbar (brand, nav tabs, status pill, theme switcher, reboot btn), Network Topology card, Overview stats, Telemetry card |
| **2. Orient** | 5–15 s | Scans topology hero | Visual flow: Internet → Main Router → Clients — understands system boundary at a glance | Topology card with animated connector lines, status dots (red=Internet, cyan=Router, muted=Clients), client count |
| **3. Select** | 15–30 s | Clicks "Stage 1" or "Run All" | Toast confirmation → progress bar appears → buttons enter loading state | Primary CTA buttons (Run All / Stage 1–5), toast at top-center, progress bar in Overview card |
| **4. Wait/Monitor** | 30 s – 5 min | Watches progress | 3 s polling updates: progress bar advances, status chips flip PENDING→RUNNING→PASS/FAIL, running count badge | Progress bar (gradient), % label, running cases counter, table status badges (live), client table row highlights |
| **5. Inspect (Pass)** | On demand | Clicks screenshot thumbnail | Lightbox opens with full-size image, red-box highlights (if configured), "Open in New Tab" works | Lightbox modal, image panel, caption, actions (Open in New Tab, Close), ESC/click-backdrop to close |
| **6. Inspect (Fail)** | On demand | Clicks "Retry" on failed case | Single case re-runs → returns to monitoring view | Destructive-style "Retry" button per row, toast "Running X.Y", polling resumes |
| **7. Archive** | Post-run | Navigates to Reports tab | Historical runs grid with thumbnails, file counts, summary metadata | Reports tab, card grid, screenshot thumbnails (lazy-loaded), lightbox integration |

---

## Emotional Arc — Per Step

| Step | User Does | User Feels | Plan Supports |
|------|-----------|------------|---------------|
| **1. Land** | Opens dashboard | **Oriented, confident** — immediate clarity on system health | Topology hero + status pill (green=online) gives instant "systems nominal" signal |
| **2. Orient** | Scans topology | **In control** — mental model formed in <10 s | Visual flow diagram (Internet → Router → Clients) maps to physical architecture |
| **3. Select** | Clicks Run | **Empowered** — action is obvious, feedback instant | Clear CTA hierarchy (primary brand gradient), toast confirms submission, buttons disable to prevent double-submit |
| **4. Wait/Monitor** | Watches progress | **Informed, not anxious** — live data prevents "is it stuck?" | 3 s polling, progress bar % + running count, status chips update in-place, row hover reveals thumbnails |
| **5. Inspect (Pass)** | Views evidence | **Validated** — sees exactly what passed | Lightbox with red-box highlights (case_highlights config), full-resolution "Open in New Tab" for deep dive |
| **6. Inspect (Fail)** | Retries failure | **Agency** — one click, no context switch | Inline "Retry" button on FAIL rows, same polling loop, no modal forms |
| **7. Archive** | Reviews history | **Trust** — accumulated evidence over time | Reports grid with thumbnails, file counts, sortable by date, lightbox reuse |

---

## UI/UX Design Decisions Mapped to Journey

| Journey Need | Design Solution | Location in `index.html` |
|--------------|-----------------|--------------------------|
| **Zero-flicker theme** | Inline `<script>` before `<body>` paints — reads localStorage, applies `data-theme` | Lines 499–529 |
| **Instant orientation** | Topology hero card spans full width (`.bento-1`), animated connector lines, status dots | Lines 573–599 |
| **Clear CTA hierarchy** | Primary buttons use brand gradient + shadow; ghost/destructive variants for secondary actions | Lines 297–349 |
| **Live feedback without anxiety** | 3 s `setInterval(load, 3000)` + toast + progress bar + running count badge | Lines 879–886, 1098–1099 |
| **Evidence-first inspection** | Lightbox modal (z-index 60), backdrop blur, ESC/click-outside close, "Open in New Tab" | Lines 447–470, 688–701, 1051–1095 |
| **Fail → Retry in one click** | Inline "Retry" button (`.btn.destructive`) on FAIL rows, reuses `runOne()` | Lines 908, 965 |
| **Historical trust** | Reports tab renders card grid with lazy-loaded thumbs, same lightbox | Lines 981–996, 819 |
| **Accessibility** | `role`, `aria-*` attributes, focus-visible rings, semantic HTML, color contrast | Throughout (e.g., lines 202, 224, 315, 493–495) |

---

## Technical Constraints Preserved

- **Flask API contracts unchanged**: `/api/state`, `/api/config`, `/api/run`, `/screenshot/<p>`, `/api/reports`
- **CASE_META** local metadata aligned with `atp_web.py` CASES dict (lines 753–778)
- **Polling interval**: 3 s (`setInterval(load, 3000)`) — balances live feel vs. server load
- **Theme persistence**: `localStorage` key `atp-theme` + `matchMedia` system listener
- **No external icon deps**: All icons are inline Lucide-style SVGs

---

## Future Enhancement Opportunities

| Area | Idea | Journey Step |
|------|------|--------------|
| **Progress granularity** | Per-stage progress rings (not just global %) | 4 |
| **Failure diagnostics** | Inline error snippet / log tail on FAIL row hover | 6 |
| **Keyboard shortcuts** | `R` = Run All, `1–5` = Stage, `Esc` = close lightbox | 3, 5 |
| **WebSocket push** | Replace 3 s polling with server-sent events for instant updates | 4 |
| **Report comparison** | Side-by-side diff of two historical runs | 7 |
| **Export journey** | "Share run" → generates signed URL with screenshots | 7 |

---

## Acceptance Checklist (for QA)

- [ ] **Land**: Page loads <2 s on LAN; status pill shows "Online" within 1 s
- [ ] **Orient**: Topology hero renders without layout shift; client count matches CASE_META keys
- [ ] **Select**: Clicking "Run All" shows toast within 200 ms; buttons enter loading state
- [ ] **Monitor**: Progress bar updates every 3 s; no duplicate toasts; running count accurate
- [ ] **Inspect Pass**: Lightbox opens <300 ms; image loads; red boxes visible if `case_highlights` configured; "Open in New Tab" opens full-res image
- [ ] **Inspect Fail**: "Retry" button appears only on FAIL; click triggers single-case run; returns to monitoring
- [ ] **Archive**: Reports tab lists all `reports/` subdirectories; thumbnails lazy-load; lightbox works
- [ ] **Theme**: Light/Dark/System toggle persists across reloads; no flash on initial load
- [ ] **A11y**: Tab order logical; focus rings visible; screen reader announces status changes (aria-live)
- [ ] **Mobile**: Topbar collapses tabs; cards stack; lightbox fits viewport; touch targets ≥44 px

---

*Document version: 1.0*  
*Author: Design Implementation Specialist*  
*Linked files: `templates/index.html` (inline comments), `atp_web.py` (Flask backend)*