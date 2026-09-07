

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Credenciais do GitHub App. Um token pessoal só alcança repositórios do próprio
# dono; um App é instalado por cada organização, que concede as permissões no
# repositório dela. É o que permite atender repositórios de terceiros.
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY_PATH = os.getenv("GITHUB_APP_PRIVATE_KEY_PATH")


def chave_privada_do_app() -> str | None:
    """Lê a chave privada do App, se ela estiver configurada.

    A chave fica em arquivo, e não numa variável de ambiente, porque é um bloco
    PEM de várias linhas — formato que arquivos `.env` não representam bem.
    """
    if not GITHUB_APP_PRIVATE_KEY_PATH:
        return None
    return Path(GITHUB_APP_PRIVATE_KEY_PATH).read_text(encoding="utf-8")


def app_configurado() -> bool:
    """Diz se há credenciais de App disponíveis."""
    return bool(GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY_PATH)


GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")

GEMINI_MODEL = "gemini-2.5-flash"


LLM_LOCAL_MODELO = os.getenv("LLM_LOCAL_MODELO", "qwen2.5-coder:14b")
LLM_LOCAL_URL = os.getenv(
    "LLM_LOCAL_URL", "http://localhost:11434/v1/chat/completions"
)


def validar_configuracao() -> None:
    """Garante que há alguma forma de autenticação no GitHub configurada.

    São duas formas alternativas, e basta uma: o GitHub App, que atende
    repositórios de qualquer dono, ou um token pessoal, que só alcança os
    repositórios do próprio dono e serve para desenvolvimento.
    """
    if app_configurado():
        return

    if not GITHUB_TOKEN or GITHUB_TOKEN.startswith("cole_"):
        raise RuntimeError(
            "Nenhuma credencial do GitHub configurada. Defina GITHUB_APP_ID e "
            "GITHUB_APP_PRIVATE_KEY_PATH para usar o GitHub App, ou "
            "GITHUB_TOKEN para autenticação com token pessoal."
        )
