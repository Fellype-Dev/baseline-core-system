"""
Adaptador de ENTRADA: recebe o webhook do GitHub e o traduz para o domínio.

Este é o outro lado do hexágono em relação ao GitHubAdapter. Aqui o GitHub é o
CONDUTOR: ele chama a nossa aplicação, disparando um POST quando um Pull Request
acontece. O papel deste adaptador é apenas entender o formato do GitHub e
convertê-lo num PullRequest do domínio, delegando o processamento ao núcleo.

Ele NÃO decide o que fazer com o PR — recebe essa ação de fora (do composition
root, o main.py). Assim o adaptador de entrada permanece desacoplado do miolo.
"""

import hashlib
import hmac
import json
import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.core.models import PullRequest

_log = logging.getLogger(__name__)

# Cabeçalho em que o GitHub envia a assinatura do corpo da requisição.
_CABECALHO_DE_ASSINATURA = "X-Hub-Signature-256"

# Assinatura da ação executada quando um PR chega: recebe um PullRequest e age.
# Quem fornece a ação concreta é o composition root, não este adaptador.
AoReceberPullRequest = Callable[[PullRequest], None]


def assinatura_confere(corpo: bytes, assinatura: str | None, segredo: str) -> bool:
    """Confere se o corpo recebido foi assinado com o segredo combinado.

    O GitHub assina cada entrega com HMAC-SHA256 sobre o corpo bruto — por isso
    a verificação acontece antes de interpretar o JSON: reserializar o conteúdo
    produziria bytes diferentes e invalidaria a assinatura.

    A comparação usa `compare_digest`, que leva o mesmo tempo independentemente
    de onde os valores divergem. Uma comparação comum vazaria, pelo tempo de
    resposta, quantos caracteres iniciais estavam corretos.
    """
    if not assinatura:
        return False

    esperada = "sha256=" + hmac.new(
        segredo.encode("utf-8"), corpo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperada, assinatura)


def criar_router_webhook(
    ao_receber_pr: AoReceberPullRequest, segredo: str | None = None
) -> APIRouter:
    """Cria o router do webhook já ligado à ação que trata o Pull Request.

    Quando `segredo` é informado, só entregas assinadas por ele são aceitas.
    Sem segredo, a verificação é desligada e um aviso é registrado: o endereço
    fica público e qualquer um pode acionar a revisão.
    """
    router = APIRouter()

    if not segredo:
        _log.warning(
            "Webhook sem segredo configurado: as entregas NAO serao verificadas. "
            "Defina GITHUB_WEBHOOK_SECRET no .env e o mesmo valor no webhook do "
            "repositorio."
        )

    @router.post("/webhook")
    async def receber_evento_github(
        request: Request, tarefas: BackgroundTasks
    ) -> dict:
        corpo = await request.body()

        if segredo:
            assinatura = request.headers.get(_CABECALHO_DE_ASSINATURA)
            if not assinatura_confere(corpo, assinatura, segredo):
                _log.warning("Entrega recusada: assinatura ausente ou invalida.")
                raise HTTPException(status_code=401, detail="assinatura invalida")

        payload = json.loads(corpo)

        # O GitHub envia muitos tipos de evento pelo mesmo endereço.
        # Só reagimos à ABERTURA de um Pull Request.
        if payload.get("action") == "opened" and "pull_request" in payload:
            pr = PullRequest(
                repositorio=payload["repository"]["full_name"],
                numero=payload["pull_request"]["number"],
            )
            # Resiliência (E2): a revisão (AST + RAG + LLM) pode levar segundos.
            # O GitHub considera o webhook falho se a resposta demorar, então
            # agendamos o trabalho para DEPOIS da resposta e devolvemos 200 já.
            tarefas.add_task(ao_receber_pr, pr)

        return {"status": "recebido"}

    return router
