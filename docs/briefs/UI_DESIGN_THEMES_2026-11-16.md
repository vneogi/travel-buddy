<!-- Imported 2026-11-16 from the owner's draft (travel_buddy_spec_design_themes.md), converted to ASCII. Penciled as UX-57 and UX-58; overlaps are mapped in docs/UX_BACKLOG.md. Not a landed spec. -->

# SPEC -- Design Themes

**Status:** Draft for product and engineering review  
**Product:** Travel Buddy  
**Target:** Flutter mobile app (Android-first; iOS-compatible where supported)  
**Owner:** Vikrant  
**Scope:** Visual language, theme tokens, field-use ergonomics, and design principles for distinctive on-trip experiences.

## 1. Summary

Travel Buddy should feel like a **modern field instrument**: calm and editorial when planning, clear and dependable when plans change, and legible outdoors in unfamiliar places. The visual identity should support the product's core promise: a grounded, trip-scoped companion that helps a traveler decide and act when reality changes, including when connectivity is unreliable.

The theme system should retain a recognizable Travel Buddy identity across destinations. Destination accents may add atmosphere, but must not alter meaning, accessibility, trust treatments, or the perceived reliability of information. This specification establishes the design direction and the rules for exploring it; it does not authorize unsourced claims, automatic itinerary changes, or platform capabilities that need separate technical validation.

## 2. Product and design principles

1. **Field clarity over decoration.** A traveler should understand what is happening now, what comes next, and what action is safe without interpreting ornament.
2. **Warm, grounded, not generic.** Use tactile paper-and-ink warmth and restrained destination character rather than gradients, loud neon, or social-feed conventions.
3. **Trust is part of the interface.** Verified facts, generated/unconfirmed text, estimates, unknown values, and sponsored content remain visually distinct according to existing provenance and disclosure contracts.
4. **One-thumb operation.** Frequent on-trip actions should be reachable near the bottom of the screen; destructive or itinerary-changing actions still require clear review and confirmation.
5. **Designed for real light and weak connectivity.** Contrast, type size, loading, cached states, and offline explanations matter more than decorative motion.
6. **Calm feedback.** Use brief, purposeful transitions and haptics. Avoid confetti, streaks, points, and persistent attention-grabbing effects.
7. **Respect battery, privacy, and agency.** No background location polling, automatic maximum brightness, silent schedule changes, or data collection solely to support visual polish.

## 3. Theme architecture

### 3.1 Stable base identity

Keep the current warm neutral base and established teal/amber brand direction as the default starting point, subject to contrast testing against actual app screens:

- Warm off-white canvas: current `AppColors.surface` (`#FBF9F4`)
- Deep ink: current `AppColors.ink` (`#14201F`)
- Primary teal: current `AppColors.primary` (`#0E7C7B`)
- Warm amber accent: current `AppColors.accent` (`#E8A33D`)
- Muted text and dividers: current theme tokens

These are starting values from the current Flutter theme, not permission to hard-code new one-off colors. Migrate any approved changes through centralized theme tokens in `mobile/lib/theme/`.

### 3.2 Semantic tokens

Define and apply semantic roles, not destination-specific raw hex values, for:

- `canvas`, `surface`, `raisedSurface`, `primaryText`, `secondaryText`, `subtleText`
- `brandPrimary`, `brandAccent`, `interactive`, `focus`, `divider`
- `success`, `warning`, `danger`, `offline`, `locked`
- `factVerified`, `factUnconfirmed`, `estimate`, `sponsored`

Semantic status and provenance colors must retain the same meaning in every destination theme and lighting mode. Never rely on color alone; pair color with a label, icon, border, or other visible cue.

### 3.3 Destination accent palettes (proposal)

Destination accents are optional, restrained extensions of the stable base, not separate brands or full-screen recolors. Apply them only to low-risk decorative or contextual elements such as a small header accent, selected-day marker, or non-semantic illustration. Keep core buttons, status colors, booking locks, warning states, and provenance styling stable.

| Context | Proposed accent direction | Candidate values | Use carefully |
|---|---|---|---|
| Laos / Mekong corridor | Forest jade with warm teak/saffron | `#1B4332`, `#D48C46` | Small destination accents; preserve existing teal for primary actions |
| Zanzibar / Stone Town | Indian Ocean blue with clove/ochre | `#0B4F6C`, `#C2843A` | Small destination accents; ensure distinction from warning/sponsored amber |
| Dubai | Existing dusk teal and desert amber | `#0E7C7B`, `#E8A33D` | Default brand expression |

