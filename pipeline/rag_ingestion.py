"""Travel Buddy MVP - RAG Ingestion Pipeline

⚠️  STATUS: SCAFFOLDED — NOT WIRED INTO THE REQUEST PATH.
    This module is dead code in the current MVP. Venues come from
    seed_data.py (in-memory) or seed_supabase.py (Supabase).
    The scraping targets (TimeOut, Reddit) have ToS/legal exposure
    that must be cleared before running this for real.

The "Local Vibe" Engine (BRD Section 3).
Transforms unstructured local web data into searchable vector embeddings.

Pipeline steps:
  1. Scrape: Fetch content from Dubai lifestyle sources
  2. Parse: Extract venue-level information
  3. Chunk: Semantic chunking (preserving context)
  4. Extract Metadata: LLM pass for vibe_tags, audience, micro_location
  5. Embed: Generate vector embeddings
  6. Store: Upsert to Supabase pgvector

Sources (from BRD Section 3.1):
  - TimeOut Dubai
  - What's On UAE
  - Reddit r/dubai (filtered threads)
  - Curated lifestyle blogs

Requires:
  pip install httpx beautifulsoup4 litellm
  Environment vars: TB_LITELLM_API_KEY
"""

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urljoin

import httpx

from config.settings import settings
from pipeline.chunker import VenueChunk, chunker


# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class ScrapedVenue:
    """Raw venue data from scraping."""
    name: str
    raw_text: str
    source_url: str
    source_name: str  # "timeout_dubai", "whats_on", "reddit"
    scraped_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    raw_metadata: Dict = field(default_factory=dict)


@dataclass
class EnrichedVenue:
    """Venue with extracted metadata ready for embedding."""
    name: str
    description: str
    micro_location: str
    lat: float
    lng: float
    vibe_tags: List[str]
    audience: List[str]
    category: str
    opening_hours: str
    source_url: str
    chunks: List[VenueChunk] = field(default_factory=list)
    embeddings: List[List[float]] = field(default_factory=list)


# ==============================================================================
# Scraper Adapters
# ==============================================================================

class BaseScraper:
    """Base class for venue scrapers."""

    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self):
        self.rate_limit_delay = 2.0  # seconds between requests

    async def fetch_page(self, url: str) -> str:
        """Fetch a page with rate limiting and user agent."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"User-Agent": self.USER_AGENT},
                follow_redirects=True,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.text

    async def scrape_venues(self) -> List[ScrapedVenue]:
        raise NotImplementedError


class TimeOutDubaiScraper(BaseScraper):
    """Scraper for TimeOut Dubai venue reviews."""

    BASE_URL = "https://www.timeoutdubai.com"
    CATEGORIES = [
        "/restaurants",
        "/bars-nightlife",
        "/things-to-do/art-culture",
        "/things-to-do/attractions",
    ]

    async def scrape_venues(self) -> List[ScrapedVenue]:
        """Scrape venue listings from TimeOut Dubai."""
        from bs4 import BeautifulSoup

        venues = []
        for category in self.CATEGORIES:
            try:
                html = await self.fetch_page(f"{self.BASE_URL}{category}")
                soup = BeautifulSoup(html, "html.parser")

                # Find venue cards (structure varies by site updates)
                cards = soup.find_all("article", class_=re.compile(r"card|listing"))

                for card in cards[:10]:  # Limit per category
                    title_elem = card.find(["h2", "h3"])
                    desc_elem = card.find("p")
                    link_elem = card.find("a", href=True)

                    if title_elem and desc_elem:
                        venue_url = urljoin(self.BASE_URL, link_elem["href"]) if link_elem else ""
                        venues.append(ScrapedVenue(
                            name=title_elem.get_text(strip=True),
                            raw_text=desc_elem.get_text(strip=True),
                            source_url=venue_url,
                            source_name="timeout_dubai",
                        ))

                time.sleep(self.rate_limit_delay)

            except Exception as e:
                print(f"Error scraping {category}: {e}")
                continue

        return venues


class RedditDubaiScraper(BaseScraper):
    """Scraper for Reddit r/dubai venue discussions."""

    SUBREDDIT_URL = "https://www.reddit.com/r/dubai"
    SEARCH_QUERIES = [
        "best restaurants interior design",
        "quiet cafe premium",
        "hidden gems authentic local",
        "best acoustics bar lounge",
        "rooftop views premium",
    ]

    async def scrape_venues(self) -> List[ScrapedVenue]:
        """Fetch relevant Reddit discussions about Dubai venues."""
        venues = []

        for query in self.SEARCH_QUERIES:
            try:
                # Use Reddit JSON API (no auth needed for public)
                url = (
                    f"https://www.reddit.com/r/dubai/search.json"
                    f"?q={query}&restrict_sr=1&sort=relevance&limit=5"
                )
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        url,
                        headers={"User-Agent": self.USER_AGENT},
                        timeout=15.0,
                    )

                if response.status_code == 200:
                    data = response.json()
                    posts = data.get("data", {}).get("children", [])

                    for post in posts:
                        post_data = post.get("data", {})
                        text = post_data.get("selftext", "")
                        title = post_data.get("title", "")

                        if len(text) > 100:  # Only substantial posts
                            venues.append(ScrapedVenue(
                                name=title[:100],
                                raw_text=f"{title}. {text[:2000]}",
                                source_url=f"https://reddit.com{post_data.get('permalink', '')}",
                                source_name="reddit_dubai",
                            ))

                time.sleep(self.rate_limit_delay)

            except Exception as e:
                print(f"Reddit scrape error for '{query}': {e}")
                continue

        return venues


# ==============================================================================
# Metadata Extraction (LLM-powered)
# ==============================================================================

class MetadataExtractor:
    """Uses LLM to extract structured metadata from venue text.

    From BRD Section 3.2:
    - vibe_tags: [leisurely, premium_interiors, energetic, authentic]
    - audience: [solo_traveler, executive, family_with_teens]
    - micro_location: [Al Quoz, DIFC, Jumeirah]
    """

    EXTRACTION_PROMPT = """Extract structured metadata from this Dubai venue description.

