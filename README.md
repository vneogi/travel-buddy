# Travel Buddy AI - Dubai MVP Backend

An AI-powered travel companion backend that maintains a continuous, self-correcting itinerary state loop. The system accepts real-time user interruptions, intelligently replaces affected activities using local venue knowledge (RAG), and dynamically shifts the remaining schedule without altering locked reservations.

## Architecture Overview

```
┌────────────────────────────────────────────────────────────┐
│                    FastAPI Router Layer                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │  Reroute   │ │  Semantic  │ │  Circuit   │ │ Async    │ │
│  │  Throttle  │ │  Cache     │ │  Breaker   │ │ Router   │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘ │
└────────────────────────────────────────────────────────────┘
                              │
┌────────────────────────────────────────────────────────────┐
│              LangGraph State Machine                         │
│  classify_intent -> cache_check -> venue_search ->           │
│  generate_response -> update_state -> respond                │
└────────────────────────────────────────────────────────────┘
                              │
┌────────────────────────────────────────────────────────────┐
│                  Services Layer                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │  Database  │ │  Embedding │ │  Cache     │ │ Maps     │ │
│  │  Service   │ │  Service   │ │  Service   │ │ Service  │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘ │
└────────────────────────────────────────────────────────────┘
```

## Project Structure

```
travel-buddy-mvp/
├── main.py                  # FastAPI app entry point
├── seed_data.py             # 16 curated Dubai venues (synthetic)
├── requirements.txt         # Python dependencies
├── config/
│   └── settings.py          # All configuration & guardrail levers
├── models/
│   ├── schemas.py           # Pydantic models & TypedDicts
│   └── database.py          # PostgreSQL schema (SQL)
├── services/
│   ├── database_service.py  # In-memory DB (swap for Supabase)
│   ├── embedding_service.py # Vector embedding generation
│   ├── cache_service.py     # Semantic cache (Lever 2)
│   └── maps_service.py      # Google Maps mock (transit/places)
├── agents/
│   ├── state_machine.py     # LangGraph state machine
│   └── router_agent.py      # Intent classifier & model router
└── routers/
    └── trip_router.py       # FastAPI endpoints + guardrails
```

## 5 Cost-Control Guardrails (from BRD)

| Lever | Name | Implementation |
|-------|------|----------------|
| 1 | Reroute Throttle | Free users: 5 reroutes/day. Pro: 50/day |
| 2 | Semantic Cache | Cosine similarity > 0.92 = cached response (zero LLM cost) |
| 3 | Circuit Breaker | Max 3 internal graph transitions before fallback |
| 4 | Asymmetric Router | Light model for info queries, heavy for restructuring |
| 5 | Ad-Injection Boost | Sponsored venues get score boost in RAG results |

## Quick Start (MVP with Synthetic Data)

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python main.py
# OR
uvicorn main:app --reload --port 8000

# Open API docs
open http://localhost:8000/docs
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | Health check + system stats |
| POST | `/api/v1/trip/create` | Create new Dubai itinerary |
| GET | `/api/v1/trip/{trip_id}` | Get trip state |
| POST | `/api/v1/trip/event` | Process user event (main endpoint) |
| GET | `/api/v1/user/{user_id}/status` | User tier & reroute info |
| POST | `/api/v1/user/{user_id}/upgrade` | Upgrade to Pro |
| GET | `/api/v1/venues/search` | Search venues via RAG |
| GET | `/api/v1/stats` | System analytics |

## Example: Process a Trip Event

```json
POST /api/v1/trip/event
{
  "user_id": "user-123",
  "trip_id": "<trip_id_from_create>",
  "event_type": "swap_activity",
  "message": "I'm too tired for the gallery walk, find me a quiet cafe with great interiors",
  "target_node_id": "<node_id_to_replace>",
  "preferences": {
    "vibe_tags": ["leisurely", "premium_interiors"],
    "mood": "relaxed"
  }
}
```

## Production Roadmap

1. **Phase 1 (Current)**: Synthetic MVP - all services in-memory
2. **Phase 2**: Connect Supabase (PostgreSQL + pgvector)
3. **Phase 3**: Integrate LiteLLM with real models (GPT-4o + Gemini Flash)
4. **Phase 4**: Real Google Maps/Places API integration
5. **Phase 5**: Mobile app (Flutter/React Native) + Play Store deployment
6. **Phase 6**: RAG pipeline with real venue ingestion from TimeOut, What's On
