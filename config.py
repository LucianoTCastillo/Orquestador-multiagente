import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


# Busca .env junto a este archivo, independientemente de la terminal.
PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env", override=False)


def get_run_mode() -> str:
    """Obtiene el modo de ejecución y valida su valor."""
    mode = os.getenv("RUN_MODE", "local").strip().lower()

    if mode not in {"local", "api"}:
        raise ValueError(
            "RUN_MODE debe ser 'local' o 'api'. "
            "Revisá tu configuración."
        )

    return mode


@lru_cache(maxsize=1)
def get_llm():
    """Crea el cliente de OpenAI únicamente en modo API."""
    if get_run_mode() != "api":
        raise RuntimeError(
            "El modelo de OpenAI solo se puede usar con RUN_MODE=api."
        )

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()

    if not api_key:
        raise ValueError(
            "El modo API requiere configurar OPENAI_API_KEY."
        )

    if not model:
        raise ValueError(
            "El modo API requiere configurar OPENAI_MODEL "
            "con un modelo disponible para esa cuenta."
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        timeout=60,
        max_retries=0,
    )