"""
Testes do QdrantAdapter (busca semântica sobre as regras do SDD).

Marcados como `integracao`: carregam o modelo de embeddings e criam um banco
vetorial em disco temporário. São mais lentos que os testes puros.

Rodar apenas os rápidos:   pytest -m "not integracao"
Rodar apenas estes:        pytest -m integracao
"""

import pytest

from app.adapters.qdrant_adapter import QdrantAdapter
from app.core.models import RegraArquitetural
from app.core.ports import ConhecimentoPort

REGRAS = [
    RegraArquitetural(
        identificador="SEG-001",
        titulo="Segredos não podem estar no código-fonte",
        categoria="seguranca",
        severidade="obrigatoria",
        regra=(
            "Tokens de acesso, chaves de API e senhas jamais devem ser escritos "
            "diretamente no código. Devem vir de variáveis de ambiente."
        ),
        motivacao=(
            "Credenciais no código são publicadas no histórico do controle de "
            "versão e precisam ser revogadas."
        ),
        linguagens=("python",),
        aplica_se_a=("**/*.py",),
    ),
    RegraArquitetural(
        identificador="ARQ-003",
        titulo="Adaptadores não devem conter regras de negócio",
        categoria="arquitetura",
        severidade="obrigatoria",
        regra=(
            "A responsabilidade de um adaptador é traduzir entre o mundo externo "
            "e o domínio. Decisões de negócio pertencem ao núcleo."
        ),
        motivacao=(
            "Um adaptador que decide o comportamento do produto prende a regra "
            "de negócio a uma tecnologia e prejudica a testabilidade."
        ),
        linguagens=("python",),
        aplica_se_a=("app/adapters/**",),
    ),
    RegraArquitetural(
        identificador="DOC-001",
        titulo="Não utilizar anos fixos em títulos e documentação",
        categoria="documentacao",
        severidade="recomendada",
        regra=(
            "Títulos e documentação não devem conter anos fixos, pois se tornam "
            "desatualizados. Utilize termos atemporais."
        ),
        motivacao=(
            "Referências temporais fixas exigem manutenção recorrente na virada "
            "do ano."
        ),
        linguagens=("python",),
        aplica_se_a=("**/*.md",),
    ),
]


@pytest.fixture(scope="module")
def adaptador(tmp_path_factory):
    """Um adaptador com as regras já indexadas, reaproveitado por todos os testes.

    Escopo de módulo para carregar o modelo de embeddings uma única vez.
    """
    caminho = tmp_path_factory.mktemp("qdrant_teste")
    instancia = QdrantAdapter(caminho_dados=str(caminho))
    instancia.indexar_regras(REGRAS)
    yield instancia
    instancia.fechar()


@pytest.mark.integracao
def test_adaptador_satisfaz_o_contrato(adaptador):
    assert isinstance(adaptador, ConhecimentoPort)


@pytest.mark.integracao
def test_busca_encontra_regra_sobre_segredos(adaptador):
    # A consulta não repete as palavras da regra: a correspondência é semântica.
    resultado = adaptador.buscar_regras_relevantes(
        "o token de acesso está escrito direto no arquivo python"
    )
    assert resultado[0].identificador == "SEG-001"


@pytest.mark.integracao
def test_busca_encontra_regra_sobre_adaptadores(adaptador):
    resultado = adaptador.buscar_regras_relevantes(
        "um adaptador está tomando decisões de negócio em vez de só traduzir dados"
    )
    assert resultado[0].identificador == "ARQ-003"


@pytest.mark.integracao
def test_busca_respeita_o_limite_de_resultados(adaptador):
    resultado = adaptador.buscar_regras_relevantes("qualquer texto")
    # O adaptador foi configurado para devolver no máximo 3 regras.
    assert len(resultado) <= 3


@pytest.mark.integracao
def test_busca_sem_colecao_indexada_devolve_lista_vazia(tmp_path):
    vazio = QdrantAdapter(caminho_dados=str(tmp_path / "sem_indice"))
    try:
        assert vazio.buscar_regras_relevantes("qualquer coisa") == []
    finally:
        vazio.fechar()
