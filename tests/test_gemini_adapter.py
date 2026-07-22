"""Testes do GeminiAdapter.

O teste de contrato e o de tradução rodam SEM rede (a construção do adaptador não
chama a API, e a chamada ao modelo é substituída por um dublê). Um teste real,
que gasta uma chamada de API, fica marcado como `integracao` e só roda sob
demanda.
"""

import pytest

import config
from app.adapters.gemini_adapter import GeminiAdapter
from app.core.ports import LLMPort


def test_gemini_adapter_satisfaz_o_contrato():
    # Construir não faz chamada de rede, então uma chave falsa basta. Se ele pode
    # ser instanciado, é porque implementou toda a LLMPort.
    adaptador = GeminiAdapter(api_key="chave_falsa", modelo="gemini-2.5-flash")
    assert isinstance(adaptador, LLMPort)


def test_avaliar_repassa_o_prompt_e_devolve_o_texto():
    """O adaptador deve mandar o prompt ao modelo e devolver `resposta.text`.

    Substituímos o objeto do modelo por um dublê que registra o prompt recebido
    e devolve um texto conhecido — assim verificamos a tradução sem tocar a rede.
    """

    class _RespostaFalsa:
        text = '{"violacoes": []}'

    class _ModeloFalso:
        def __init__(self):
            self.prompt_recebido = None

        def generate_content(self, prompt):
            self.prompt_recebido = prompt
            return _RespostaFalsa()

    adaptador = GeminiAdapter(api_key="chave_falsa", modelo="gemini-2.5-flash")
    modelo_falso = _ModeloFalso()
    adaptador._modelo = modelo_falso  # injeta o dublê no lugar do cliente real

    resultado = adaptador.avaliar("meu prompt de teste")

    assert modelo_falso.prompt_recebido == "meu prompt de teste"
    assert resultado == '{"violacoes": []}'


@pytest.mark.integracao
def test_avaliar_contra_a_api_real_devolve_texto():
    """Chamada real ao Gemini (gasta cota). Só roda sob `-m integracao`.

    Pede uma resposta trivial e verifica apenas que veio texto não vazio — não
    fixamos o conteúdo, que é não determinístico.
    """
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY.startswith("cole_"):
        pytest.skip("GEMINI_API_KEY não configurada no .env")

    adaptador = GeminiAdapter(
        api_key=config.GEMINI_API_KEY, modelo=config.GEMINI_MODEL
    )
    resposta = adaptador.avaliar("Responda apenas com a palavra: ok")

    assert isinstance(resposta, str)
    assert resposta.strip() != ""
