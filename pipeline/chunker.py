"""Travel Buddy MVP - Semantic Chunker

Splits scraped venue text by semantic boundaries (not word count).
Ensures:
  - Reviews about acoustics stay with that venue
  - Vibe descriptions stay tethered to location data
  - Metadata tags are extracted alongside each chunk

Chunking Strategy (from BRD Section 3.2):
  1. Split by venue (each venue = one logical unit)
  2. Within venue: split by thematic context if >500 tokens
  3. Preserve contextual headers (venue name, location)
"""

import re
from typing import Dict, List, Optional


class VenueChunk:
    """A semantic chunk of venue information."""

    def __init__(
        self,
        text: str,
        venue_name: str,
        micro_location: str,
        chunk_type: str = "description",  # description, review, feature
        source_url: Optional[str] = None,
    ):
        self.text = text
        self.venue_name = venue_name
        self.micro_location = micro_location
        self.chunk_type = chunk_type
        self.source_url = source_url
        self.token_count = len(text.split())  # Approximate

    @property
    def embedding_text(self) -> str:
        """Text used for embedding generation.

        Includes venue context for semantic grounding.
        """
        return f"{self.venue_name} in {self.micro_location}, Dubai. {self.text}"

    def to_dict(self) -> Dict:
        return {
            "text": self.text,
            "venue_name": self.venue_name,
            "micro_location": self.micro_location,
            "chunk_type": self.chunk_type,
            "source_url": self.source_url,
            "token_count": self.token_count,
        }


class SemanticChunker:
    """Chunks venue content by semantic boundaries."""

    MAX_CHUNK_TOKENS = 500
    MIN_CHUNK_TOKENS = 50

    # Thematic separators (ordered by priority)
    THEME_SEPARATORS = [
        r"\n\n",  # Double newline
        r"\. (?=[A-Z])",  # Sentence boundary
        r"(?:Interior|Atmosphere|Food|Drinks|Service|Location|Price):",  # Section headers
    ]

    def chunk_venue_text(
        self,
        text: str,
        venue_name: str,
        micro_location: str,
        source_url: Optional[str] = None,
    ) -> List[VenueChunk]:
        """Split venue text into semantic chunks."""
        # Clean text
        text = self._clean_text(text)

        # If short enough, keep as single chunk
        if len(text.split()) <= self.MAX_CHUNK_TOKENS:
            return [
                VenueChunk(
                    text=text,
                    venue_name=venue_name,
                    micro_location=micro_location,
                    source_url=source_url,
                )
            ]

        # Split by thematic separators
        segments = self._split_by_themes(text)

        # Merge small segments, split large ones
        chunks = []
        current_chunk = ""

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            combined = f"{current_chunk} {segment}".strip()

            if len(combined.split()) > self.MAX_CHUNK_TOKENS:
                # Save current chunk if substantial
                if len(current_chunk.split()) >= self.MIN_CHUNK_TOKENS:
                    chunks.append(
                        VenueChunk(
                            text=current_chunk.strip(),
                            venue_name=venue_name,
                            micro_location=micro_location,
                            chunk_type=self._classify_chunk(current_chunk),
                            source_url=source_url,
                        )
                    )
                current_chunk = segment
            else:
                current_chunk = combined

        # Don't forget the last chunk
        if current_chunk and len(current_chunk.split()) >= self.MIN_CHUNK_TOKENS:
            chunks.append(
                VenueChunk(
                    text=current_chunk.strip(),
                    venue_name=venue_name,
                    micro_location=micro_location,
                    chunk_type=self._classify_chunk(current_chunk),
                    source_url=source_url,
                )
            )

        return (
            chunks
            if chunks
            else [
                VenueChunk(
                    text=text[:2000],
                    venue_name=venue_name,
                    micro_location=micro_location,
                    source_url=source_url,
                )
            ]
        )

    def chunk_review(
        self,
        review_text: str,
        venue_name: str,
        micro_location: str,
        reviewer: Optional[str] = None,
    ) -> List[VenueChunk]:
        """Chunk a user review, preserving sentiment and context."""
        chunks = self.chunk_venue_text(
            text=review_text,
            venue_name=venue_name,
            micro_location=micro_location,
        )
        for chunk in chunks:
            chunk.chunk_type = "review"
        return chunks

    def _split_by_themes(self, text: str) -> List[str]:
        """Split text by thematic boundaries."""
        # Try separators in priority order
        for sep_pattern in self.THEME_SEPARATORS:
            segments = re.split(sep_pattern, text)
            if len(segments) > 1:
                return segments

        # Fallback: split by sentences
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return sentences

    def _classify_chunk(self, text: str) -> str:
        """Classify chunk type based on content."""
        text_lower = text.lower()

        if any(
            w in text_lower
            for w in ["interior", "design", "decor", "acoustic", "lighting", "furniture"]
        ):
            return "atmosphere"
        elif any(w in text_lower for w in ["food", "menu", "dish", "cuisine", "chef", "taste"]):
            return "culinary"
        elif any(w in text_lower for w in ["service", "staff", "attentive", "friendly", "wait"]):
            return "service"
        elif any(w in text_lower for w in ["price", "expensive", "affordable", "value", "cost"]):
            return "pricing"
        elif any(w in text_lower for w in ["located", "area", "neighborhood", "district", "walk"]):
            return "location"
        else:
            return "description"

    def _clean_text(self, text: str) -> str:
        """Clean raw scraped text."""
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        # Remove HTML artifacts
        text = re.sub(r"<[^>]+>", "", text)
        # Remove excessive punctuation
        text = re.sub(r"[.]{3,}", "...", text)
        return text.strip()


# Singleton instance
chunker = SemanticChunker()
