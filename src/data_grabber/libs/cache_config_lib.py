import json
import random
from pathlib import Path

CACHE_CONFIG_FILENAME = 'cache_config.json'
CACHE_CONFIG_PATH = Path(__file__).resolve().parent.parent / CACHE_CONFIG_FILENAME

DEFAULT_CACHE_CONFIG = {
    'user_details': {
        'ttl_days_min': 7.0,
        'ttl_days_max': 14.0,
    },
    'nominatim': {
        'ttl_days_min': 180.0,
        'ttl_days_max': 365.0,
    },
}


def _copy_defaults():
    return {name: dict(values) for name, values in DEFAULT_CACHE_CONFIG.items()}


def _validate_number(cache_name, setting, value, config_path):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"Invalid value for '{cache_name}.{setting}' in {config_path}: "
            f"expected a number, got {value!r}."
        )
    return float(value)


def load_cache_config(path=None):
    """
    Loads and validates cache TTL settings.

    Missing files and missing settings fall back to DEFAULT_CACHE_CONFIG.
    Invalid settings raise a ValueError.
    """
    config_path = Path(path) if path is not None else CACHE_CONFIG_PATH
    config = _copy_defaults()

    if not config_path.is_file():
        return config

    try:
        with config_path.open('r', encoding='utf-8') as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read cache configuration {config_path}: {error}") from error

    if not isinstance(data, dict):
        raise ValueError(f"Cache configuration {config_path} must contain a JSON object.")

    for cache_name, cache_values in data.items():
        if cache_name not in DEFAULT_CACHE_CONFIG:
            raise ValueError(
                f"Unknown cache '{cache_name}' in {config_path}. "
                f"Valid names: {', '.join(sorted(DEFAULT_CACHE_CONFIG))}."
            )
        if not isinstance(cache_values, dict):
            raise ValueError(
                f"Cache '{cache_name}' in {config_path} must contain a JSON object."
            )
        for setting, value in cache_values.items():
            if setting not in DEFAULT_CACHE_CONFIG[cache_name]:
                raise ValueError(
                    f"Unknown setting '{cache_name}.{setting}' in {config_path}. "
                    f"Valid settings: {', '.join(sorted(DEFAULT_CACHE_CONFIG[cache_name]))}."
                )
            config[cache_name][setting] = _validate_number(
                cache_name, setting, value, config_path
            )

    for cache_name, values in config.items():
        minimum = values['ttl_days_min']
        maximum = values['ttl_days_max']
        if minimum <= 0:
            raise ValueError(
                f"'{cache_name}.ttl_days_min' in {config_path} must be greater than 0."
            )
        if maximum < minimum:
            raise ValueError(
                f"'{cache_name}.ttl_days_max' in {config_path} must be "
                f"greater than or equal to ttl_days_min."
            )

    return config


CACHE_CONFIG = load_cache_config()


def get_ttl_seconds(cache_name):
    """
    Returns a random TTL in seconds for the given cache.

    The value is drawn uniformly from the configured min/max range on every call.
    If both values are equal, the TTL is fixed.
    """
    try:
        values = CACHE_CONFIG[cache_name]
    except KeyError as error:
        raise KeyError(f"Unknown cache '{cache_name}'.") from error

    days = random.uniform(values['ttl_days_min'], values['ttl_days_max'])
    return days * 24 * 60 * 60
