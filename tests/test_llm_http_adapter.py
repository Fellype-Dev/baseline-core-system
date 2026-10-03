
import pytest
import requests

from app.adapters.llm_http_adapter import (
    URL_PADRAO,
    ErroDoModelo,
    LLMHttpAdapter,
)
from app.core.ports import LLMPort


def _resposta(conteudo='{"violacoes": []}', **extra):
    class _Falsa:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": conteudo}, **extra}]}

    return _Falsa()


def _capturar(monkeypatch, resposta=None):
    """Substitui o POST e devolve o dicionário com o que foi enviado."""
    capturado = {}

    def _post(url, headers=None, json=None, timeout=None):
        capturado["url"] = url
        capturado["headers"] = headers
        capturado["corpo"] = json
        return resposta if resposta is not None else _resposta()

    monkeypatch.setattr(requests, "post", _post)
    return capturado


def test_adaptador_satisfaz_o_contrato():
    # Construir não faz chamada de rede: se pode ser criado, implementou a porta.
    assert isinstance(LLMHttpAdapter(), LLMPort)


def test_avaliar_envia_o_prompt_e_devolve_o_conteudo(monkeypatch):
    capturado = _capturar(monkeypatch)

    resultado = LLMHttpAdapter(modelo="modelo-teste").avaliar("meu prompt")

    assert resultado == '{"violacoes": []}'
    assert capturado["corpo"]["model"] == "modelo-teste"
    assert capturado["corpo"]["messages"][0]["content"] == "meu prompt"
    # Temperatura zero é requisito da avaliação empírica: sem ela, duas rodadas
    # do mesmo corpus dariam números diferentes.
    assert capturado["corpo"]["temperature"] == 0


# --- Credencial -------------------------------------------------------------
#
# O mesmo adaptador atende um executor nesta máquina e um provedor que hospeda
# modelos abertos. A diferença entre os dois cabe em um cabeçalho.

def test_sem_chave_nao_manda_cabecalho_de_autenticacao(monkeypatch):
    """Executor local não pede credencial, e alguns recusam cabeçalho vazio."""
    capturado = _capturar(monkeypatch)

    LLMHttpAdapter().avaliar("prompt")

    assert capturado["headers"] == {}


def test_com_chave_manda_o_cabecalho_bearer(monkeypatch):
    capturado = _capturar(monkeypatch)

    LLMHttpAdapter(chave="chave-de-teste").avaliar("prompt")

    assert capturado["headers"] == {"Authorization": "Bearer chave-de-teste"}


def test_endereco_do_provedor_e_respeitado(monkeypatch):
    """Trocar executor local por provedor hospedado é mudar a URL."""
    capturado = _capturar(monkeypatch)

    LLMHttpAdapter(url="https://provedor.exemplo/v1/chat/completions").avaliar("x")

    assert capturado["url"] == "https://provedor.exemplo/v1/chat/completions"


# --- Falhas -----------------------------------------------------------------

def test_executor_fora_do_ar_vira_erro_claro(monkeypatch):
    def _post_que_falha(url, headers=None, json=None, timeout=None):
        raise requests.ConnectionError("conexão recusada")

    monkeypatch.setattr(requests, "post", _post_que_falha)

    with pytest.raises(ErroDoModelo, match="não foi possível consultar o modelo"):
        LLMHttpAdapter().avaliar("prompt")


def test_resposta_em_formato_inesperado_vira_erro_claro(monkeypatch):
    class _Estranha:
        def raise_for_status(self):
            pass

        def json(self):
            return {"resultado": "formato que não conhecemos"}

    _capturar(monkeypatch, resposta=_Estranha())

    with pytest.raises(ErroDoModelo, match="formato inesperado"):
        LLMHttpAdapter().avaliar("prompt")


def test_resposta_cortada_por_contexto_vira_erro_claro(monkeypatch):
    """Silenciar isso já custou caro: o prompt truncado some sem avisar."""
    _capturar(monkeypatch, resposta=_resposta(conteudo="", finish_reason="length"))

    with pytest.raises(ErroDoModelo, match="limite de contexto"):
        LLMHttpAdapter().avaliar("prompt")


def test_resposta_vazia_vira_erro_claro(monkeypatch):
    _capturar(monkeypatch, resposta=_resposta(conteudo="   "))

    with pytest.raises(ErroDoModelo, match="resposta vazia"):
        LLMHttpAdapter().avaliar("prompt")


@pytest.mark.integracao
def test_avaliar_contra_o_executor_local_real():
    """Chamada real ao executor local. Pulado se ele não estiver no ar."""
    try:
        requests.get(URL_PADRAO.replace("/v1/chat/completions", "/api/tags"), timeout=3)
    except requests.RequestException:
        pytest.skip("executor local (Ollama) não está em execução")

    resposta = LLMHttpAdapter().avaliar("Responda apenas com a palavra: ok")

    assert isinstance(resposta, str)
    assert resposta.strip() != ""
