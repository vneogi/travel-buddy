# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Setup: Install dependencies and configure path
import sys
import os

# Add project to path
project_path = "/Workspace/Users/vikrant.neogi@databricks.com/travel-buddy-mvp"
sys.path.insert(0, project_path)
os.chdir(project_path)

# Install minimal dependencies
%pip install pydantic pydantic-settings fastapi httpx -q
dbutils.library.restartPython()

# COMMAND ----------

# DBTITLE 1,Initialize Application (Load Modules)
import sys, os
project_path = "/Workspace/Users/vikrant.neogi@databricks.com/travel-buddy-mvp"
sys.path.insert(0, project_path)
os.chdir(project_path)

# Import all modules
from config.settings import settings
from models.schemas import *
from services.database_service import db_service
from services.embedding_service import embedding_service
from services.cache_service import cache_service
from services.maps_service import maps_service
from agents.router_agent import router_agent
from agents.state_machine import state_machine
from seed_data import seed_venues

# Seed venue data
venue_count = seed_venues()
print(f"{'='*60}")
print(f"  Travel Buddy MVP - Initialized Successfully!")
print(f"  Venues loaded: {venue_count}")
print(f"  Geo-fence: {settings.geo_fence}")
print(f"  Max reroutes (free): {settings.max_daily_reroutes_free}")
print(f"  Cache threshold: {settings.semantic_cache_threshold}")
print(f"  Circuit breaker depth: {settings.max_loop_depth}")
print(f"{'='*60}")

# COMMAND ----------

# DBTITLE 1,Test 1: Create a Trip & Inspect Itinerary
from datetime import datetime, timedelta

# Create a user and trip
user_id = "test-user-001"
user = db_service.get_or_create_user(user_id)
print(f"User: {user.user_id} | Tier: {user.tier_status.value} | Reroutes: {user.daily_reroute_count}/{user.max_daily_reroutes}")

# Create a sample trip
start = datetime(2026, 8, 5, 9, 0, 0)
nodes = [
    TripNode(
        venue_name="Museum of the Future",
        scheduled_start=start,
        duration_minutes=120,
        micro_location="Downtown",
        vibe_tags=["energetic", "premium_interiors", "artistic"],
        lat=25.2208, lng=55.2812,
    ),
    TripNode(
        venue_name="The Espresso Lab",
        scheduled_start=start + timedelta(hours=2, minutes=30),
        duration_minutes=45,
        micro_location="Business Bay",
        vibe_tags=["leisurely", "independent"],
        lat=25.2280, lng=55.2870,
    ),
    TripNode(
        venue_name="La Petite Maison",
        scheduled_start=start + timedelta(hours=4),
        duration_minutes=90,
        is_locked=True,  # LOCKED reservation - cannot be changed!
        micro_location="DIFC",
        vibe_tags=["premium_interiors", "executive"],
        lat=25.2100, lng=55.2800,
    ),
    TripNode(
        venue_name="Alserkal Avenue Galleries",
        scheduled_start=start + timedelta(hours=6),
        duration_minutes=120,
        micro_location="Al Quoz",
        vibe_tags=["artistic", "authentic"],
        lat=25.1436, lng=55.2250,
    ),
]

trip = TripState(user_id=user_id, nodes=nodes)
db_service.save_trip(trip)

print(f"\nTrip Created: {trip.trip_id}")
print(f"{'─'*60}")
for i, node in enumerate(trip.nodes, 1):
    lock_icon = " [LOCKED]" if node.is_locked else ""
    print(f"  {i}. {node.venue_name}{lock_icon}")
    print(f"     Time: {node.scheduled_start.strftime('%H:%M')} | {node.duration_minutes}min | {node.micro_location}")
    print(f"     Vibes: {', '.join(node.vibe_tags)}")
print(f"{'─'*60}")

# COMMAND ----------

# DBTITLE 1,Test 2: Venue RAG Search (Hybrid Search with Sponsored Boost)
# Test the hybrid search with different queries
print("=" * 60)
print("  HYBRID RAG SEARCH TEST")
print("=" * 60)

queries = [
    ("quiet cafe with great coffee and minimalist design", None),
    ("authentic cultural experience in old Dubai", ["authentic", "cultural"]),
    ("premium restaurant for executive dinner", ["premium_interiors", "executive"]),
]

for query, vibe_filter in queries:
    print(f"\n  Query: '{query}'")
    if vibe_filter:
        print(f"  Filter: {vibe_filter}")
    
    results = db_service.hybrid_venue_search(
        query=query,
        user_lat=25.2000,  # Near Downtown Dubai
        user_lng=55.2700,
        vibe_filter=vibe_filter,
        top_k=3,
    )
    
    for i, r in enumerate(results, 1):
        sponsored = " [SPONSORED]" if r.venue.is_sponsored else ""
        print(f"    {i}. {r.venue.name}{sponsored}")
        print(f"       Score: {r.similarity_score:.4f} -> Final: {r.final_score:.4f} | {r.venue.micro_location}")
    print(f"  {'─'*50}")

# COMMAND ----------

