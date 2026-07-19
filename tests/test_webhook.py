"""Testes do adaptador de entrada (tradução do webhook do GitHub para o domínio)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.webhook import criar_router_webhook
from app.core.models import PullRequest


def _cliente_com_captura():
    """Monta um app de teste cuja ação apenas registra os PRs recebidos."""
    recebidos: list[PullRequest] = []
    app = FastAPI()
    app.include_router(criar_router_webhook(recebidos.append))
    return TestClient(app), recebidos


def test_pr_aberto_e_traduzido_para_o_dominio():
    cliente, recebidos = _cliente_com_captura()

    resposta = cliente.post(
        "/webhook",
        json={
            "action": "opened",
            "repository": {"full_name": "dono/repo"},
            "pull_request": {"number": 42},
        },
    )

    assert resposta.status_code == 200
    assert recebidos == [PullRequest("dono/repo", 42)]


def test_evento_que_nao_e_abertura_e_ignorado():
    cliente, recebidos = _cliente_com_captura()

    cliente.post("/webhook", json={"action": "closed"})

    assert recebidos == []
