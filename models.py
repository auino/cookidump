"""
Data models for Cookidoo scraping.

This module contains the dataclass definitions for Recipe and Collection objects.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class RecipeState(Enum):
    """Memory management states for Recipe objects."""
    BASIC_INFO_ONLY = "basic"      # ID, title, URL only
    FULL_DATA_LOADED = "loaded"    # All content loaded
    JSON_EXPORTED = "exported"     # JSON written, content can be cleared
    MEMORY_CLEARED = "cleared"     # Large fields cleared to save memory


@dataclass
class Collection:
    title: str
    url: str
    colltype: str

    # Collection data
    all_recipes: List['Recipe'] = None  # All recipes in the collection
    json_recipes: List['Recipe'] = None  # Recipes to be exported as JSON (filtered by pattern)
    recipe_list_text: str = ""  # Text representation of all recipes for file output
    actual_recipe_count: int = 0  # Actual count from scraping the page
    header_recipe_count: int = -1  # Count from page header (for saved collections only)
    official_recipe_count: int = -1  # Official count from management page (for master index)

    def __post_init__(self):
        if self.all_recipes is None:
            self.all_recipes = []
        if self.json_recipes is None:
            self.json_recipes = []

    @property
    def master_index_count(self) -> int:
        """The recipe count to use in the Master Index - official count when available."""
        return self.official_recipe_count if self.official_recipe_count != -1 else self.actual_recipe_count


@dataclass
class Recipe:
    id: str
    title: str
    url: str
    # Core recipe information
    language: str = ""
    categories: List[str] = None
    source: str = ""
    source_url: str = ""

    # Content
    ingredients: str = ""
    directions: str = ""
    notes: str = ""
    mynotes: str = ""
    tags: List[str] = None

    # Timing and serving info
    prep_time: str = ""
    total_time: str = ""
    servings: str = ""
    scaling: List[str] = None

    # Image data
    photo_data: str = ""
    photos: List[dict] = None

    # Memory management (not included in JSON)
    _memory_state: RecipeState = field(default=RecipeState.BASIC_INFO_ONLY, init=False, repr=False)

    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if self.tags is None:
            self.tags = []
        if self.scaling is None:
            self.scaling = []
        if self.photos is None:
            self.photos = []

    def mark_full_data_loaded(self):
        """Mark that all recipe data has been loaded."""
        self._memory_state = RecipeState.FULL_DATA_LOADED

    def mark_json_exported(self):
        """Mark that JSON has been exported for this recipe."""
        self._memory_state = RecipeState.JSON_EXPORTED

    def clear_memory_heavy_fields(self, debug: bool = False):
        """
        Clear memory-heavy fields to reduce memory usage.
        Only clears if JSON has been exported.
        """
        if self._memory_state != RecipeState.JSON_EXPORTED:
            return False  # Not safe to clear yet

        if debug:
            # Calculate approximate memory usage before clearing
            memory_before = (
                len(self.photo_data) +
                len(self.ingredients) +
                len(self.directions) +
                len(self.notes) +
                len(self.mynotes)
            )

        # Clear the memory-heavy fields
        self.ingredients = ""
        self.directions = ""
        self.notes = ""
        self.mynotes = ""
        self.photo_data = ""
        self.photos = []

        self._memory_state = RecipeState.MEMORY_CLEARED

        if debug:
            print(f"Cleared ~{memory_before:,} characters from recipe {self.id}")

        return True

    def is_memory_cleared(self) -> bool:
        """Check if memory has been cleared for this recipe."""
        return self._memory_state == RecipeState.MEMORY_CLEARED

    def is_json_exported(self) -> bool:
        """Check if JSON has been exported for this recipe."""
        return self._memory_state in [RecipeState.JSON_EXPORTED, RecipeState.MEMORY_CLEARED]

    def get_memory_state(self) -> RecipeState:
        """Get current memory state."""
        return self._memory_state

    def get_estimated_memory_usage(self) -> int:
        """Get estimated memory usage in bytes (rough approximation)."""
        if self._memory_state == RecipeState.MEMORY_CLEARED:
            # Only basic fields remain
            return len(self.id) + len(self.title) + len(self.url) + 100  # ~100 bytes overhead

        # Full data loaded
        return (
            len(self.id) + len(self.title) + len(self.url) +
            len(self.ingredients) + len(self.directions) +
            len(self.notes) + len(self.mynotes) + len(self.photo_data) +
            len(str(self.categories)) + len(str(self.tags)) +
            len(str(self.photos)) + 200  # ~200 bytes overhead
        )