Venue text: {text}

Extract the following as JSON:
{{
  "venue_name": "string (clean name)",
  "micro_location": "string (Dubai district: DIFC, Al Quoz, Jumeirah, Downtown, Deira, Dubai Marina, JBR, Business Bay, D3, Palm Jumeirah)",
  "category": "string (restaurant, cafe, gallery, bar, beach_club, museum, market, attraction, community_space, shopping)",
  "vibe_tags": ["list of: leisurely, premium_interiors, energetic, authentic, artistic, independent, cultural, executive"],
  "audience": ["list of: solo_traveler, executive, couple, family_with_teens, group, art_enthusiast, food_enthusiast, creative_professional"],
  "estimated_lat": 25.XXXX,
  "estimated_lng": 55.XXXX,
  "opening_hours": "HH:MM-HH:MM (best estimate)"
}}

Rules:
- Only include vibe_tags that genuinely apply
- Be specific about micro_location (use district name)
- Estimate coordinates for the Dubai district
- If unsure, use the district center coordinates"""

    async def extract_metadata(self, venue_text: str) -> Dict:
        """Extract metadata using LLM."""
        try:
            import litellm

            response = await litellm.acompletion(
                model=settings.light_model,  # Use cheap model for extraction
                messages=[
                    {
                        "role": "user",
                        "content": self.EXTRACTION_PROMPT.format(text=venue_text[:1500]),
                    }
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"Metadata extraction failed: {e}")
            return self._fallback_extraction(venue_text)

    def _fallback_extraction(self, text: str) -> Dict:
        """Rule-based fallback when LLM is unavailable."""
        text_lower = text.lower()

        # Simple keyword-based classification
        vibe_tags = []
        if any(w in text_lower for w in ["quiet", "calm", "relaxed", "peaceful"]):
            vibe_tags.append("leisurely")
        if any(w in text_lower for w in ["luxury", "premium", "elegant", "design"]):
            vibe_tags.append("premium_interiors")
        if any(w in text_lower for w in ["lively", "vibrant", "bustling", "music"]):
            vibe_tags.append("energetic")
        if any(w in text_lower for w in ["traditional", "heritage", "local", "authentic"]):
            vibe_tags.append("authentic")
        if any(w in text_lower for w in ["art", "gallery", "exhibition", "creative"]):
            vibe_tags.append("artistic")

        return {
            "venue_name": text[:50],
            "micro_location": "Downtown",
            "category": "experience",
            "vibe_tags": vibe_tags or ["leisurely"],
            "audience": ["solo_traveler"],
            "estimated_lat": 25.2048,
            "estimated_lng": 55.2708,
            "opening_hours": "09:00-23:00",
        }


# ==============================================================================
# Main Pipeline Orchestrator
# ==============================================================================

class RAGIngestionPipeline:
    """Orchestrates the full ingestion pipeline.

    Usage:
        pipeline = RAGIngestionPipeline()
        stats = await pipeline.run_full_ingestion()
    """

    def __init__(self):
        self.scrapers = [
            TimeOutDubaiScraper(),
            RedditDubaiScraper(),
        ]
        self.extractor = MetadataExtractor()
        self._stats = {
            "scraped": 0,
            "chunked": 0,
            "embedded": 0,
            "stored": 0,
            "errors": 0,
        }

    async def run_full_ingestion(self) -> Dict:
        """Execute the complete pipeline."""
        print(f"[{datetime.now(tz=timezone.utc)}] Starting RAG ingestion pipeline...")

        # Step 1: Scrape
        all_venues = []
        for scraper in self.scrapers:
            try:
                venues = await scraper.scrape_venues()
                all_venues.extend(venues)
                print(f"  Scraped {len(venues)} venues from {scraper.__class__.__name__}")
            except Exception as e:
                print(f"  Scraper {scraper.__class__.__name__} failed: {e}")
                self._stats["errors"] += 1

        self._stats["scraped"] = len(all_venues)

        # Step 2-5: Process each venue
        enriched_venues = []
        for venue in all_venues:
            try:
                enriched = await self._process_venue(venue)
                if enriched:
                    enriched_venues.append(enriched)
            except Exception as e:
                print(f"  Error processing {venue.name}: {e}")
                self._stats["errors"] += 1

        # Step 6: Store (would call supabase_service in production)
        self._stats["stored"] = len(enriched_venues)

        print(f"\n  Pipeline complete: {self._stats}")
        return self._stats

    async def _process_venue(self, venue: ScrapedVenue) -> Optional[EnrichedVenue]:
        """Process a single venue through the pipeline."""
        # Extract metadata via LLM
        metadata = await self.extractor.extract_metadata(venue.raw_text)

        # Chunk the text
        chunks = chunker.chunk_venue_text(
            text=venue.raw_text,
            venue_name=metadata.get("venue_name", venue.name),
            micro_location=metadata.get("micro_location", "Dubai"),
            source_url=venue.source_url,
        )
        self._stats["chunked"] += len(chunks)

        # Generate embeddings for each chunk
        embeddings = []
        try:
            import litellm
            for chunk in chunks:
                response = await litellm.aembedding(
                    model=settings.embedding_model,
                    input=[chunk.embedding_text],
                )
                embeddings.append(response.data[0]["embedding"])
                self._stats["embedded"] += 1
        except Exception as e:
            print(f"  Embedding failed for {venue.name}: {e}")
            return None

        return EnrichedVenue(
            name=metadata.get("venue_name", venue.name),
            description=venue.raw_text[:1000],
            micro_location=metadata.get("micro_location", "Dubai"),
            lat=metadata.get("estimated_lat", 25.2048),
            lng=metadata.get("estimated_lng", 55.2708),
            vibe_tags=metadata.get("vibe_tags", []),
            audience=metadata.get("audience", []),
            category=metadata.get("category", "experience"),
            opening_hours=metadata.get("opening_hours", "09:00-23:00"),
            source_url=venue.source_url,
            chunks=chunks,
            embeddings=embeddings,
        )

    async def ingest_single_venue(
        self, name: str, text: str, source_url: str = ""
    ) -> Optional[EnrichedVenue]:
        """Ingest a single venue (useful for manual additions)."""
        venue = ScrapedVenue(
            name=name,
            raw_text=text,
            source_url=source_url,
            source_name="manual",
        )
        return await self._process_venue(venue)


# Singleton
rag_pipeline = RAGIngestionPipeline()
