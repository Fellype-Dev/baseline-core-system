"""
Carregamento centralizado das configurações do projeto.

Lê as variáveis do arquivo .env e as disponibiliza para o resto do sistema.
Manter tudo aqui evita espalhar chaves e facilita trocar valores no futuro.
"""

import os
from dotenv import load_dotenv

# Lê o arquivo .env e injeta as variáveis no ambiente do processo.
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Modelo do Gemini usado na revisão. Centralizado aqui para troca fácil depois.
GEMINI_MODEL = "gemini-2.5-flash"


def validar_configuracao() -> None:
    """Garante que as chaves obrigatórias foram preenchidas no .env.

    Chamada na inicialização para falhar cedo, com uma mensagem clara,
    em vez de dar um erro confuso mais adiante na execução.
    """
    faltando = []
    if not GITHUB_TOKEN or GITHUB_TOKEN.startswith("cole_"):
        faltando.append("GITHUB_TOKEN")
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("cole_"):
        faltando.append("GEMINI_API_KEY")

    if faltando:
        raise RuntimeError(
            "As seguintes variáveis não foram configuradas no arquivo .env: "
            + ", ".join(faltando)
            + ". Preencha o .env antes de iniciar o servidor."
        )
