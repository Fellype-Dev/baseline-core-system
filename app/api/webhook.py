
import hashlib
import hmac
import json
import logging
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.core.models import PullRequest

_log = logging.getLogger(__name__)

_CABECALHO_DE_ASSINATURA = "X-Hub-Signature-256"

# Ação executada quando um Pull Request chega: recebe o PR, o que aconteceu com
# ele em vocabulário do domínio, e o identificador da instalação do App que
# originou a entrega (nulo quando a autenticação é por token pessoal). Quem
# fornece a ação concreta é o composition root.
AoReceberPullRequest = Callable[[PullRequest, str, int | None], None]

# Tradução do vocabulário do GitHub para o do domínio. Uma ação sem
# correspondência aqui não é traduzível, e por isso não atravessa o adaptador —
# não há como falar de um `labeled` em termos de domínio. Decidir o que fazer
# com o que É traduzível não cabe a este arquivo: `fechado` passa adiante, e é
# o núcleo que sabe não haver revisão a fazer.
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

            # Entregas de um GitHub App identificam a instalação que as originou,
            # e é ela que determina com quais credenciais responder. O conceito é
            # do GitHub, então fica aqui, no adaptador de entrada, sem alcançar o
            # vocabulário do domínio. Entregas por token pessoal não trazem o
            # campo, e nesse caso o valor é nulo.
            instalacao = (payload.get("installation") or {}).get("id")

            tarefas.add_task(ao_receber_pr, pr, evento, instalacao)

        return {"status": "recebido"}

    return router
