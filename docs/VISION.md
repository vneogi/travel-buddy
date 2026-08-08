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


---

---

# PART II — COMMITTED ROADMAP ADDITIONS

Reviewed and accepted 2026-08-08. These build on existing code and are
committed, unlike Part III.

## 24. Deterministic Scheduling Core (CSP), LLM as Explainer

`services/scheduler.py` becomes the authority for all schedule decisions.
The LLM never computes a schedule — it only explains one the solver produced.

Rationale: an LLM-computed schedule is 2-5s, costs per reroute, is
non-deterministic, hallucinates opening hours, and **cannot run offline.**
The Offline Vault and LLM-based rerouting are architecturally incompatible.
A deterministic solver runs on-device in milliseconds.

Cost function: maximize preference match, minus fatigue penalty, minus
transit friction, minus heat exposure. Hard constraints: locked bookings,
opening hours, party constraints.

## 25. Fatigue as a First-Class Scheduling Input

A 3-state selector (Exhausted / Hungry / Energised) feeds the solver's
fatigue penalty directly. **Manual input only — no HealthKit/Google Fit.**
Biometrics add two platform permission flows and a privacy review for a
signal the user can give in one tap.

Evidence: "Tired/sick" is the only mid-trip-change cause BOTH survey
respondents selected. Both rated over-packed schedules 2-3/5.

## 26. Show Driver Cards (Offline)

Full-screen card: venue name in large native script, nearest landmark,
GPS pin, fair-fare band. Works fully offline; lives in the Offline Vault.

Evidence: the one respondent who answered Q33 named "Money & language"
and "No internet" as the biggest struggles in an unfamiliar place.

## 27. Bookings as Hard Anchors

External reservations (flight, hotel, Klook slot) ingest as **locked nodes**,
which `scheduler.py` already treats as fixed anchors. The hotel is the daily
geographic anchor: departure, mid-day rest, and return are computed relative
to transit time from it.

Evidence: Q30 is the survey's ONLY unanimous free-text signal — both
respondents said accommodation location disrupted their daily plans.

**Ingestion is a forward-to address (`trips@...`), NOT Gmail OAuth.**
Gmail restricted-scope verification requires a third-party security
assessment ($15k-75k/yr, multi-month) and grants read access to the user's
entire inbox. A forwarded email is one message the user explicitly sent us:
~95% of the value, none of the liability. This is the permanent design, not
a stopgap.

## 28. Food & Local Intelligence — Substrate Now, Engine Later

Local food intelligence is expensive to acquire and cannot be retrofitted,
so the **data substrate ships before Laos** even though the ranking engine
does not.

Substrate (now):
- Signals can reference a dish, not just a venue (see §29)
- `venue_dish` entity: local script, romanization, English, price band,
  signature flag
- `party_member.dietary_constraints` — allergen/dietary is a safety
  feature and belongs in the party profile, not the food engine

Engine (post-Laos, needs data volume): two-tier rescue-vs-destination
ranking, trap-score weighting, dish-level recommendation.

Acquisition strategy: dish data is per-venue manual curation. Laos is the
first ingest — capture dishes on the ground as contributor #1, then extend
via user signals. Being second-best at food is acceptable; being unable to
*represent* food is not.

## 29. Generalized Signal Subject — `(entity_type, entity_id)`

**The load-bearing schema decision.** Signals currently reference venues
only, so a dish-level, neighborhood-level, or transit-leg-level fact is
not merely unsupported — it is unrepresentable, and the schema raises no
error to tell you so.

Generalizing the subject to `(entity_type, entity_id)` where
`entity_type ∈ {venue, dish, area, transit_leg}` is near-free now
(negligible production data) and requires migrating a live signal table
later. Everything in §28 depends on it.

## 30. Explicitly Deferred, With Rationale

Recorded so these are not re-proposed without new information.

