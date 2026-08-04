"""
Composition root: o único lugar que monta o sistema inteiro.

Aqui — e somente aqui — os adaptadores concretos (GitHubAdapter e, futuramente,
Qdrant e LLM) são criados e ligados às portas que o núcleo usa. É a "ponta solta"
onde a arquitetura hexagonal se resolve: trocar uma tecnologia significa mudar
uma linha AQUI, e nada mais.

Estado atual: "esqueleto ambulante" (walking skeleton). Recebe o webhook, busca
os arquivos do PR e posta um comentário de teste — ainda sem AST/RAG/LLM.
"""

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

# Observabilidade mínima (F2): sem isto, os logs do pipeline (ex.: falha do
# modelo, registrada com _log.exception) não apareceriam no console do servidor.
logging.basicConfig(level=logging.INFO)

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
# Motor de verificação: modelo de linguagem ABERTO, executado localmente.
# Esta linha é o único ponto do sistema que sabe qual modelo está em uso — a
# migração do Gemini (andaime) para o modelo aberto não exigiu nenhuma alteração
# no núcleo, apenas um novo adaptador implementando a mesma LLMPort.
llm = LocalLLMAdapter(modelo=config.LLM_LOCAL_MODELO, url=config.LLM_LOCAL_URL)
# Observabilidade: o pipeline anuncia cada etapa, e este adaptador as transmite
# aos navegadores conectados ao fluxograma. Note que o núcleo ganhou uma saída
# inteiramente nova sem que uma linha de regra de negócio fosse alterada.
observador = ObservadorSSE()


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
        # Esta função roda em segundo plano (BackgroundTasks): uma exceção aqui
        # não tem para onde propagar e sumiria sem rastro. Registramos com
        # stacktrace para não silenciar a falha (QUA-001).
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
    """Diz se o serviço está no ar e se suas dependências respondem.

    Fica no composition root, e não junto do adaptador de webhook, porque a
    pergunta que ele responde é sobre a INSTALAÇÃO (o modelo está no ar? o
    índice está acessível?) e não sobre o domínio. É o único ponto do sistema
    que legitimamente conhece todas as peças concretas ao mesmo tempo.

    Serve para verificar o serviço de fora, pelo navegador, sem precisar abrir
    um Pull Request para descobrir que alguma peça caiu.
    """
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
