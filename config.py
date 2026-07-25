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

# Modelo do Gemini. Mantido apenas para comparação experimental: o Gemini serviu
# de andaime durante a construção e não é mais o motor do sistema.
GEMINI_MODEL = "gemini-2.5-flash"

# Modelo de linguagem aberto executado localmente — o motor de verificação do
# sistema. Trocar de modelo (ou de executor) é mudar estes dois valores.
LLM_LOCAL_MODELO = os.getenv("LLM_LOCAL_MODELO", "qwen2.5-coder:14b")
LLM_LOCAL_URL = os.getenv(
    "LLM_LOCAL_URL", "http://localhost:11434/v1/chat/completions"
)


def validar_configuracao() -> None:
    """Garante que as chaves obrigatórias foram preenchidas no .env.

    Chamada na inicialização para falhar cedo, com uma mensagem clara,
    em vez de dar um erro confuso mais adiante na execução.

    A chave do Gemini NÃO é obrigatória: o sistema roda com o modelo local, e a
    chave só é necessária para reproduzir a comparação experimental entre os
    dois modelos.
    """
    faltando = []
    if not GITHUB_TOKEN or GITHUB_TOKEN.startswith("cole_"):
        faltando.append("GITHUB_TOKEN")

    if faltando:
        raise RuntimeError(
            "As seguintes variáveis não foram configuradas no arquivo .env: "
            + ", ".join(faltando)
            + ". Preencha o .env antes de iniciar o servidor."
        )
