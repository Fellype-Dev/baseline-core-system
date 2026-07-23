"""
Composition root: o único lugar que monta o sistema inteiro.

Aqui — e somente aqui — os adaptadores concretos (GitHubAdapter e, futuramente,
Qdrant e LLM) são criados e ligados às portas que o núcleo usa. É a "ponta solta"
onde a arquitetura hexagonal se resolve: trocar uma tecnologia significa mudar
uma linha AQUI, e nada mais.

Estado atual: "esqueleto ambulante" (walking skeleton). Recebe o webhook, busca
os arquivos do PR e posta um comentário de teste — ainda sem AST/RAG/LLM.
"""

import uvicorn
from fastapi import FastAPI

import config
from app.adapters.gemini_adapter import GeminiAdapter
from app.adapters.github_adapter import GitHubAdapter
from app.adapters.qdrant_adapter import QdrantAdapter
from app.api.webhook import criar_router_webhook
from app.core.models import PullRequest
from app.core.pipeline import revisar_pull_request

# Falha cedo, com mensagem clara, se as chaves não estiverem no .env.
config.validar_configuracao()

# --- Montagem das dependências (o "wiring" da arquitetura) ---
# Os três adaptadores concretos nascem AQUI e são usados apenas através das suas
# portas. Trocar qualquer tecnologia (GitHub, Qdrant, Gemini) significa mudar
# uma destas linhas — e nada mais no sistema.
#
# O QdrantAdapter carrega o modelo de embeddings na criação; por isso é montado
# uma única vez, na inicialização, e reaproveitado a cada Pull Request.
repositorio = GitHubAdapter(token=config.GITHUB_TOKEN)
conhecimento = QdrantAdapter()
llm = GeminiAdapter(api_key=config.GEMINI_API_KEY, modelo=config.GEMINI_MODEL)


def ao_receber_pull_request(pr: PullRequest) -> None:
    """Liga o evento de PR ao pipeline do núcleo, injetando as portas.

    Esta função é a "ação" que o adaptador de webhook dispara. Ela apenas
    entrega ao núcleo (o pipeline) os adaptadores já montados — nenhuma regra de
    negócio mora aqui.

    Observação: o processamento é síncrono. Movê-lo para fora do laço de eventos
    (BackgroundTasks) para responder ao GitHub imediatamente é a feature E2
    (resiliência).
    """
    print(f"Processando PR #{pr.numero} em {pr.repositorio}...")
    revisar_pull_request(pr, repositorio, conhecimento, llm)
    print("  Revisão publicada no PR.")


# --- Aplicação web ---
app = FastAPI(title="Revisor Arquitetural de Pull Requests")
app.include_router(criar_router_webhook(ao_receber_pull_request))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
