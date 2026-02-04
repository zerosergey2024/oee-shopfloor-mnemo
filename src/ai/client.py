from __future__ import annotations
import os
from openai import OpenAI

def get_openai_client() -> OpenAI:
    # SDK рекомендует брать ключ из env
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def get_model_name() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-5.2")
