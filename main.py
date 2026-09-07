
import logging

import uvicorn
from fastapi import FastAPI

import config
from app.adapters.github_adapter import GitHubAdapter
from app.adapters.github_app import FabricaDeGitHub
from app.adapters.local_llm_adapter import LocalLLMAdapter
from app.adapters.qdrant_adapter import QdrantAdapter
from app.adapters.sse_adapter import ObservadorSSE
from app.api.conhecimento import criar_router_conhecimento
from app.api.eventos import criar_router_eventos
from app.api.webhook import criar_router_webhook
from app.core.models import EventoDeProgresso, PullRequest
from app.core.pipeline import merece_revisao, revisar_pull_request

logging.basicConfig(level=logging.INFO)

config.validar_configuracao()

conhecimento = QdrantAdapter()

llm = LocalLLMAdapter(modelo=config.LLM_LOCAL_MODELO, url=config.LLM_LOCAL_URL)

observador = ObservadorSSE()

# A autenticação no GitHub tem duas formas, e a configuração decide qual vale.
# Com App, a credencial depende da instalação que disparou o evento, e o
# adaptador é criado por requisição. Com token pessoal, um único adaptador serve
# a tudo — caminho mantido para desenvolvimento, já que um token só alcança os
# repositórios do próprio dono.
fabrica_de_github = (
    FabricaDeGitHub(config.GITHUB_APP_ID, config.chave_privada_do_app())
    if config.app_configurado()
    else None
)
repositorio_por_token = (
    GitHubAdapter(token=config.GITHUB_TOKEN) if config.GITHUB_TOKEN else None
)


def _repositorio_para(instalacao: int | None):
    """Escolhe com quais credenciais responder a esta entrega.

    Note que a decisão acontece aqui, no composition root, e não no núcleo: o
    pipeline recebe uma `RepositorioPort` e não faz ideia de como ela foi
    autenticada. Foi por isso que passar de "um adaptador para tudo" para "um
    adaptador por instalação" não exigiu alteração alguma na regra de negócio.
    """
    if fabrica_de_github is not None and instalacao is not None:
        return fabrica_de_github.para_instalacao(instalacao)
    if repositorio_por_token is not None:
        return repositorio_por_token
    raise RuntimeError(
        "Entrega sem instalação e sem token pessoal configurado: não há como "
        "autenticar no GitHub."
    )


def ao_receber_pull_request(
    pr: PullRequest, evento: str = "aberto", instalacao: int | None = None
) -> None:

    # A política de quando revisar é do núcleo; aqui só se pergunta a ela.
    if not merece_revisao(evento):
        print(f"PR #{pr.numero}: evento '{evento}' não pede revisão.")
        return

    print(f"Processando PR #{pr.numero} em {pr.repositorio} ({evento})...")
    observador.registrar(
        EventoDeProgresso(
            etapa="webhook",
            descricao=(
                f"Pull Request #{pr.numero} de {pr.repositorio}: {evento}."
            ),
        )
    )
    try:
        repositorio = _repositorio_para(instalacao)
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
