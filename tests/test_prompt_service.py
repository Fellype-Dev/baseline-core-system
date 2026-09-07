
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


# --- Forma completa dos elementos alterados ---------------------------------
#
# Regressão de um falso positivo real: o diff do GitHub traz três linhas de
# contexto e terminou exatamente em `except Exception:`. O corpo do bloco ficou
# de fora, e o modelo — vendo um handler sem corpo — acusou exceção engolida
# num código que registra o erro em log.

CODIGO_COM_HANDLER = (
    "import logging\n"                                        # 1
    "\n"                                                      # 2
    "\n"                                                      # 3
    "def ao_receber(pr, instalacao=None):\n"                  # 4
    "    try:\n"                                              # 5
    "        repositorio = escolher(instalacao)\n"            # 6
    "        revisar(pr, repositorio)\n"                      # 7
    "    except Exception:\n"                                 # 8
    "        logging.getLogger(__name__).exception(\n"        # 9
    "            'Falha ao revisar o PR.'\n"                   # 10
    "        )\n"                                             # 11
)

# O corte cai na linha 8: é o fim do contexto do hunk.
DIFF_QUE_CORTA_NO_EXCEPT = (
    "@@ -4,4 +4,5 @@ def ao_receber(pr, instalacao=None):\n"
    "     try:\n"
    "+        repositorio = escolher(instalacao)\n"
    "         revisar(pr, repositorio)\n"
    "     except Exception:\n"
)


@pytest.fixture
def arquivo_com_handler():
    return ArquivoAlterado(
        caminho="main.py",
        diff=DIFF_QUE_CORTA_NO_EXCEPT,
        conteudo=CODIGO_COM_HANDLER,
    )


@pytest.fixture
def elemento_handler():
    return ElementoDeCodigo(
        tipo="funcao",
        nome="ao_receber",
        assinatura="def ao_receber(pr, instalacao=None)",
        linha_inicio=4,
        linha_fim=11,
    )


def test_diff_sozinho_esconde_o_corpo_do_handler(arquivo_com_handler):
    """Confirma a premissa: sem o corpo, a evidência não chega ao modelo."""
    assert "logging.getLogger" not in arquivo_com_handler.diff


def test_corpo_completo_traz_o_que_o_diff_cortou(
    arquivo_com_handler, elemento_handler, regra
):
    prompt = montar_prompt(arquivo_com_handler, [elemento_handler], [regra])
    assert "logging.getLogger(__name__).exception(" in prompt


def test_corpo_pode_ser_desligado_para_comparacao(
    arquivo_com_handler, elemento_handler, regra
):
    """A chave existe para medir as duas configurações no mesmo conjunto."""
    prompt = montar_prompt(
        arquivo_com_handler, [elemento_handler], [regra], incluir_corpo=False
    )
    assert "logging.getLogger" not in prompt


def test_corpo_vem_com_as_linhas_numeradas(
    arquivo_com_handler, elemento_handler, regra
):
    """O modelo aponta por número; contar linhas é trabalho que ele faz mal."""
    prompt = montar_prompt(arquivo_com_handler, [elemento_handler], [regra])

    assert "   4 | def ao_receber(pr, instalacao=None):" in prompt
    assert "   8 |     except Exception:" in prompt


def test_numero_da_linha_e_pedido_quando_ha_listagem_numerada(
    arquivo_com_handler, elemento_handler, regra
):
    prompt = montar_prompt(arquivo_com_handler, [elemento_handler], [regra])
    assert '"linha"' in prompt


def test_numero_da_linha_nao_e_pedido_sem_listagem(arquivo, elementos, regra):
    """Cobrar um número que não foi oferecido descartaria achado legítimo."""
    prompt = montar_prompt(arquivo, elementos, [regra], incluir_corpo=False)
    assert '"linha"' not in prompt


def test_sem_conteudo_o_prompt_segue_apenas_com_o_diff(elementos, regra):
    """Linguagem sem AST ou conteúdo indisponível: degrada, não quebra."""
    arquivo = ArquivoAlterado(caminho="script.js", diff="@@ -1 +1 @@\n+var x = 1;\n")
    prompt = montar_prompt(arquivo, elementos, [regra])

    assert "var x = 1;" in prompt
    assert "Forma completa" not in prompt


def test_intervalo_invalido_nao_produz_trecho_errado(regra):
    """Melhor nenhum corpo do que um recorte silenciosamente deslocado."""
    arquivo = ArquivoAlterado(
        caminho="curto.py", diff="@@ -1 +1 @@\n+x = 1\n", conteudo="x = 1\n"
    )
    fora_do_arquivo = ElementoDeCodigo(
        tipo="funcao", nome="f", assinatura="def f()", linha_inicio=50, linha_fim=90
    )
    prompt = montar_prompt(arquivo, [fora_do_arquivo], [regra])

    assert "Forma completa" not in prompt


def test_metodo_alterado_dispensa_a_classe_inteira(regra):
    """A classe envolve o método; mandar as duas duplicaria o mesmo código."""
    codigo = (
        "class Servico:\n"                    # 1
        "    def intocado(self):\n"           # 2
        "        return 'nao mexi aqui'\n"    # 3
        "\n"                                  # 4
        "    def alterado(self):\n"           # 5
        "        return 'mudou'\n"            # 6
    )
    arquivo = ArquivoAlterado(
        caminho="app/servico.py",
        diff="@@ -5,2 +5,2 @@\n+        return 'mudou'\n",
        conteudo=codigo,
    )
    classe = ElementoDeCodigo(
        tipo="classe", nome="Servico", assinatura="class Servico",
        linha_inicio=1, linha_fim=6,
    )
    metodo = ElementoDeCodigo(
        tipo="metodo", nome="Servico.alterado", assinatura="def alterado(self)",
        linha_inicio=5, linha_fim=6,
    )

    prompt = montar_prompt(arquivo, [classe, metodo], [regra])
    corpos = prompt[prompt.index("Forma completa"):]

    assert "return 'mudou'" in corpos
    assert "nao mexi aqui" not in corpos


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
