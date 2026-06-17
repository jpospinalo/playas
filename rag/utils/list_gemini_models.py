#!/usr/bin/env python
"""List available Gemini/Gemma models and their supported actions.

Usage:
    uv run python scripts/list_gemini_models.py
"""

import os

from dotenv import load_dotenv
from google import genai

load_dotenv()


def list_models() -> None:
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta GOOGLE_API_KEY o GEMINI_API_KEY en el entorno")

    client = genai.Client(api_key=api_key)

    for model in client.models.list(config={"page_size": 100, "query_base": True}):
        actions = getattr(model, "supported_actions", None)
        print(model.name, actions)


if __name__ == "__main__":
    list_models()