| Capability | Status | Rationale |
|---|---|---|
| Isar migration | **Declined** | Working, tested `sqflite` outbox passed the airplane-mode drill. Rewriting persistence 8 weeks pre-Laos risks the one thing proven to work. |
| PostGIS / graph DB | **Deferred** | ~16 seed venues. pgvector + lat/lng index is sufficient below ~500. Adopt when venue count forces it. |
| Gmail OAuth | **Declined permanently** | Restricted-scope assessment $15k-75k/yr; full-inbox read access. Forwarding address supersedes. |
| HealthKit / Google Fit | **Declined** | Two permission flows + privacy review for a signal one tap provides. |
| Tiered SLM routing | **Deferred** | `llm_key_present=False` today. Get one model working before a 3-tier router. `light_model=gpt-4o-mini` is already the cheap tier. |
| Trap score computation | **Deferred; column now** | Needs post-Laos volume. Ship the unpopulated column so data has somewhere to land. |
| Silent Veto | **Needs design review** | "The app hid my partner's preference from me" is an unpatchable trust problem. Consent design first. |
| Street utility index | **Post-Laos** | Loses to Google Maps without differentiation; revisit with real data. |
| Flight delay cascade | **Post-Laos** | Depends on §27 anchors landing first. |


# PART III — PHASE 2+ DIRECTIONAL HYPOTHESES

**Status: NOT COMMITTED. Do not build against Part III.**

Sections 17–23 explore expanding beyond the on-trip wedge into pre-trip
planning, booking, and full-trip management. They are recorded so the
thinking is not lost — they are NOT the current roadmap.

Where Part III conflicts with §6 (on-trip wedge), **§6 wins.**

Evidence status: the expansion in Part III was drafted partly from a
user survey with **n=2 respondents, one of whom is a family member**.
Every directional claim in Part III currently rests on one or two
responses. Part III may be promoted only after the survey reaches
n>=20 with independent respondents and the claims survive.

Revisit: after the Laos field test (Oct 2026).

---

## 17. Thesis upgrade: from on-trip companion to full-trip operating system
*Added Aug 2026 after user research + competitive analysis. This reframes the product scope.*

**Before:** "AI companion that works *while you're on the trip* — the friend on the ground who
reflows your day when plans change."

**After:** "AI travel operating system that knows your ENTIRE trip context — flights, hotels,
trains, group composition, budget, dietary needs, and personal preferences — and uses that full
context to orchestrate each day in real-time."

The original thesis (§1) is correct but too narrow. A "friend on the ground" who doesn't know your
flight departs at 09:00 tomorrow, that your hotel is 40 minutes from the old town, or that your
toddler needs a nap at 14:00 — isn't actually a friend. A real local friend knows your *whole day*,
not just "which café is good." The upgrade: we are the **operating system for the trip**, not merely
the activity layer.

**Why this is defensible and not scope creep:**
1. **Data compounds faster** with full context — a ❤ on a venue PLUS "they had a 6am flight next
   day and a toddler" is an *orders of magnitude* richer training signal than a bare ❤.
2. **Switching cost becomes massive** — your full trip history + preferences + booking data +
   cross-trip memory = painful to leave.
3. **Integration depth = technical moat** — MCP connections to 20+ services, LLM extraction
   of booking confirmations, calendar sync. Months of work competitors must replicate.
4. **The "one-stop-shop" positioning** — travelers currently juggle 8-12 apps (flights, hotels,
   transit, activities, reviews, maps, translate, currency). Consolidation is the unmet desire.

**What changes:** The scheduler now reads *constraints* (flights, check-in/out, inter-city
transport) in addition to *preferences*. Recommendations factor in transit-to-airport, hotel
location as daily anchor, and available time windows — not just venue quality.

**What doesn't change:** On-trip intelligence is still the wedge. Offline-first is still core.
Behavioral signals are still the moat. We just give the engine *much more context* to be smart
with.

## 18. The Travel Calendar (Layer 4 — full trip context)

Today the engine knows: "you have 5 activity nodes today." Tomorrow it knows: "you land at 14:00,
check in at 16:00 at a hotel in District 3, have a bus at 09:00 on Day 4 from the Northern
terminal, and fly home at 15:30 on Day 9 from the international airport." That context transforms
every recommendation.

**Entities (new — SPEC-06 will formalize):**
```
trip_leg {leg_id, trip_id, leg_type, origin, destination,
          depart_at, arrive_at, carrier, reference, status}
  leg_type: flight | train | bus | ferry | car_rental | drive

trip_stay {stay_id, trip_id, accommodation_name, address,
           address_local_script, lat, lng, check_in, check_out,
           confirmation_ref, notes}
```

