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

## 11. In-trip capabilities & how they compound into the moat

Principle: **any single capability is copyable in a sprint; the moat is that they all
emit and consume the same accumulating behavioral data asset.** Competitors can't replay
our users' real on-trip behavior across our destinations. We prioritize the capabilities
whose *data* is proprietary and outcome-linked, not the ones that are generic glue.

| # | Capability | How it's built | Signal it feeds/consumes | Moat strength |
|---|---|---|---|---|
| 1 | Reads the group, adjusts silently | Audience model (profile + per-trip party) as recommender input | audience-segmented accept/reject | segmented data |
| 2 | Owns "what now?" — **proactive** reroute | Context watcher (weather/hours/popular_times) surfaces plan-B before pain | reroute_suggested/accepted/rejected | acceptance-rate data (capture pre-Laos) |
| 3 | Invisible logistics (food/toilet/fare) | Micro-intent handlers on location+time, ranked by fused score | acted-on micro-suggestions | table-stakes glue |
| 4 | Right *time*, not just place | Time as first-class ranking dim; scheduler slots optimal time | arrival_delta, dwell, timed crowding | outcome-linked timing |
| 5 | Protects against regret (anti-trap) | Fused quality + trap-score + user disappointment signals steer gently | not_as_described, disliked | on-brand, core |
| 6 | Reconciles split group desires | Multi-preference optimizer over party + schedule + transit | group-compromise acceptance | flagship, ~nobody has it |
| 7 | Calm in the unexpected — offline | Offline-first cache + curated "help me now" pack per city | offline usage patterns | structural (incumbents won't) |
| 8 | Remembers you across trips | Persistent per-user preference model, improves each trip | full cross-trip signal history | retention -> lock-in |

**Why it's uncopyable over time:** (a) the signals are **behavioral, not scrapable**
("which alternative a tired family accepted at 3pm in 41C" only exists via on-trip use);
(b) they're **segmented + outcome-linked** (not "4.2 stars" but "loved by daddy-kiddo trips
at golden hour when rerouted-to"); (c) cross-trip memory (#8) turns the data moat into
personal **switching cost**. Build priority concentrates in #2/#4/#5/#6/#7.

## 12. Audience-aware recommendations (extends §3)

Recommendations, pacing, food, and reroute logic MUST key off **who is travelling**, held in
two places: the persistent **user profile** (traveller type, dietary, mobility, interests) and
the **per-trip party** (this trip's companions + ages: solo/couple/friends/family-young-kids/
family-teens/multigen/daddy-kiddo/accessibility). Same person travels differently each trip.
This is both a UX differentiator (incumbents recommend generically) and the source of the
segmented behavioral data in §11.

## 13. Monetization — services & lodging (extends §9)

- **Future — local services marketplace (Phase 3+):** guides (~$100/day freelancers), private
  car+driver, and *cheaper local tours that bypass the GetYourGuide/Viator markup*. This is
  **supply** (strongest moat type) and the eventual take-rate business. Timing: after retention
  is proven; requires per-partner ops, so sequence it deliberately, one flagship city first.
- **Lodging (hotel/BnB/homestay/hostel):** capture stay experiences as a signal category; earn
  via affiliate/commission. Lower urgency than services.


## 14. The Travelogue: reciprocity that powers the flywheel

**Problem it solves:** signal capture is otherwise *extractive* — the user taps ❤ or "closed" and
gets nothing back. Weak incentive → thin signal volume → starved flywheel (§4).

**The mechanic:** captured signals (`visited_confirmed`, `dwell_minutes`, `arrival_delta`, ratings,
photos, the itinerary timeline) automatically assemble into a trip diary the user actually wants.
**It is a *rendering* of data we already capture** — near-zero marginal instrumentation cost.

**Why it's high-ROI:**
- **Reciprocal, not extractive:** users get something they value for the signals we need.
- **It answers the consent question** (DATA_MODEL §14 Q3): the ask becomes *"allow location so your
  trip diary builds itself"* — a benefit framing for exactly the permission the moat requires.
- **Retention + re-engagement:** post-trip the diary pulls users back; cross-trip it makes trip #2
  feel continuous with #1, reinforcing capability #8 (memory → switching cost).
- **More on-trip opens** (north star, §7) → more signal. Virtuous.

**Explicitly NOT a social feature.** No feed, no following, no creator economy. Sharing is optional
export, never the point. We are a utility with a memory, not a network.

**Timing:** post-Laos. It renders captured data, so as long as SPEC-01/02 capture signals during the
field trip, it can be built afterward — designed against *real* trip data.

## 15. Distribution: the tourism-board option (Phase 3+)

Competitor signal (Explurger's "NiVU", 2026): QR codes at heritage sites via an Indian state tourism
department partnership. Their *features* (on-site insights, translation, recommendations) are
commodity; the **partnership is the real asset** — it owns the physical point of intent and is
plausibly exclusive per state.

**Assessment:** a QR scan is a single-moment content lookup — no behavioral data, no cross-trip
memory, doesn't serve the "my day just broke" moment. Our wedge is untouched. But it confirms the
on-site frontier is contested, and makes India a harder market.

**Our version (later):** tourism-ministry partnerships across our footprint (Laos, Cambodia,
Uzbekistan, Kyrgyzstan, Azerbaijan) — *supply + distribution + credibility* in one deal, arguably a
better fit than the guides/drivers marketplace (§13).

**Sequencing rule:** approach **from strength, post-retention** — offering "we can show your ministry
what independent travelers actually do in your country." Pre-retention we have no leverage and B2G
cycles would consume the company. **Do not chase this in 2026.**

## 16. UX direction & the Offline Vault

UI/UX ideas are tracked in `docs/UX_BACKLOG.md`, mapped to the §11 capabilities. **Architecture is
frozen** — see UX_BACKLOG §0 for what we are deliberately NOT changing (no Isar migration, no
provider rewrite, no folder restructure, no optimistic offline reflow, no background GPS polling).

**Elevated to P1: the Offline Vault / Rescue Pack** (`docs/specs/SPEC-04-offline-vault.md`). It fills
a real gap in our thinking: we specified offline **data sync** thoroughly but never *"what does the
user need to DO when stranded?"* — no signal, lost, in a country whose script they can't read. The
native-script address card (show the taxi driver your hotel, offline) is the emblematic feature.
This is capability #7 made concrete and a **structural** advantage: online-only incumbents cannot
serve this moment.