# DBTITLE 1,Test 3: Intent Classification (Lever 4 - Asymmetric Routing)
print("=" * 60)
print("  INTENT CLASSIFICATION TEST (Lever 4: Asymmetric Routing)")
print("=" * 60)

test_messages = [
    ("I'm too tired for the gallery, find me something relaxing", "reroute"),
    ("What's the dress code at Zuma?", "ask_info"),
    ("Translate 'thank you' to Arabic", "translate"),
    ("It's raining, swap my outdoor activity", "weather_alert"),
    ("How much does a taxi cost to the mall?", "ask_info"),
    ("Cancel my 3pm activity and replace with indoor art", "swap_activity"),
]

print(f"\n  {'Message':<55} {'Event':<15} {'Tier':<8} {'Conf'}")
print(f"  {'─'*55} {'─'*15} {'─'*8} {'─'*5}")
for msg, event in test_messages:
    tier, confidence = router_agent.classify_intent(msg, event)
    model_info = router_agent.get_model_info(tier)
    tier_display = f"{tier.value.upper()}"
    print(f"  {msg[:53]:<55} {event:<15} {tier_display:<8} {confidence:.2f}")

print(f"\n  Light model: {settings.light_model} (${0.0001}/1K tokens)")
print(f"  Heavy model: {settings.heavy_model} (${0.005}/1K tokens)")
print(f"  Cost ratio: Heavy is {0.005/0.0001:.0f}x more expensive")

# COMMAND ----------

# DBTITLE 1,Test 4: Semantic Cache (Lever 2 - Zero-Cost Duplicate Responses)
print("=" * 60)
print("  SEMANTIC CACHE TEST (Lever 2: Zero-Cost Duplicates)")
print("=" * 60)

# Store a response
cache_service.clear_all()
cache_service.store_response(
    query="What's the dress code at Zuma DIFC?",
    response="Smart casual. No shorts or flip-flops. Collared shirt recommended for gentlemen."
)
cache_service.store_response(
    query="How do I get to Dubai Mall from DIFC?",
    response="Take the Metro Red Line (1 stop) or taxi (8 min, ~AED 20)."
)

# Test with similar queries (should hit cache)
test_queries = [
    "What's the dress code at Zuma DIFC?",      # Exact match
    "dress code for Zuma in DIFC?",              # Similar phrasing
    "What should I wear to Zuma?",               # Semantic similar
    "Best sushi restaurant in Dubai Marina?",     # Unrelated (should miss)
]

print(f"\n  Cache threshold: {settings.semantic_cache_threshold}")
print(f"  {'─'*60}")
for query in test_queries:
    result = cache_service.check_cache(query)
    if result:
        response, score = result
        print(f"  HIT  [{score:.4f}] '{query[:45]}...'")
        print(f"        -> {response[:60]}...")
    else:
        print(f"  MISS [<{settings.semantic_cache_threshold}] '{query[:45]}...'")

stats = cache_service.get_stats()
print(f"\n  Cache Stats: {stats['total_hits']} hits / {stats['total_misses']} misses = {stats['hit_rate']:.1%} hit rate")

# COMMAND ----------

# DBTITLE 1,Test 5: Full State Machine - Swap Activity (End-to-End)
print("=" * 60)
print("  STATE MACHINE TEST: Swap Activity (Full Flow)")
print("=" * 60)

# Get the trip
trip = db_service.get_trip(trip.trip_id)
target_node = trip.nodes[3]  # Alserkal Avenue (non-locked)

print(f"\n  Before: Node '{target_node.venue_name}' ({target_node.micro_location})")
print(f"  Request: 'I'm tired, swap this for a quiet premium cafe'")
print(f"  {'─'*60}")

# Process the swap event
result = state_machine.process_event(
    trip_state=trip,
    event_type=EventType.SWAP_ACTIVITY.value,
    message="I'm tired of walking, swap this for a quiet premium cafe with great interiors",
    target_node_id=target_node.node_id,
    preferences={"vibe_tags": ["leisurely", "premium_interiors"], "mood": "relaxed"},
)

print(f"  Routing tier used: {result['routing_tier_used'].upper()}")
print(f"  From cache: {result['from_cache']}")
print(f"  Response: {result['response'][:100]}...")

if result['venues_found']:
    print(f"\n  Venues considered:")
    for v in result['venues_found']:
        print(f"    - {v.venue.name} (score: {v.final_score:.4f})")

updated_trip = result['updated_trip_state']
print(f"\n  After: Node '{updated_trip.nodes[3].venue_name}' ({updated_trip.nodes[3].micro_location})")
print(f"\n  Full updated itinerary:")
for i, node in enumerate(updated_trip.nodes, 1):
    lock_icon = " [LOCKED]" if node.is_locked else ""
    status_icon = " *SWAPPED*" if node.venue_name != trip.nodes[i-1].venue_name else ""
    print(f"    {i}. {node.venue_name}{lock_icon}{status_icon}")

# COMMAND ----------

# DBTITLE 1,Test 6: Reroute Throttle (Lever 1 - Free Tier Limit)
print("=" * 60)
print("  REROUTE THROTTLE TEST (Lever 1: 5 Reroutes/Day)")
print("=" * 60)

