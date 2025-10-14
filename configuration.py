"""
Centralized configuration management for Cookidoo scraping.

This module provides a comprehensive configuration system that consolidates
all settings, defaults, timeouts, and parameters used throughout the application.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Union, Tuple, Pattern
import json
import os
import re


@dataclass
class ScrapingConfiguration:
    """
    Comprehensive configuration for Cookidoo scraping operations.

    All timeouts, delays, thread counts, and other parameters are centralized here.
    This makes the system easily configurable and maintainable.
    """

    # ============ Core Application Settings ============

    # File paths
    webdriver_path: str = ""
    output_dir: Path = Path("./output")
    json_dir: str = "json_food"
    cookies_file: str = "cookies.json"

    # Processing options
    locale: Optional[str] = None
    pattern: Optional[str] = None
    saved_collections: bool = False

    # Compiled regex patterns (computed from pattern string)
    collection_pattern: Optional[Pattern[str]] = field(default=None, init=False, repr=False)
    recipe_pattern: Optional[Pattern[str]] = field(default=None, init=False, repr=False)
    json_export: bool = False
    headless: bool = True
    save_cookies_only: bool = False

    # Collection exclusion patterns (regex) - collections matching these patterns will not have recipes saved to JSON
    # Even if recipe patterns would match recipes in these collections
    # Example: ["^Nickel", "Test.*"] would exclude collections like "Nickelodeon" or "Test Collection"
    excluded_collection_patterns: List[str] = field(default_factory=lambda: ['^ZZ'])

    # ============ Threading Configuration ============

    max_collection_threads: int = 3
    max_recipe_threads: int = 2

    # Thread safety and limits
    max_concurrent_browsers: int = field(init=False)  # Calculated from thread counts

    def __post_init__(self):
        # Calculate maximum concurrent browsers
        self.max_concurrent_browsers = self.max_collection_threads * (1 + self.max_recipe_threads)

    # ============ Timing and Delays ============

    # Browser timeouts (seconds)
    page_load_timeout: int = 30
    element_wait_timeout: int = 10
    implicit_wait: float = 0  # CRITICAL: Must be 0! Even 0.1s causes 300-400ms delays per recipe element when checking optional fields

    # Scrolling and dynamic content
    scroll_delay: float = 1.0
    max_scroll_retries: int = 3
    load_more_timeout: int = 2
    scroll_result_timeout: int = 2

    # Network timeouts
    image_download_timeout: int = 30
    json_save_timeout: int = 10

    # ============ Browser Configuration ============

    # Chrome options
    window_size: tuple = (1920, 1080)
    user_agent: Optional[str] = None
    disable_images: bool = False
    disable_javascript: bool = False

    # Performance settings
    disable_dev_shm_usage: bool = True  # Helps in Docker/limited memory environments
    disable_gpu: bool = True  # Reduces resource usage
    no_sandbox: bool = False  # Security vs compatibility tradeoff

    # ============ Content Processing ============

    # Recipe processing
    max_ingredient_length: int = 10000
    max_directions_length: int = 20000
    max_notes_length: int = 5000

    # Memory management
    enable_memory_cleanup: bool = True
    memory_cleanup_threshold: int = 100  # Clean memory after N recipes
    debug_memory_usage: bool = False

    # ============ Error Handling and Retry Logic ============

    max_retries: int = 3
    retry_delay: float = 2.0
    continue_on_error: bool = True

    # Collection processing
    skip_empty_collections: bool = True
    min_recipes_per_collection: int = 1

    # Recipe processing
    skip_invalid_recipes: bool = True
    require_ingredients: bool = True
    require_directions: bool = True

    # ============ Logging and Debugging ============

    verbose_logging: bool = False
    debug_selectors: bool = False
    log_memory_stats: bool = True
    log_timing_stats: bool = False

    # Progress reporting
    progress_update_interval: int = 10  # Report progress every N recipes
    show_memory_cleanup: bool = True

    # ============ Validation and Limits ============

    max_collections_per_run: int = 1000
    max_recipes_per_collection: int = 2000
    max_total_recipes: int = 10000

    # File size limits (MB)
    max_image_size_mb: int = 10
    max_json_size_mb: int = 5

    # ============ Advanced Configuration ============

    # Custom selector overrides (for different Cookidoo versions)
    custom_selectors: Dict[str, str] = field(default_factory=dict)

    # Feature flags
    experimental_features: Dict[str, bool] = field(default_factory=dict)

    # Additional metadata
    base_url: str = ""
    valid_categories: Dict[str, str] = field(default_factory=dict)


@dataclass
class BrowserConfiguration:
    """Browser-specific configuration extracted from main config."""

    headless: bool
    window_size: tuple
    page_load_timeout: int
    implicit_wait: int
    user_agent: Optional[str]
    disable_images: bool
    disable_javascript: bool
    disable_dev_shm_usage: bool
    disable_gpu: bool
    no_sandbox: bool

    @classmethod
    def from_scraping_config(cls, config: ScrapingConfiguration) -> 'BrowserConfiguration':
        """Create browser config from main scraping configuration."""
        return cls(
            headless=config.headless,
            window_size=config.window_size,
            page_load_timeout=config.page_load_timeout,
            implicit_wait=config.implicit_wait,
            user_agent=config.user_agent,
            disable_images=config.disable_images,
            disable_javascript=config.disable_javascript,
            disable_dev_shm_usage=config.disable_dev_shm_usage,
            disable_gpu=config.disable_gpu,
            no_sandbox=config.no_sandbox
        )


@dataclass
class ThreadingConfiguration:
    """Threading-specific configuration extracted from main config."""

    max_collection_threads: int
    max_recipe_threads: int
    max_concurrent_browsers: int

    @classmethod
    def from_scraping_config(cls, config: ScrapingConfiguration) -> 'ThreadingConfiguration':
        """Create threading config from main scraping configuration."""
        return cls(
            max_collection_threads=config.max_collection_threads,
            max_recipe_threads=config.max_recipe_threads,
            max_concurrent_browsers=config.max_concurrent_browsers
        )


class ConfigurationManager:
    """
    Manages loading, validation, and access to configuration settings.

    Provides methods to load configuration from files, environment variables,
    and command line arguments while maintaining validation and defaults.
    """

    @staticmethod
    def create_default_config() -> ScrapingConfiguration:
        """Create a configuration with all default values."""
        return ScrapingConfiguration()

    @staticmethod
    def load_from_file(filepath: str) -> ScrapingConfiguration:
        """
        Load configuration from JSON file.

        Args:
            filepath: Path to JSON configuration file

        Returns:
            ScrapingConfiguration with loaded values

        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is malformed
        """
        try:
            with open(filepath, 'r') as f:
                config_data = json.load(f)

            # Create default config and update with loaded values
            config = ScrapingConfiguration()

            # Update configuration with loaded values
            for key, value in config_data.items():
                if hasattr(config, key):
                    # Handle Path objects specially
                    if key == 'output_dir' and isinstance(value, str):
                        setattr(config, key, Path(value))
                    else:
                        setattr(config, key, value)
                else:
                    print(f"Warning: Unknown configuration key '{key}' ignored")

            return config

        except FileNotFoundError:
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")

    @staticmethod
    def save_to_file(config: ScrapingConfiguration, filepath: str):
        """
        Save configuration to JSON file.

        Args:
            config: Configuration to save
            filepath: Path where to save configuration
        """
        # Convert config to dictionary
        config_dict = {}

        for key, value in config.__dict__.items():
            # Handle special types
            if isinstance(value, Path):
                config_dict[key] = str(value)
            elif hasattr(value, '__dict__'):  # Complex objects
                config_dict[key] = value.__dict__
            else:
                config_dict[key] = value

        # Save to file with pretty formatting
        with open(filepath, 'w') as f:
            json.dump(config_dict, f, indent=4, sort_keys=True)

    @staticmethod
    def load_from_env(config: ScrapingConfiguration) -> ScrapingConfiguration:
        """
        Update configuration from environment variables.

        Environment variables should be prefixed with 'COOKIDUMP_'
        Example: COOKIDUMP_MAX_COLLECTION_THREADS=5

        Args:
            config: Base configuration to update

        Returns:
            Updated configuration
        """
        env_prefix = 'COOKIDUMP_'

        for key in config.__dict__.keys():
            env_key = f"{env_prefix}{key.upper()}"
            env_value = os.environ.get(env_key)

            if env_value is not None:
                # Get the current value to determine type
                current_value = getattr(config, key)

                try:
                    # Convert environment string to appropriate type
                    if isinstance(current_value, bool):
                        new_value = env_value.lower() in ('true', '1', 'yes', 'on')
                    elif isinstance(current_value, int):
                        new_value = int(env_value)
                    elif isinstance(current_value, float):
                        new_value = float(env_value)
                    elif isinstance(current_value, Path):
                        new_value = Path(env_value)
                    else:
                        new_value = env_value

                    setattr(config, key, new_value)

                except (ValueError, TypeError) as e:
                    print(f"Warning: Invalid environment value for {env_key}: {e}")

        return config

    @staticmethod
    def validate_configuration(config: ScrapingConfiguration) -> List[str]:
        """
        Validate configuration values and return list of issues.

        Args:
            config: Configuration to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        issues = []

        # Validate thread counts
        if config.max_collection_threads < 1:
            issues.append("max_collection_threads must be at least 1")
        if config.max_collection_threads > 20:
            issues.append("max_collection_threads should not exceed 20 (resource usage)")

        if config.max_recipe_threads < 1:
            issues.append("max_recipe_threads must be at least 1")
        if config.max_recipe_threads > 10:
            issues.append("max_recipe_threads should not exceed 10 per collection")

        # Validate timeouts
        if config.page_load_timeout < 5:
            issues.append("page_load_timeout should be at least 5 seconds")
        if config.element_wait_timeout < 1:
            issues.append("element_wait_timeout should be at least 1 second")
        if config.implicit_wait > 0.5:
            issues.append("implicit_wait should be 0 or very low (<=0.5s) to avoid cumulative delays when checking optional elements")

        # Validate scroll settings
        if config.scroll_delay < 0.1:
            issues.append("scroll_delay should be at least 0.1 seconds")
        if config.max_scroll_retries < 1:
            issues.append("max_scroll_retries should be at least 1")

        # Validate file size limits
        if config.max_image_size_mb < 1:
            issues.append("max_image_size_mb should be at least 1 MB")
        if config.max_json_size_mb < 1:
            issues.append("max_json_size_mb should be at least 1 MB")

        # Validate paths
        if config.webdriver_path and not os.path.exists(config.webdriver_path):
            issues.append(f"webdriver_path does not exist: {config.webdriver_path}")

        # Validate browser resource usage
        if config.max_concurrent_browsers > 50:
            issues.append(f"max_concurrent_browsers ({config.max_concurrent_browsers}) may use excessive resources")

        return issues

    @staticmethod
    def get_optimized_config_for_system() -> ScrapingConfiguration:
        """
        Create an optimized configuration based on system resources.

        Returns:
            Configuration optimized for the current system
        """
        import psutil

        config = ScrapingConfiguration()

        # Get system information
        cpu_count = psutil.cpu_count()
        memory_gb = psutil.virtual_memory().total / (1024**3)

        # Adjust thread counts based on system resources
        if cpu_count >= 8 and memory_gb >= 16:
            # High-end system
            config.max_collection_threads = min(6, cpu_count // 2)
            config.max_recipe_threads = 3
        elif cpu_count >= 4 and memory_gb >= 8:
            # Mid-range system
            config.max_collection_threads = 4
            config.max_recipe_threads = 2
        else:
            # Low-end system
            config.max_collection_threads = 2
            config.max_recipe_threads = 1

        # Adjust timeouts for slower systems
        if memory_gb < 4:
            config.page_load_timeout = 45
            config.element_wait_timeout = 15
            config.scroll_delay = 1.5

        # Enable memory cleanup for systems with limited RAM
        if memory_gb < 8:
            config.enable_memory_cleanup = True
            config.memory_cleanup_threshold = 50
            config.debug_memory_usage = True

        return config

    @staticmethod
    def is_collection_excluded_from_json(config: ScrapingConfiguration, collection_title: str) -> bool:
        """
        Check if a collection should be excluded from JSON export based on regex exclusion patterns.

        Args:
            config: Configuration containing regex exclusion patterns
            collection_title: Title of the collection to check

        Returns:
            True if collection should be excluded, False otherwise
        """
        if not config.excluded_collection_patterns:
            return False

        import re

        for pattern in config.excluded_collection_patterns:
            try:
                # Use regex matching (case insensitive)
                if re.search(pattern, collection_title, re.IGNORECASE):
                    return True
            except re.error:
                # Log invalid regex patterns but continue processing
                print(f"Warning: Invalid regex pattern '{pattern}' in excluded_collection_patterns")
                continue

        return False

    @staticmethod
    def validate_and_compile_pattern(pattern: str) -> Tuple[bool, str, Optional[Pattern[str]], Optional[Pattern[str]]]:
        """
        Validate and compile collection and recipe regex patterns.

        Pattern format: collection_regex[::recipe_regex]
        If no '::' is present, the entire pattern is treated as a collection pattern.

        Args:
            pattern: Pattern string to validate and compile

        Returns:
            Tuple of (is_valid, error_message, compiled_collection_pattern, compiled_recipe_pattern)
            is_valid: True if pattern is valid, False otherwise
            error_message: Empty string if valid, error description if invalid
            compiled_collection_pattern: Compiled regex for collection matching (None if no pattern)
            compiled_recipe_pattern: Compiled regex for recipe matching (None if no pattern)
        """
        if not pattern:
            return True, "", None, None  # Empty pattern is valid (means no filtering)

        try:
            compiled_collection = None
            compiled_recipe = None

            if '::' in pattern:
                # Split pattern into collection and recipe parts
                collection_pattern_str = re.sub(r'::.*', '', pattern)
                recipe_pattern_str = re.sub(r'.*::', '', pattern)

                # Validate and compile collection pattern
                if collection_pattern_str:
                    try:
                        compiled_collection = re.compile(collection_pattern_str)
                    except re.error as e:
                        return False, f"Invalid collection regex '{collection_pattern_str}': {e}", None, None

                # Validate and compile recipe pattern
                if recipe_pattern_str:
                    try:
                        compiled_recipe = re.compile(recipe_pattern_str)
                    except re.error as e:
                        return False, f"Invalid recipe regex '{recipe_pattern_str}': {e}", None, None

            else:
                # No '::' separator, treat entire pattern as collection pattern
                try:
                    compiled_collection = re.compile(pattern)
                except re.error as e:
                    return False, f"Invalid collection regex '{pattern}': {e}", None, None

            return True, "", compiled_collection, compiled_recipe

        except Exception as e:
            return False, f"Pattern validation error: {e}", None, None

    @staticmethod
    def validate_pattern(pattern: str) -> Tuple[bool, str]:
        """
        Validate collection and recipe regex patterns (backward compatibility).

        This is a simplified version that only returns validation status.
        For new code, use validate_and_compile_pattern instead.

        Args:
            pattern: Pattern string to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        is_valid, error_message, _, _ = ConfigurationManager.validate_and_compile_pattern(pattern)
        return is_valid, error_message

    @staticmethod
    def create_config_from_args(args) -> ScrapingConfiguration:
        """
        Create configuration from command line arguments.

        Args:
            args: Parsed command line arguments

        Returns:
            Configuration with values from arguments
        """
        config = ScrapingConfiguration()

        # Map command line arguments to configuration
        config.webdriver_path = args.webdriverfile
        config.output_dir = Path(args.outputdir)
        config.locale = args.locale
        config.pattern = args.pattern
        config.saved_collections = args.saved
        config.json_export = args.json is not None
        config.json_dir = args.json if args.json else "json_food"
        config.headless = args.headless
        config.save_cookies_only = args.save_cookies
        config.max_collection_threads = args.max_threads

        # Validate and compile patterns before proceeding
        if args.pattern:
            is_valid, error_message, compiled_collection, compiled_recipe = ConfigurationManager.validate_and_compile_pattern(args.pattern)
            if not is_valid:
                raise ValueError(f"Invalid pattern '{args.pattern}': {error_message}")

            # Store the compiled patterns for efficient reuse during scraping
            config.collection_pattern = compiled_collection
            config.recipe_pattern = compiled_recipe

        return config
