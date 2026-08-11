"""Travel Buddy MVP - Synthetic Seed Data

Curated Dubai venues focusing on exceptional interior design,
refined acoustics, independent culture, and premium environments.
Bypasses generic tourist spots in favor of locally-revered spaces.
"""

from models.schemas import VenueRAG
from services.db_provider import db_service


DUBAI_VENUES = [
    VenueRAG(
        name="The Third Line Gallery",
        description="One of the Middle East's most respected contemporary art spaces. Stark white walls with polished concrete floors create a meditative viewing experience. Rotating exhibitions from regional and international artists.",
        micro_location="Al Quoz",
        lat=25.1436, lng=55.2250,
        vibe_tags=["artistic", "premium_interiors", "leisurely", "authentic"],
        audience=["solo_traveler", "executive", "art_enthusiast"],
        category="gallery",
        opening_hours="10:00-19:00",
    ),
    VenueRAG(
        name="Carbon 12",
        description="An edgy contemporary gallery in a converted warehouse space within Alserkal Avenue. Raw industrial architecture meets carefully curated photography and mixed-media installations. Known for championing emerging MENASA artists.",
        micro_location="Al Quoz",
        lat=25.1440, lng=55.2245,
        vibe_tags=["artistic", "independent", "authentic", "energetic"],
        audience=["solo_traveler", "art_enthusiast", "creative_professional"],
        category="gallery",
        opening_hours="10:00-18:00",
    ),
    VenueRAG(
        name="A4 Space",
        description="A multi-purpose creative community space in Alserkal Avenue. Features a library, cinema, workshop spaces, and an intimate rooftop garden. Original warehouse steel beams meet locally-sourced timber shelving.",
        micro_location="Al Quoz",
        lat=25.1433, lng=55.2248,
        vibe_tags=["artistic", "authentic", "leisurely", "independent"],
        audience=["solo_traveler", "creative_professional", "family_with_teens"],
        category="community_space",
        opening_hours="09:00-21:00",
    ),
    VenueRAG(
        name="The Maine Oyster Bar and Grill",
        description="New England-inspired interiors in DIFC. Dark wood paneling, brass fixtures, and vintage maritime decor create an intimate 1920s East Coast oyster house atmosphere. Exceptional raw bar and craft cocktails.",
        micro_location="DIFC",
        lat=25.2115, lng=55.2795,
        vibe_tags=["premium_interiors", "leisurely", "executive"],
        audience=["executive", "couple", "solo_traveler"],
        category="restaurant",
        is_sponsored=True, bid_weight=0.8,
        opening_hours="12:00-01:00",
    ),
    VenueRAG(
        name="Opera Gallery DIFC",
        description="A blue-chip gallery representing modern masters and contemporary heavyweights. Museum-quality lighting and climate control. Works by Banksy, Kaws, and regional artists rotate quarterly.",
        micro_location="DIFC",
        lat=25.2108, lng=55.2801,
        vibe_tags=["artistic", "premium_interiors", "executive", "leisurely"],
        audience=["executive", "art_enthusiast", "collector"],
        category="gallery",
        opening_hours="10:00-20:00",
    ),
    VenueRAG(
        name="Zuma DIFC",
        description="Izakaya-inspired restaurant with open-plan kitchen and robata grill centerpiece. Natural stone, warm timber, and flowing water features create zen-like atmosphere. Legendary Saturday brunch among Dubai residents.",
        micro_location="DIFC",
        lat=25.2105, lng=55.2810,
        vibe_tags=["premium_interiors", "energetic", "executive", "authentic"],
        audience=["executive", "couple", "group"],
        category="restaurant",
        is_sponsored=True, bid_weight=0.6,
        opening_hours="12:00-00:00",
    ),
    VenueRAG(
        name="Drift Beach Dubai",
        description="Private beach club at One and Only Royal Mirage with French Riviera aesthetics. White-washed cabanas, azure infinity pool, hand-raked sand. Sound system calibrated for ambient listening. Mediterranean menu by Michelin-trained chef.",
        micro_location="Jumeirah",
        lat=25.0980, lng=55.1680,
        vibe_tags=["leisurely", "premium_interiors", "executive"],
        audience=["executive", "couple", "solo_traveler"],
        category="beach_club",
        opening_hours="08:00-20:00",
    ),
    VenueRAG(
        name="Madinat Jumeirah Souk",
        description="Recreated traditional Arabian souk with winding waterways and abra boat rides. Artisan boutiques, traditional wind-tower architecture, evening lantern lighting and live oud music.",
        micro_location="Jumeirah",
        lat=25.1340, lng=55.1852,
        vibe_tags=["authentic", "cultural", "leisurely", "premium_interiors"],
        audience=["family_with_teens", "couple", "solo_traveler"],
        category="shopping",
        opening_hours="10:00-23:00",
    ),
    VenueRAG(
        name="The Espresso Lab",
        description="Dubai's specialty coffee pioneers. Single-origin beans roasted in-house. Minimalist Scandinavian-Japanese interior with terrazzo counters, handmade ceramic cups. No music - just the sound of extraction. Pour-over rituals.",
        micro_location="Business Bay",
        lat=25.2280, lng=55.2870,
        vibe_tags=["leisurely", "premium_interiors", "authentic", "independent"],
        audience=["solo_traveler", "executive", "creative_professional"],
        category="cafe",
        opening_hours="07:00-22:00",
    ),
    VenueRAG(
        name="Atmosphere Burj Khalifa",
        description="World's highest restaurant on the 122nd floor. Custom-woven carpets, hand-blown glass installations, acoustically-treated walls for intimate conversation. Refined afternoon tea service.",
        micro_location="Downtown",
        lat=25.1972, lng=55.2744,
        vibe_tags=["premium_interiors", "executive", "leisurely"],
        audience=["couple", "executive", "family_with_teens"],
        category="restaurant",
        is_sponsored=True, bid_weight=0.9,
        opening_hours="09:00-23:00",
    ),
    VenueRAG(
        name="Arabian Tea House",
        description="Restored heritage house with traditional courtyard architecture. White-washed walls, turquoise accents, bougainvillea pergolas, barasti ceiling. Traditional Emirati breakfast and karak chai. Authentic old Dubai.",
        micro_location="Deira",
        lat=25.2635, lng=55.2970,
        vibe_tags=["authentic", "cultural", "leisurely", "independent"],
        audience=["solo_traveler", "family_with_teens", "couple"],
        category="cafe",
        opening_hours="07:00-22:00",
    ),
    VenueRAG(
        name="Gold Souk and Spice Souk",
        description="Historic commercial heart of old Dubai. Narrow alleys with 300+ gold retailers and spice merchants. Sensory experience of frankincense, saffron, cardamom. Best in late afternoon with local shoppers.",
        micro_location="Deira",
        lat=25.2862, lng=55.2962,
        vibe_tags=["authentic", "cultural", "energetic"],
        audience=["solo_traveler", "family_with_teens", "couple"],
        category="market",
        opening_hours="10:00-22:00",
    ),
    VenueRAG(
        name="Tresind Studio",
        description="20-seat chef's table with progressive Indian cuisine. Custom acoustic panels, moody lighting, open kitchen. One Michelin star. Fixed 8-course tasting menu changes monthly based on seasonal Indian ingredients.",
        micro_location="Dubai Marina",
        lat=25.0760, lng=55.1410,
        vibe_tags=["premium_interiors", "executive", "authentic", "leisurely"],
        audience=["executive", "couple", "food_enthusiast"],
        category="restaurant",
        opening_hours="19:00-23:00",
    ),
    VenueRAG(
        name="Ain Dubai Observation Wheel",
        description="World's largest observation wheel at 250 meters. Private climate-controlled cabins with premium seating. 38-minute rotation with 360-degree views. Best at sunset as the city transitions from gold to neon.",
        micro_location="JBR",
        lat=25.0800, lng=55.1290,
        vibe_tags=["energetic", "premium_interiors", "leisurely"],
        audience=["couple", "family_with_teens", "solo_traveler"],
        category="attraction",
        opening_hours="10:00-22:00",
    ),
    VenueRAG(
        name="The Lighthouse D3",
        description="Beautifully designed restaurant in Dubai Design District. Showcase of regional design talent - custom furniture, artisanal ceramics. Clean seasonal Mediterranean-Arabic fusion. Attracts architects and designers.",
        micro_location="D3",
        lat=25.1850, lng=55.2880,
        vibe_tags=["premium_interiors", "artistic", "leisurely", "independent"],
        audience=["creative_professional", "executive", "solo_traveler"],
        category="restaurant",
        opening_hours="08:00-23:00",
    ),
    VenueRAG(
        name="Museum of the Future",
        description="Visionary architectural landmark with Arabic calligraphy windows. Interior deploys spatial audio, projection mapping, and biophilic design across seven floors. Speculative scenarios for humanity's future.",
        micro_location="Downtown",
        lat=25.2208, lng=55.2812,
        vibe_tags=["energetic", "premium_interiors", "artistic", "cultural"],
        audience=["family_with_teens", "solo_traveler", "creative_professional"],
        category="museum",
        opening_hours="10:00-19:30",
    ),
]


def seed_venues() -> tuple:
    """Seed the in-memory venue database with Dubai venues. Returns count.

    When the backend is SupabaseService, venues are already in the database
    (seeded once via seed_supabase.py with real embeddings). Skip the seed
    and report the existing count instead.
    """
    from services.db_provider import IS_SUPABASE
    if IS_SUPABASE:
        # Venues live in venues_rag, seeded by seed_supabase.py.
        # Don't call add_venue() — it requires an embedding argument
        # that the in-memory seed path doesn't compute.
        try:
            count = db_service.get_venue_count()
            return count, "from venues_rag"
        except Exception:
            return 0, "venues_rag unreachable"
    for venue in DUBAI_VENUES:
        db_service.add_venue(venue)
    return len(DUBAI_VENUES), "seeded in-memory"


if __name__ == "__main__":
    count = seed_venues()
    print(f"Seeded {count} venues into the database.")