These colors are design hypotheses, not culturally validated facts. Before adoption, review with users familiar with each destination, test light/dark and color-vision accessibility, and check they do not imply unsupported regional claims.

## 4. Lighting and legibility modes

### 4.1 High-visibility mode

Provide an optional, manually controlled **High-Visibility** display setting for bright outdoor use. It should increase text/background contrast, strengthen card outlines and focus indicators, and keep critical time and direction labels clear. It must not depend on continuous ambient-light or GPS monitoring.

- Entry point: accessible display control in app settings and, if practical, a low-friction in-app toggle.
- Prefer theme-token changes and stronger contrast over arbitrary global font enlargement.
- Preserve the user's text scaling and system accessibility settings.
- Do not automatically force maximum device brightness.

### 4.2 Low-glare dark theme

Offer a system-following dark theme, with an optional low-glare treatment for night use. Candidate surfaces use deep charcoal/green rather than a full white screen or saturated amber text. Reserve warm highlights for a small number of accents; use readable neutral text for body copy.

- Follow OS brightness preference by default.
- Avoid claiming battery savings across all devices; behavior varies by display technology and settings.
- Keep warning, danger, verified/unverified, and sponsored states distinguishable and compliant in dark mode.

### 4.3 Accessibility requirements

- Meet WCAG contrast targets for text and interactive elements; verify actual token pairings in both light and dark modes.
- Support OS text scaling without clipping or horizontal overflow.
- Maintain minimum 44dp touch targets for important controls.
- Honor reduced-motion preferences and screen readers.
- Focus states, labels, and state changes must be understandable without color or haptics.

## 5. Typography, spacing, and material

- Use the existing typography and spacing system as the source of truth; tune tokens rather than inserting local styles.
- Use tabular/monospaced numerals selectively for time rails, dates, durations, and numeric status so values align and scan easily. Do not use monospaced styling for long-form body text.
- Keep primary venue names and next-action labels prominent; reduce secondary metadata before reducing legibility.
- Favor crisp dividers, restrained shadows, and consistent rounded geometry. Avoid faux paper textures that reduce contrast or make the interface feel like a scrapbook.
- Keep cards visually calm. Use elevation only to express hierarchy or an actionable state, not as decoration on every element.

## 6. Motion and haptic language

Create a small, consistent interaction vocabulary:

- **Light confirmation:** brief subtle feedback for a user-confirmed selection or day change.
- **Locked-item refusal:** a restrained, distinct response with visible text explaining why a confirmed booking cannot be moved or dismissed through that gesture.
- **Sync completion:** subtle success feedback only after the app has evidence that a queued operation synced; do not imply completion merely because a signal was queued.
- **Errors and warnings:** visible text and stable UI state remain primary. Haptics are optional reinforcement, not the only feedback.

Motion should be short, purposeful, and reversible. Respect reduced-motion settings. Avoid continuous animation, simulated "thinking" that overstates AI activity, or motion that delays access to the timeline.

## 7. Field-use interaction patterns

### 7.1 One-thumb action zone

Keep the persistent Ask entry and the most frequent contextual action within comfortable lower-screen reach where the current layout permits. Use bottom sheets for focused decisions such as swap comparison or situation selection. Do not move important navigation or trip context into a bottom-only area that disappears when scrolling.

- Primary action on a stop should be explicit and visually singular.
- Secondary actions may live in a clearly labeled overflow menu.
- Confirmations must name the actual change, especially when it affects multiple itinerary nodes.
- Preserve the current booking-lock protections and explicit traveler agency.

### 7.2 Timeline as an instrument

The itinerary should read as a connected sequence rather than a stack of unrelated cards:

- Give the active stop and next stop clear visual priority.
- Use a simple timeline rail to reinforce chronological order.
- Show transit connectors only when duration/mode comes from a defined trusted source; otherwise leave the connection neutral rather than inventing an estimate.
- Keep past days compact but accessible, and retain visible warnings only when they have an actionable destination.
- Avoid dense decorative maps or connector graphics that compete with time, place, and action.

### 7.3 Driver handoff presentation

The Driver Card should feel like a practical handoff tool: large local/verified place text, a clearly differentiated provenance state, and a high-contrast, minimal layout. A "Show to driver" mode may hide unrelated controls and emphasize the place/directions. Rotation, brightness override, Quick Settings tiles, and lock-screen exposure require device/privacy review and are not assumed by this theme specification.

## 8. Signature experiences to explore

The following concepts are design directions. Each needs a product/technical spec and data review before implementation.

### 8.1 What Now "Decision Compass"