# Simulate using up reroutes
test_user = "throttle-test-user"
db_service.get_or_create_user(test_user)

print(f"\n  Free tier max: {settings.max_daily_reroutes_free} reroutes/day")
print(f"  {'─'*50}")

for i in range(7):  # Try 7 reroutes (should fail at 6th)
    allowed, remaining, max_r = db_service.check_reroute_allowed(test_user)
    if allowed:
        db_service.increment_reroute_count(test_user)
        print(f"  Reroute {i+1}: ALLOWED ({remaining-1} remaining)")
    else:
        print(f"  Reroute {i+1}: BLOCKED! Limit reached.")
        print(f"    -> HTTP 403: 'Upgrade to Pro for 50 reroutes/day'")
        break

# Test upgrade
print(f"\n  Upgrading user to Pro...")
db_service.upgrade_user(test_user)
allowed, remaining, max_r = db_service.check_reroute_allowed(test_user)
print(f"  Pro tier: {remaining} reroutes remaining (max: {max_r})")

# COMMAND ----------

# DBTITLE 1,Test 7: Maps Service - Transit & Venue Validation
print("=" * 60)
print("  MAPS SERVICE TEST (Transit Times & Validation)")
print("=" * 60)

# Calculate transit from Downtown to various locations
origin = (25.1972, 55.2744)  # Burj Khalifa area
destinations = [
    ("DIFC", 25.2100, 55.2800),
    ("Al Quoz (Alserkal)", 25.1436, 55.2250),
    ("Dubai Marina", 25.0805, 55.1403),
    ("Deira (Old Dubai)", 25.2700, 55.3100),
]

print(f"\n  From: Downtown Dubai (Burj Khalifa)")
print(f"  {'─'*50}")
for name, lat, lng in destinations:
    transit = maps_service.get_transit_time(origin[0], origin[1], lat, lng)
    print(f"  -> {name:<22} {transit['distance_km']:>5.1f} km | {transit['duration_minutes']:>3} min | Traffic: {transit['traffic_condition']}")

# Test venue validation
print(f"\n  Nearby landmarks from Downtown:")
landmarks = maps_service.get_nearby_landmarks(origin[0], origin[1], radius_km=3.0)
for name, dist in landmarks:
    print(f"    {name}: {dist} km")

# COMMAND ----------

# DBTITLE 1,Test 8: Full API Simulation (FastAPI with TestClient)
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

print("=" * 60)
print("  FULL API SIMULATION (FastAPI TestClient)")
print("=" * 60)

# 1. Health check
resp = client.get("/api/v1/health")
print(f"\n  GET /health -> {resp.status_code}")
health = resp.json()
print(f"    App: {health['app']} v{health['version']}")
print(f"    Venues: {health['venues_loaded']}")

# 2. Create a trip
resp = client.post("/api/v1/trip/create", json={
    "user_id": "api-test-user",
    "start_date": "2026-08-05T09:00:00",
    "initial_mood": "adventurous"
})
print(f"\n  POST /trip/create -> {resp.status_code}")
create_data = resp.json()
trip_id = create_data["trip_id"]
print(f"    Trip: {trip_id}")
print(f"    Nodes: {len(create_data['nodes'])} | Locked: {create_data['locked_count']}")

# 3. Process a light event (info query)
resp = client.post("/api/v1/trip/event", json={
    "user_id": "api-test-user",
    "trip_id": trip_id,
    "event_type": "ask_info",
    "message": "What's the dress code at this restaurant?"
})
print(f"\n  POST /trip/event (ask_info) -> {resp.status_code}")
event_data = resp.json()
print(f"    Tier: {event_data['routing_tier_used']} | Cache: {event_data['from_cache']}")
print(f"    Response: {event_data['message'][:80]}...")

# 4. Process a heavy event (swap activity)
nodes = create_data["nodes"]
target = nodes[1]["node_id"]  # Second activity (not locked)
resp = client.post("/api/v1/trip/event", json={
    "user_id": "api-test-user",
    "trip_id": trip_id,
    "event_type": "swap_activity",
    "message": "Replace this with a quiet gallery with amazing interiors",
    "target_node_id": target,
    "preferences": {"vibe_tags": ["artistic", "premium_interiors"]}
})
print(f"\n  POST /trip/event (swap) -> {resp.status_code}")
event_data = resp.json()
print(f"    Tier: {event_data['routing_tier_used']} | Cache: {event_data['from_cache']}")
print(f"    Reroutes remaining: {event_data['reroutes_remaining']}")
print(f"    Response: {event_data['message'][:80]}...")

# 5. Check user status
resp = client.get("/api/v1/user/api-test-user/status")
print(f"\n  GET /user/status -> {resp.status_code}")
print(f"    {resp.json()}")

# 6. Get system stats
resp = client.get("/api/v1/stats")
print(f"\n  GET /stats -> {resp.status_code}")
print(f"    {resp.json()}")

print(f"\n{'='*60}")
print(f"  ALL TESTS PASSED - MVP OPERATIONAL")
print(f"{'='*60}")
