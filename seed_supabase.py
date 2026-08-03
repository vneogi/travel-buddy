"""One-time seeding of the 16 Dubai venues into Supabase `venues_rag`.

Unlike seed_venues() (which fills the in-memory store on startup), the Supabase
venues table starts empty -- so after flipping to the Supabase backend, RAG
search returns nothing until this runs. Idempotent: only inserts venues whose
name isn't already present.

Requires real embeddings (TB_LITELLM_API_KEY set) and the supabase + litellm
packages installed. Run once after the schema exists:

    python seed_supabase.py
"""

import sys

from seed_data import DUBAI_VENUES
from services.embedding_service import embedding_service
from services.supabase_service import get_supabase_service


def _vector_literal(vec) -> str:
    """pgvector text form for a PostgREST insert: '[v1,v2,...]'."""
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def seed_supabase() -> int:
    svc = get_supabase_service()
    if svc is None:
        sys.exit("TB_SUPABASE_URL / TB_SUPABASE_KEY not configured -- nothing to seed.")

    if embedding_service.use_synthetic:
        sys.exit(
            "Refusing to seed: embeddings are synthetic. Set TB_LITELLM_API_KEY so "
            "venues are embedded with the same model used at query time, then retry."
        )

    existing = {
        r["name"]
        for r in (svc.client.table("venues_rag").select("name").execute().data or [])
    }
    to_insert = [v for v in DUBAI_VENUES if v.name not in existing]
    if not to_insert:
        print(f"All {len(DUBAI_VENUES)} venues already present. Nothing to do.")
        return 0

    rows = []
    for v in to_insert:
        text = f"{v.name} {v.description} {' '.join(v.vibe_tags)}"
        rows.append({
            "name": v.name,
            "description": v.description,
            "micro_location": v.micro_location,
            "lat": v.lat,
            "lng": v.lng,
            "vibe_tags": v.vibe_tags,
            "audience": v.audience,
            "category": v.category,
            "opening_hours": v.opening_hours,
            "is_sponsored": v.is_sponsored,
            "bid_weight": v.bid_weight,
            "embedding": _vector_literal(embedding_service.generate_embedding(text)),
        })

    svc.client.table("venues_rag").insert(rows).execute()
    print(f"Inserted {len(rows)} venues (skipped {len(existing)} existing).")
    return len(rows)


if __name__ == "__main__":
    seed_supabase()
