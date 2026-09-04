
import logging

import uvicorn
from fastapi import FastAPI

import config
from app.adapters.github_adapter import GitHubAdapter
from app.adapters.local_llm_adapter import LocalLLMAdapter
from app.adapters.qdrant_adapter import QdrantAdapter
from app.adapters.sse_adapter import ObservadorSSE
from app.api.conhecimento import criar_router_conhecimento
from app.api.eventos import criar_router_eventos
from app.api.webhook import criar_router_webhook
from app.core.models import EventoDeProgresso, PullRequest
from app.core.pipeline import revisar_pull_request

logging.basicConfig(level=logging.INFO)

config.validar_configuracao()

repositorio = GitHubAdapter(token=config.GITHUB_TOKEN)
conhecimento = QdrantAdapter()

llm = LocalLLMAdapter(modelo=config.LLM_LOCAL_MODELO, url=config.LLM_LOCAL_URL)

observador = ObservadorSSE()


def ao_receber_pull_request(pr: PullRequest) -> None:

    print(f"Processando PR #{pr.numero} em {pr.repositorio}...")
    observador.registrar(
        EventoDeProgresso(
            etapa="webhook",
            descricao=f"Pull Request #{pr.numero} recebido de {pr.repositorio}.",
        )
    )
    try:
        revisar_pull_request(pr, repositorio, conhecimento, llm, observador)
        print("  Revisão publicada no PR.")
    except Exception:

        logging.getLogger(__name__).exception(
            "Falha ao revisar o PR #%s de %s.", pr.numero, pr.repositorio
        )


# --- Aplicação web ---
app = FastAPI(title="Revisor Arquitetural de Pull Requests")
app.include_router(
    criar_router_webhook(ao_receber_pull_request, config.GITHUB_WEBHOOK_SECRET)
)
app.include_router(criar_router_eventos(observador))
app.include_router(criar_router_conhecimento(conhecimento))


@app.get("/health")
def verificar_saude() -> dict:

    import requests

    saude = {
        "servico": "no ar",
        "modelo": config.LLM_LOCAL_MODELO,
        "llm": "indisponivel",
        "conhecimento": "indisponivel",
    }

    try:
        endereco = config.LLM_LOCAL_URL.replace("/v1/chat/completions", "/api/tags")
        requests.get(endereco, timeout=5).raise_for_status()
        saude["llm"] = "no ar"
    except Exception:
        logging.getLogger(__name__).warning("Modelo de linguagem não respondeu.")

    try:
        # Uma consulta trivial confirma que o índice está acessível e populado.
        if conhecimento._cliente.collection_exists("regras_arquiteturais"):
            saude["conhecimento"] = "no ar"
    except Exception:
        logging.getLogger(__name__).warning("Banco de conhecimento não respondeu.")

    saude["pronto"] = saude["llm"] == "no ar" and saude["conhecimento"] == "no ar"
    return saude


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
