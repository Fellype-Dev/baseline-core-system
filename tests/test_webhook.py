"""Testes do adaptador de entrada (tradução do webhook do GitHub para o domínio)."""

import hashlib
import hmac
import json

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


# --- Verificação da assinatura ----------------------------------------------

SEGREDO = "segredo-de-teste"

PAYLOAD = {
    "action": "opened",
    "repository": {"full_name": "dono/repo"},
    "pull_request": {"number": 7},
}


def _cliente_protegido():
    recebidos: list[PullRequest] = []
    app = FastAPI()
    app.include_router(criar_router_webhook(recebidos.append, SEGREDO))
    return TestClient(app), recebidos


def _assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(
        segredo.encode("utf-8"), corpo, hashlib.sha256
    ).hexdigest()


def test_entrega_assinada_corretamente_e_aceita():
    cliente, recebidos = _cliente_protegido()
    corpo = json.dumps(PAYLOAD).encode("utf-8")

    resposta = cliente.post(
        "/webhook",
        content=corpo,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _assinar(corpo),
        },
    )

    assert resposta.status_code == 200
    assert recebidos == [PullRequest("dono/repo", 7)]


def test_entrega_sem_assinatura_e_recusada():
    cliente, recebidos = _cliente_protegido()

    resposta = cliente.post("/webhook", json=PAYLOAD)

    assert resposta.status_code == 401
    assert recebidos == []


def test_entrega_com_assinatura_de_outro_segredo_e_recusada():
    cliente, recebidos = _cliente_protegido()
    corpo = json.dumps(PAYLOAD).encode("utf-8")

    resposta = cliente.post(
        "/webhook",
        content=corpo,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _assinar(corpo, "segredo-errado"),
        },
    )

    assert resposta.status_code == 401
    assert recebidos == []


def test_corpo_adulterado_invalida_a_assinatura():
    """Assinatura válida para outro conteúdo não pode liberar a entrega."""
    cliente, recebidos = _cliente_protegido()
    original = json.dumps(PAYLOAD).encode("utf-8")
    adulterado = json.dumps(
        {**PAYLOAD, "pull_request": {"number": 999}}
    ).encode("utf-8")

    resposta = cliente.post(
        "/webhook",
        content=adulterado,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": _assinar(original),
        },
    )

    assert resposta.status_code == 401
    assert recebidos == []


def test_sem_segredo_configurado_a_verificacao_fica_desligada():
    """Compatibilidade: instalações sem segredo continuam funcionando."""
    cliente, recebidos = _cliente_com_captura()

    resposta = cliente.post("/webhook", json=PAYLOAD)

    assert resposta.status_code == 200
    assert recebidos == [PullRequest("dono/repo", 7)]
