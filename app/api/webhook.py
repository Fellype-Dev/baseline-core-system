
import hashlib
import hmac
import json
import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.core.models import PullRequest

_log = logging.getLogger(__name__)

_CABECALHO_DE_ASSINATURA = "X-Hub-Signature-256"


AoReceberPullRequest = Callable[[PullRequest, str, int | None], None]


_EVENTOS_DO_DOMINIO = {
    "opened": "aberto",
    "reopened": "reaberto",
    "synchronize": "atualizado",
    "closed": "fechado",
}


def assinatura_confere(corpo: bytes, assinatura: str | None, segredo: str) -> bool:

    if not assinatura:
        return False

    esperada = "sha256=" + hmac.new(
        segredo.encode("utf-8"), corpo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperada, assinatura)


def criar_router_webhook(
    ao_receber_pr: AoReceberPullRequest, segredo: str | None = None
) -> APIRouter:

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


        evento = _EVENTOS_DO_DOMINIO.get(payload.get("action"))

        if evento is not None and "pull_request" in payload:
            pr = PullRequest(
                repositorio=payload["repository"]["full_name"],
                numero=payload["pull_request"]["number"],
            )


            instalacao = (payload.get("installation") or {}).get("id")

            tarefas.add_task(ao_receber_pr, pr, evento, instalacao)

        return {"status": "recebido"}

    return router