**Engine impact:**
- Scheduler computes AVAILABLE WINDOWS per day from legs + stays
- Departure buffer: 2h domestic flights, 3h international, 1h trains/buses
- Check-out day: morning activities must be near hotel (bags!)
- Transit day: activities only at origin AM + destination PM
- Jet-lag awareness: first day after long-haul = gentle schedule
- Last day: "morning only" with airport transit time baked in
- Hotel location = daily anchor → radius-filter activities from there

**Input methods (phased):**
- Phase 1 (Laos): manual form at trip creation (flight number, hotel name, dates)
- Phase 2: "Paste your confirmation email/text" → LLM extracts structured data
- Phase 3: Forward confirmation to `trips@travelbuddy.app` → server-side parsing
- Phase 4: MCP integration (Gmail, Google Calendar, Apple Calendar) → auto-import

**Competitive context:** TripIt does email-parsing well but has ZERO intelligence. We do
email-parsing (later) AND use the data to make *smart decisions*. That's the combined wedge.

## 19. Food & dining as a first-class moment

**Survey insight:** "Best unplanned trip moment" = finding a great authentic family restaurant
serendipitously. This is not a minor signal — it's the *highest-delight on-trip moment* our users
report. Food must be elevated from "just another venue category" to a first-class concern.

**What changes:**
- **Meal slots** are first-class itinerary nodes (breakfast / lunch / dinner / snack). The scheduler
  places them intelligently — not just activities back-to-back with no food.
- **"I'm hungry NOW" micro-intent:** location + time + party + dietary → immediate recommendation.
  This is capability #3 (invisible logistics) made concrete for the highest-frequency need.
