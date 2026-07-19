"""
Adaptador de ENTRADA: recebe o webhook do GitHub e o traduz para o domínio.

Este é o outro lado do hexágono em relação ao GitHubAdapter. Aqui o GitHub é o
CONDUTOR: ele chama a nossa aplicação, disparando um POST quando um Pull Request
acontece. O papel deste adaptador é apenas entender o formato do GitHub e
convertê-lo num PullRequest do domínio, delegando o processamento ao núcleo.

Ele NÃO decide o que fazer com o PR — recebe essa ação de fora (do composition
root, o main.py). Assim o adaptador de entrada permanece desacoplado do miolo.
"""

from collections.abc import Callable

from fastapi import APIRouter, Request

from app.core.models import PullRequest

# Assinatura da ação executada quando um PR chega: recebe um PullRequest e age.
# Quem fornece a ação concreta é o composition root, não este adaptador.
AoReceberPullRequest = Callable[[PullRequest], None]


def criar_router_webhook(ao_receber_pr: AoReceberPullRequest) -> APIRouter:
    """Cria o router do webhook já ligado à ação que trata o Pull Request."""
    router = APIRouter()

    @router.post("/webhook")
    async def receber_evento_github(request: Request) -> dict:
        payload = await request.json()

        # O GitHub envia muitos tipos de evento pelo mesmo endereço.
        # Só reagimos à ABERTURA de um Pull Request.
        if payload.get("action") == "opened" and "pull_request" in payload:
            pr = PullRequest(
                repositorio=payload["repository"]["full_name"],
                numero=payload["pull_request"]["number"],
            )
            ao_receber_pr(pr)

        # Responder rápido com 200 é importante: o GitHub espera a confirmação
        # de recebimento e considera o webhook falho se demorar demais.
        return {"status": "recebido"}

    return router
