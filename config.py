

import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

GEMINI_MODEL = "gemini-2.5-flash"


LLM_LOCAL_MODELO = os.getenv("LLM_LOCAL_MODELO", "qwen2.5-coder:14b")
LLM_LOCAL_URL = os.getenv(
    "LLM_LOCAL_URL", "http://localhost:11434/v1/chat/completions"
)


def validar_configuracao() -> None:

    faltando = []
    if not GITHUB_TOKEN or GITHUB_TOKEN.startswith("cole_"):
        faltando.append("GITHUB_TOKEN")

    if faltando:
        raise RuntimeError(
            "As seguintes variáveis não foram configuradas no arquivo .env: "
            + ", ".join(faltando)
            + ". Preencha o .env antes de iniciar o servidor."
        )
