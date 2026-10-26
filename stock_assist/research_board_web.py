"""Four-route interactive entry for the existing local InsightRadar server."""
from pathlib import Path


def render_research_board(token: str) -> str:
    return Path(__file__).with_name("research_board.html").read_text(encoding="utf-8").replace("__LOCAL_SESSION_TOKEN__", token)
