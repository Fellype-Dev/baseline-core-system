"""Testes do LocalLLMAdapter.

Contrato e tradução rodam sem rede (a chamada HTTP é substituída por um dublê).
O teste contra o modelo real fica marcado como `integracao` e é pulado quando o
executor local não está no ar.
"""

import pytest
import requests

from app.adapters.local_llm_adapter import (
    URL_PADRAO,
    ErroDoModeloLocal,
    LocalLLMAdapter,
)
from app.core.ports import LLMPort


def test_local_llm_adapter_satisfaz_o_contrato():
    # Construir não faz chamada de rede: se pode ser criado, implementou a porta.
    assert isinstance(LocalLLMAdapter(), LLMPort)


def test_avaliar_envia_o_prompt_e_devolve_o_conteudo(monkeypatch):
    capturado = {}

    class _RespostaFalsa:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": '{"violacoes": []}'}}]}

    def _post_falso(url, json, timeout):
        capturado["url"] = url
        capturado["corpo"] = json
        return _RespostaFalsa()

    monkeypatch.setattr(requests, "post", _post_falso)

    resultado = LocalLLMAdapter(modelo="modelo-teste").avaliar("meu prompt")

    assert resultado == '{"violacoes": []}'
    assert capturado["corpo"]["model"] == "modelo-teste"
    assert capturado["corpo"]["messages"][0]["content"] == "meu prompt"
    # Temperatura zero é requisito da avaliação empírica: sem ela, duas rodadas
    # do mesmo corpus dariam números diferentes.
    assert capturado["corpo"]["temperature"] == 0


def test_executor_fora_do_ar_vira_erro_claro(monkeypatch):
    def _post_que_falha(url, json, timeout):
        raise requests.ConnectionError("conexão recusada")

    monkeypatch.setattr(requests, "post", _post_que_falha)

    with pytest.raises(ErroDoModeloLocal, match="modelo local"):
        LocalLLMAdapter().avaliar("prompt")


def test_resposta_em_formato_inesperado_vira_erro_claro(monkeypatch):
    class _RespostaEstranha:
        def raise_for_status(self):
            pass

        def json(self):
            return {"resultado": "formato que não conhecemos"}

    monkeypatch.setattr(requests, "post", lambda url, json, timeout: _RespostaEstranha())

    with pytest.raises(ErroDoModeloLocal, match="formato inesperado"):
        LocalLLMAdapter().avaliar("prompt")


@pytest.mark.integracao
def test_avaliar_contra_o_modelo_local_real():
    """Chamada real ao executor local. Pulado se ele não estiver no ar."""
    try:
        requests.get(URL_PADRAO.replace("/v1/chat/completions", "/api/tags"), timeout=3)
    except requests.RequestException:
        pytest.skip("executor local (Ollama) não está em execução")

    resposta = LocalLLMAdapter().avaliar("Responda apenas com a palavra: ok")

    assert isinstance(resposta, str)
    assert resposta.strip() != ""