A compact set of situation choices can make recovery feel immediate without creating a generic chatbot shell. Use a small number of clear, text-labeled options such as "Cool down", "Find shelter", "Quick break", or "Head back". The displayed choices must match deterministic intents the current engine can honor. Do not promise AC, rain conditions, distance limits, or opening status unless those attributes are present and trustworthy. Results remain structured, trip-scoped, and confirm-before-mutation.

### 8.2 Local-food "Pointing Card"

For a food stop, explore a one-tap dish card sourced from the curated dish glossary: dish name, supported local-language/phonetic text, and explicitly sourced dietary/allergen notes. The card should be high-contrast, easy to show to a vendor, and work from cached data when available. Missing translation or allergen data must be shown as unavailable, never inferred. This experience must align with dietary data governance and claim provenance.

### 8.3 Driver Card quick access

Explore a faster route from the active trip to the cached Driver Card. A notification, shortcut, or platform tile is a separate capability decision: avoid lock-screen disclosure of private trip details by default, request any required permissions clearly, and never imply a card is offline-ready until it is cached. Start with an in-app shortcut before considering OS-level surfaces.

### 8.4 Route Passport (post-trip artifact)

Explore an optional, private-by-default trip summary that turns the completed route into a restrained archival visual. Only include confirmed/recorded stops and metrics with reliable sources. Avoid "hidden gem" claims, exact distance walked, or share-ready personal data unless each is verifiable and the traveler explicitly chooses to export/share. This is a post-trip feature, not a core on-trip navigation surface.

## 9. Design system implementation plan

### Phase A -- Audit and foundations

1. Inventory existing tokens in `mobile/lib/theme/colors.dart`, `app_theme.dart`, `typography.dart`, and `spacing.dart`.
2. Audit representative screens: Home, itinerary, What Now/Ask, swap sheet, Driver Card, and offline/error states.
3. Create a theme showcase/preview for light, dark, high-visibility, provenance, warning, locked, and offline states.
4. Run contrast and text-scale checks before changing palette values.

### Phase B -- Apply the visual language

1. Centralize approved semantic tokens and remove duplicate local color literals where feasible.
2. Tune typography hierarchy, time rails, dividers, card density, and action placement on the main on-trip surfaces.
3. Add system dark mode and the user-controlled high-visibility treatment only after acceptance criteria are agreed.
4. Add haptic/motion rules to shared components and test reduced motion/accessibility behavior.

### Phase C -- Prototype signature experiences

Prototype in priority order, validating one thin slice at a time:
1. Decision Compass, backed by existing What Now intents.
2. Pointing Card, backed by curated glossary/provenance data.
3. In-app Driver Card shortcut and handoff presentation.
4. Route Passport after reliable outcome/visit evidence exists.

Do not implement all four as a redesign bundle. Keep each optional concept independently testable and removable.

## 10. Non-goals and guardrails

- No map-first shell or decorative map that crowds out the timeline.
- No social feed, DMs, points, streaks, or gamification.
- No continuous background GPS or automatic environment sensing.
- No silent itinerary reflow or mutation from a visual control.
- No unverified local-language text presented as field-verified.
- No unsourced "climate comfort", hidden-gem, local favorite, route-time, distance-walked, or venue-status claims.
- No automatic brightness override or lock-screen display of private itinerary details.
- No destination recoloring of semantic status/provenance colors.

## 11. Acceptance criteria

1. The app retains a coherent Travel Buddy identity across destinations and light/dark/high-visibility modes.
2. Primary actions, booking locks, trust/provenance labels, warnings, and offline states remain semantically consistent across themes.
3. Core on-trip screens pass contrast, large-text, screen-reader, touch-target, and reduced-motion checks.
4. The active/next itinerary hierarchy improves scanability without hiding Ask, alerts, trip context, or historical itinerary access.
5. No new theme or prototype makes unsupported claims or changes trip data without explicit confirmation.
6. High-visibility and dark modes can be changed by the traveler and do not require background location or ambient-light polling.
7. Visual changes preserve offline cache rendering and do not add avoidable network requests or battery-heavy work.
8. Each signature experience has its own implementation spec, data/provenance contract, and test plan before production implementation.

## 12. Open decisions for design review

- Should destination accents be automatic from the active trip, or should the base Travel Buddy palette remain universal with destination color limited to trip headers?
- Should High-Visibility be a manual theme toggle only, or also a quick in-trip control?
- Which one signature experience should be prototyped first: Decision Compass, Pointing Card, Driver Card quick access, or Route Passport?

These are intentionally open; the implementation should not infer answers from this draft.