- **Cuisine diversity:** the engine tracks what you've eaten this trip and avoids repeating the same
  cuisine type 3x in a row (unless that's the point — food tour).
- **Party-aware food:** `party_member.needs[]` drives dietary filtering (halal, vegetarian, nut
  allergy, kid-friendly with high chairs / kids menu / not-too-long waits).
- **Price-level awareness:** budget lunch near the activity, splurge dinner pre-planned. Cost is
  the #1 criterion from the survey — food recommendations must respect it.

**New signal types:** `food_loved`, `food_disliked`, `waited_too_long`, `meal_skipped`. These help
the engine pace meals correctly and learn cuisine preferences.

**Moat contribution:** food choices are high-frequency, segmented (family vs solo vs friends), and
contextual (time, location, mood, budget). They're also extremely local — "where locals eat" is
exactly the anti-tourist-trap positioning (§10 principle) that builds trust.

## 20. Currency, money & cost intelligence

**Survey validation:** "money" cited as a small thing that ruined a day. "Cost" ranked #1 criterion
by both respondents when picking a place. Yet no travel app provides *contextual* cost awareness.

**Features:**
- Per-destination **currency + exchange rate** (cached for offline use in the Vault)
- **Tipping norms** per country (no-tip / 10% / round-up / service-charge-included)
- **"Expensive or cheap for here?"** — contextual pricing. A $15 meal is cheap in Dubai, expensive
  in Laos. The engine knows this and flags when something is atypical.
- **ATM / money exchange** locations (cached in Vault for the offline moment you need cash)
- **Daily spending estimate** per itinerary (transport + meals + entries + tips). Before the day
  starts, you know roughly what it costs.
- **Budget mode:** when daily spend approaches a cap, prefer free/cheap alternatives automatically.

**Moat contribution:** cost signals compound — "this venue was perceived as overpriced by budget
travelers" vs. "great value for families." That's segmented, behavioral, and unscrapable data.

## 21. Local transport intelligence

**Survey validation:** "transit/distance affects choices" scored 5/5 (maximum). "Transport" cited
as a mid-trip change cause. Transit isn't a side concern — it's the *connective tissue* of every
on-trip decision.

**Features:**
- Per-city **transport mode map** — what exists here (metro / bus / grab / tuk-tuk / taxi / ferry /
  bicycle / walking). Many emerging-market cities have transport options that don't appear in Google
  Maps (songthaews in Thailand, marshrutkas in Central Asia, xe om in Vietnam).
- **Typical fares** per common route — so "is this driver ripping me off?" is answered before you
  get in. (Survey: "money" as day-ruiner. Overpaying for transport is a subset.)
- **Scam warnings** — common taxi/tuk-tuk scams per city, pre-cached (e.g., "Bangkok: meter off,
  'temple is closed,' flat rate = 3x"). This is anti-tourist-trap for transport.
- **"How do I get from X to Y?"** that knows LOCAL options (not just what Google shows). In many
  SE-Asian cities, the fastest/cheapest option isn't on any map app.
- **Airport transfer options** with realistic time estimates (traffic at departure hour).

**Moat contribution:** transit intelligence for non-Western cities is *extremely* hard to get right
and nearly impossible to scrape. It comes from user observations and local knowledge. A user who
reports "took the river ferry from Sathorn to Saphan Taksin in 8 mins, 20 baht — much faster than
Grab" creates a signal no database has. This is the "emerging markets + off-beaten-path" focus of
§3 made operational.

## 22. Agent memory & cross-trip intelligence (extends §11 capability #8)

**The switching-cost moat.** After 3 trips, the app *knows you*: you like slow mornings, you always
want coffee by 10am, your kid gets cranky after 3pm without a nap, you prefer street food to
restaurants, you walk fast but your partner doesn't. A new app starts from zero.

**Data model (new — needs formal BRD section):**
```
user_preference {pref_id, user_id, pref_type, value, confidence,
                 source_signals[], last_updated}
  pref_type: pace | wake_time | cuisine_preference | budget_level |
             activity_preference | transport_preference | nap_time |
             walking_speed | dietary | ...
```

**How it accumulates:**
- Signal history → LLM periodically extracts preferences ("across 12 signals, this user prefers
  outdoor activities before noon and indoor after 2pm")
- Explicit: user sets preferences directly (secondary — supplements observed behavior)
- Decay: preferences from 2+ years ago weight less (people change)
- Context-dependent: "prefers slow pace" only applies when `party_type = family`

**MCP / Agent Memory integration:**
- Agent memory stores the preference model + trip summaries as persistent context
- Each new trip starts with "what I know about this traveler" injected into the planner prompt
- Engine uses preferences as **soft weights** (never hard filters unless explicitly set — surprise
  and serendipity are valuable; over-personalisation creates a filter bubble)

**Timing:** post-Laos. Requires accumulated signal data to derive preferences from. The Laos trip
*generates* the data; cross-trip memory *consumes* it on the second trip.

## 23. Competitive positioning — why we win

The "most popular travel app in the world" requires combining three things no incumbent has:

| | TripIt | Wanderlog | AI Planners | Booking.com | **Travel Buddy** |
|---|---|---|---|---|---|
| Full trip context | ✅ | Partial | ❌ | ❌ | ✅ (building) |
| Live on-trip intelligence | ❌ | ❌ | ❌ | ❌ | ✅ (built) |
| Offline resilience | ❌ | ❌ | ❌ | ❌ | ✅ (built) |
| Behavioral data moat | ❌ | ❌ | ❌ | ❌ | ✅ (pipe built) |
| Cross-trip memory | ❌ | ❌ | ❌ | ❌ | ✅ (designed) |
| Works in emerging markets | ❌ | ❌ | ❌ | Partial | ✅ (focus) |

- **1 without 2** = TripIt (passive calendar, no intelligence)
- **2 without 1** = current Travel Buddy pre-§17 (smart but blind to constraints)
- **2 without 3** = Mindtrip/Layla (useless when you need it most)
- **1+2+3 together** = nobody. That's the gap. That's why we win.

**Updated flywheel:**
Full context → better recommendations → users do MORE in-app → more behavioral signals →
engine improves → more context shared → switching cost grows → retention compounds →
more users → more signal → ...

**What could kill us:**
- Google launches "Google Travel 2.0" with Gemini on-trip → Mitigation: they optimize for
  booking revenue; we optimize for trust. Different incentives = different product. Also: offline.
- Apple launches a travel layer in iOS → Mitigation: Apple doesn't serve emerging markets or
  Android (our segment).
- We spread too thin (10 cities, no depth) → Mitigation: DEEP > WIDE rule (§6). Retention first.
- Never enough users to compound data → Mitigation: make non-AI features (Vault, Calendar, Food)
  valuable enough standalone, pre-flywheel.

**Monthly gut-check (updated from §8):** "Which of the four did I compound this month?"
1. Traction (retained users)
2. Unique tech (demonstrably better on-trip intelligence)
3. Unique data (behavioral signals no competitor has)
4. **Full context** (integration depth that creates switching cost) ← NEW

If the answer is "I added a city" or "I polished the UI" — stop and refocus.
