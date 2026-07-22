"""Testes da montagem do prompt de avaliação (feature D1).

Como a função é lógica pura, todos os testes rodam sem rede: montam objetos de
domínio de exemplo e inspecionam o texto resultante.
"""

import json

import pytest

from app.core.models import ArquivoAlterado, ElementoDeCodigo, RegraArquitetural
from app.services.prompt_service import montar_prompt


@pytest.fixture
def arquivo():
    return ArquivoAlterado(
        caminho="app/core/ports.py",
        diff=(
            "@@ -1,2 +1,3 @@\n"
            " from app.adapters.github_adapter import GitHubAdapter\n"
            "+API_KEY = \"sk-segredo-hardcoded\"\n"
        ),
    )


@pytest.fixture
def elementos():
    return [
        ElementoDeCodigo(
            tipo="funcao",
            nome="carregar",
            assinatura="def carregar(caminho: str) -> str",
            linha_inicio=2,
            linha_fim=3,
        )
    ]


@pytest.fixture
def regra():
    return RegraArquitetural(
        identificador="SEG-001",
        titulo="Sem segredos no código",
        categoria="seguranca",
        severidade="obrigatoria",
        regra="Segredos não podem ser escritos diretamente no código.",
        motivacao="Um segredo versionado vaza para todo o histórico do git.",
        como_identificar="Atribuições de strings que parecem tokens ou chaves.",
        exemplo_incorreto='API_KEY = "sk-1234"',
        exemplo_correto='API_KEY = os.getenv("API_KEY")',
    )


def test_prompt_inclui_identificador_e_titulo_da_regra(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra])
    assert "SEG-001" in prompt
    assert "Sem segredos no código" in prompt


def test_prompt_inclui_motivacao_para_feedback_didatico(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra])
    assert regra.motivacao in prompt


def test_prompt_inclui_caminho_e_diff_do_arquivo(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra])
    assert "app/core/ports.py" in prompt
    # O corpo (que carrega a violação de SEG-001) vem do diff, não da assinatura.
    assert "sk-segredo-hardcoded" in prompt


def test_prompt_inclui_assinatura_dos_elementos_alterados(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra])
    assert "def carregar(caminho: str) -> str" in prompt


def test_exemplos_omitidos_por_padrao(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra])
    assert "sk-1234" not in prompt
    assert 'os.getenv("API_KEY")' not in prompt


def test_exemplos_incluidos_quando_solicitado(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra], incluir_exemplos=True)
    assert "sk-1234" in prompt
    assert 'os.getenv("API_KEY")' in prompt


def test_pede_saida_em_json(arquivo, elementos, regra):
    prompt = montar_prompt(arquivo, elementos, [regra])
    assert "JSON" in prompt
    assert '"violacoes"' in prompt


def test_robusto_sem_elementos_ainda_mostra_diff(arquivo, regra):
    # Arquivo cuja mudança não caiu em nenhum elemento estrutural: o diff basta.
    prompt = montar_prompt(arquivo, [], [regra])
    assert "sk-segredo-hardcoded" in prompt
    assert "Nenhum elemento estrutural" in prompt


def test_robusto_sem_regras(arquivo, elementos):
    prompt = montar_prompt(arquivo, elementos, [])
    assert "Nenhuma regra aplicável" in prompt


def test_formato_de_saida_e_json_parseavel(arquivo, elementos, regra):
    # Extrai o objeto de exemplo do prompt e confirma que é JSON válido, para
    # garantir que a estrutura pedida ao modelo bate com o que a D3 vai parsear.
    prompt = montar_prompt(arquivo, elementos, [regra])
    inicio = prompt.index("{", prompt.index("Formato da resposta"))

    profundidade = 0
    fim = inicio
    for i in range(inicio, len(prompt)):
        if prompt[i] == "{":
            profundidade += 1
        elif prompt[i] == "}":
            profundidade -= 1
            if profundidade == 0:
                fim = i + 1
                break

    objeto = json.loads(prompt[inicio:fim])
    assert "violacoes" in objeto
