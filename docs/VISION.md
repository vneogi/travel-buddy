# Travel Buddy — Product Vision & Strategy
*Last updated: Aug 2026. Owner: Vikrant. This is the "why" and "for whom." Technical spec lives in MASTER_BRD.md.*

## 1. The one-line thesis

**Travel Buddy is the AI companion that works *while you're on the trip* — the friend on the ground who reflows your day when plans change, especially off the beaten path and offline.**

Not another pre-trip planner. The in-the-moment layer nobody has built well.

## 2. The gap we're attacking

Every major travel product — Google, Booking, Expedia, Tripadvisor, Kayak, and the AI planners (Mindtrip, Layla, Wanderlog) — optimizes for the **pre-trip and booking** moments: research, itinerary generation, reservations. That market is crowded and commoditized; a foundation model will draft a Dubai itinerary for free.

**The under-served moment is on-trip.** Once you land, plans break: you're tired, it's 44C, a venue's shut, a train's cancelled, your mood shifts. Today you're back to juggling Maps, a static itinerary doc, and group chats. Incumbents don't prioritize this because it doesn't directly drive a booking. (Validated first-hand: extended travel in China, June 2026 — excellent pre-trip tools, zero real on-trip companion.)

**Our wedge: the live, self-correcting itinerary.** Locked reservations stay fixed; everything else reflows automatically around real-world context (weather, closures, transit, fatigue, mood). This is the product, not a feature bolted onto a booking funnel.

## 3. Who we're for (and where we start)

**Primary user:** the independent / semi-independent traveler in emerging and non-Western destinations — Southeast Asia, Central Asia, the Middle East, the Caucasus. People who go off the beaten path, where connectivity is patchy and incumbent apps are weakest.

**Why this segment:**
- It's where the on-trip pain is sharpest and least served.
- It's **defensible by focus** — big players won't prioritize it until it's proven.
- We have real distribution into it: a network of trusted early testers across Azerbaijan, Singapore, the Philippines, Cambodia, Thailand, Kazakhstan, Kyrgyzstan.

**Beachhead cities:** Dubai (polished demo) + the founder's field routes (Laos/SE-Asia, Oct 2026). We go **deep in a few**, not wide. (See S6.)

## 4. The moat: a flywheel, not a feature

The state-loop is a strong product wedge, but any funded team can copy a software feature. The durable moat is a **compounding data flywheel** no competitor can copy overnight:

> Superior **on-trip** experience -> users generate **proprietary real-time local signals** (what's actually open, actually crowded, actually worth it; plus observed reroute behavior) -> the re-planning engine gets **better than anyone's** -> attracts more on-trip users -> more signal.

You can't clone an accumulated, fresh, on-the-ground data asset — you have to out-*accumulate* it, across exactly the diverse destinations we're seeding. That asset + the engine + an engaged on-trip user base is what we're ultimately building.

**What the moat is NOT:** breadth (city count), a slick UI alone, or "we use AI." Those are table stakes or easily copied.

## 5. Offline resilience is core, not a checkbox

Our users are frequently in low- or no-connectivity areas. An on-trip companion that dies without signal is useless. **Offline-first is a defining USP**, not a nice-to-have: cached itinerary + local data + maps, event queueing, sync on reconnect, graceful degradation. This is also a genuine engineering differentiator (incumbent apps are near-useless offline).

## 6. What we are explicitly NOT doing

- **Not chasing "10 cities before launch."** Breadth is a vanity metric that spreads a small team thin and produces shallow, stale data. **We chase trip-over-trip retention in one place first**, then expand as a repeatable, quality-controlled pipeline.
- **Not competing head-on with booking funnels.** We complement them; we may earn affiliate revenue from them later.
- **Not optimizing token cost as the main worry.** Infra is cheap at our scale (low hundreds/mo). The real costs are user acquisition and local ops — spend attention there. The free tier's marginal cost stays near-zero (aggressive semantic cache + light-model routing).

## 7. North-star metric

**On-trip retention** — do people reopen Travel Buddy *during* a trip, and again on the *next* trip? Every roadmap decision is judged against this. Not downloads, not city count, not MAU vanity.

## 8. The endgame

Build toward an outcome a global travel company (Trip.com, Expedia, Booking) would acquire. They buy for exactly three things — we compound at least one every month:
1. **Traction** — a fast-growing, *retained* user base in a segment they want (independent / emerging-market travelers). <- our most realistic lever.
2. **Unique tech** — a demonstrably superior on-trip re-planning engine.
3. **Unique data** — the proprietary real-time local asset the flywheel produces.

They will never pay for a pre-revenue, no-retention, shallow-multi-city GPT wrapper. Monthly gut-check: *which of the three did I compound this month?* If the answer is "I added a city," stop and refocus.

## 9. Monetization (later, plumbing already built)

Freemium. Assume no paying users for the first ~6 months — that's fine and expected.
- **Pro subscription** (reroute limits lifted, heavy model, ad-free).
- **Affiliate / booking commissions** (hotels, tours) via affiliate networks — the incumbents' actual model, reachable without per-city BD.
- Sponsored placements only where they don't erode trust (trust is the brand).

## 10. Guiding principles

- **On-trip > pre-trip.** When in doubt, improve the in-the-moment experience.
- **Deep > wide.** Retention in one city beats presence in ten.
- **Trust is the product.** We're the anti-tourist-trap local friend; never sacrifice that for a sponsor dollar.
- **Compound the moat monthly.** Traction, unique tech, or unique data — every month, one of them.
