"""Testes da geração de diff do harness de avaliação.

O que se verifica aqui não é o formato pelo formato: é a fidelidade da medição.
Um corpus que entrega o arquivo inteiro ao modelo mede um sistema diferente do
que roda em produção, e foi assim que um falso positivo real passou despercebido
por duas rodadas de avaliação.
"""

from avaliacao.executar import diff_do_caso, montar_diff, montar_diff_parcial

BASE = (
    "def publicar(pr, texto, cliente):\n"
    "    if not texto:\n"
    "        return False\n"
    "\n"
    "    try:\n"
    "        mensagem = cliente.montar(pr, texto)\n"
    "        cliente.enviar(mensagem)\n"
    "    except Exception:\n"
    "        pass\n"
    "    return True\n"
)

MODIFICADO = BASE.replace(
    "    try:\n        mensagem",
    "    try:\n        texto = texto.strip()\n        mensagem",
)


def test_diff_parcial_nao_traz_o_arquivo_inteiro():
    diff = montar_diff_parcial(BASE, MODIFICADO)
    assert "def publicar(pr, texto, cliente):" not in diff


def test_diff_parcial_omite_o_que_passa_da_janela_de_contexto():
    """É este corte que esconde evidência do modelo — e o corpus precisa dele."""
    diff = montar_diff_parcial(BASE, MODIFICADO)

    assert "except Exception:" in diff  # última linha de contexto
    assert "pass" not in diff  # corpo do handler: ficou de fora


def test_diff_parcial_dispensa_os_cabecalhos_de_arquivo():
    """A API do GitHub entrega o patch sem `---`/`+++`; o corpus copia isso."""
    diff = montar_diff_parcial(BASE, MODIFICADO)

    assert not diff.startswith("---")
    assert "+++" not in diff
    assert diff.startswith("@@")


def test_diff_parcial_marca_a_linha_adicionada():
    diff = montar_diff_parcial(BASE, MODIFICADO)
    assert "+        texto = texto.strip()" in diff


def test_caso_sem_base_continua_sendo_arquivo_novo():
    """Compatibilidade: os dois corpora anteriores não declaram `codigo_base`."""
    caso = {"caminho": "app/novo.py", "codigo": "x = 1\ny = 2\n"}
    diff = diff_do_caso(caso)

    assert diff == montar_diff(caso["codigo"])
    assert "+x = 1" in diff
    assert "+y = 2" in diff


def test_caso_com_base_gera_diff_parcial():
    caso = {"caminho": "app/publicador.py", "codigo_base": BASE, "codigo": MODIFICADO}
    assert diff_do_caso(caso) == montar_diff_parcial(BASE, MODIFICADO)
