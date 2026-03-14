"""
Configuration for the email_finder package.

Loads settings from environment variables (via python-dotenv) with sensible
defaults. Required credentials (Mailin, Perplexity) raise a clear error when
missing so misconfigured environments fail fast.
"""

import os
from typing import Optional
from pydantic import BaseModel, model_validator
from dotenv import load_dotenv

load_dotenv()


class Config(BaseModel):
    # Mailin credentials (required)
    mailin_email: str
    mailin_password: str

    # API keys (required)
    perplexity_api_key: str

    # Name matching thresholds
    name_match_threshold: float = 0.6
    lcs_min_length: int = 4

    # Email filtering
    generic_email_prefixes: list = [
        "info", "support", "hello", "contact", "admin",
        "team", "office", "sales", "help", "media",
    ]

    # Blacklisted domains (podcast hosting platforms)
    blacklisted_domains: list = [
        "spreaker.com", "anchor.fm", "spotify.com", "podcasters.spotify.com",
        "simplecast.com", "buzzsprout.com", "libsyn.com", "podbean.com",
        "transistor.fm", "redcircle.com", "megaphone.fm", "omny.fm",
    ]

    # Browser automation
    browser_timeout: int = 30       # seconds
    mailin_wait_timeout: int = 300  # seconds to wait for bulk verify

    # Pattern generation
    max_patterns_per_lead: int = 10

    @model_validator(mode="before")
    @classmethod
    def load_from_env(cls, values: dict) -> dict:
        """Fill missing required fields from environment variables."""
        env_map = {
            "mailin_email": "MAILIN_EMAIL",
            "mailin_password": "MAILIN_PASSWORD",
            "perplexity_api_key": "PERPLEXITY_API_KEY",
        }
        for field, env_var in env_map.items():
            if not values.get(field):
                env_val = os.getenv(env_var)
                if env_val:
                    values[field] = env_val
        return values


def get_config(**overrides) -> Config:
    """
    Return a Config instance populated from environment variables.
    Pass keyword arguments to override specific fields.
    """
    return Config(**overrides)
