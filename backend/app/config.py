import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DATA_DIR = ROOT_DIR / "data"

load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class MarketConfig:
    country: str = "AE"
    name: str = "UAE"
    languages: tuple[str, ...] = ("en", "ar")
    timezone: str = "Asia/Dubai"


# YouTube videoCategoryIds hidden when the "Marketing-relevant" toggle is on.
NOISE_CATEGORY_IDS: frozenset[str] = frozenset({"10", "20"})  # Music, Gaming

YOUTUBE_CATEGORIES: dict[str, str] = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "19": "Travel & Events",
    "20": "Gaming",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
}


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY", ""))
    # "claude_cli" (default): headless Claude Code using the logged-in subscription. "mock": tests/UI dev.
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "claude_cli"))
    # Optional model override for `claude --model`; empty = CLI default.
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    claude_cli_bin: str = field(default_factory=lambda: os.getenv("CLAUDE_CLI_BIN", "claude"))
    llm_timeout_seconds: int = 300
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'dashboard.db'}")
    )
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)
    top_n: int = 10
    youtube_max_results: int = 50
    youtube_stale_hours: int = 24
    top_comments: int = 20


MARKET = MarketConfig()
settings = Settings()
