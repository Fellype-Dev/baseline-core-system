
import pytest

from app.core.models import Violacao
from app.services.result_service import (
    RespostaInvalidaError,
    anexar_evidencia,
    formatar_comentario,
    formatar_erro_de_sintaxe,
    interpretar_violacoes,
    montar_comentario_de_avaliacao,
)


# --- interpretar_violacoes --------------------------------------------------

def test_interpreta_json_puro():
    resposta = '{"violacoes": [{"regra": "SEG-001", "elemento": "carregar", "explicacao": "segredo no código"}]}'
    violacoes = interpretar_violacoes(resposta)
    assert violacoes == [
        Violacao(regra="SEG-001", explicacao="segredo no código", elemento="carregar")
    ]


def test_interpreta_lista_vazia():
    assert interpretar_violacoes('{"violacoes": []}') == []


def test_tolera_cerca_de_codigo_markdown():
    # O modelo embrulhou o JSON em ```json ... ```, apesar da instrução.
    resposta = '```json\n{"violacoes": []}\n```'
    assert interpretar_violacoes(resposta) == []


def test_tolera_texto_em_volta_do_json():
    resposta = 'Claro! Aqui está a análise:\n{"violacoes": []}\nEspero ter ajudado.'
    assert interpretar_violacoes(resposta) == []


def test_elemento_e_opcional():
    resposta = '{"violacoes": [{"regra": "ARQ-001", "explicacao": "núcleo importa adaptador"}]}'
    (violacao,) = interpretar_violacoes(resposta)
    assert violacao.regra == "ARQ-001"
    assert violacao.elemento == ""


def test_resposta_sem_json_levanta_erro():
    with pytest.raises(RespostaInvalidaError):
        interpretar_violacoes("desculpe, não consegui analisar o código")


def test_json_sem_chave_violacoes_levanta_erro():
    with pytest.raises(RespostaInvalidaError):
        interpretar_violacoes('{"resultado": "ok"}')


# --- formatar_comentario ----------------------------------------------------

def test_comentario_de_aprovacao_quando_sem_violacoes():
    comentario = formatar_comentario([])
    assert "✅" in comentario
    assert "Nenhuma violação" in comentario


def test_comentario_lista_cada_violacao_com_o_id_da_regra():
    violacoes = [
        Violacao(regra="SEG-001", explicacao="segredo hardcoded", elemento="carregar"),
        Violacao(regra="ARQ-001", explicacao="núcleo importa adaptador"),
    ]
    comentario = formatar_comentario(violacoes)
    assert "2 violações encontradas" in comentario
    assert "SEG-001" in comentario
    assert "segredo hardcoded" in comentario
    assert "`carregar`" in comentario  # elemento presente vira código inline
    assert "ARQ-001" in comentario


def test_singular_para_uma_violacao():
    comentario = formatar_comentario(
        [Violacao(regra="SEG-001", explicacao="x")]
    )
    assert "1 violação encontrada" in comentario


# --- formatar_erro_de_sintaxe -----------------------------------------------

def test_erro_de_sintaxe_cita_a_linha_e_a_mensagem():
    comentario = formatar_erro_de_sintaxe(12, "'(' was never closed")
    assert "linha 12" in comentario
    assert "'(' was never closed" in comentario
    assert "Erro de sintaxe" in comentario


def test_erro_de_sintaxe_sem_linha_conhecida():
    comentario = formatar_erro_de_sintaxe(None, "invalid syntax")
    assert "linha" not in comentario.split("não pôde ser interpretado")[1][:20]
    assert "invalid syntax" in comentario


# --- montar_comentario_de_avaliacao (D3 completo) ---------------------------

def test_fim_a_fim_gera_comentario_de_violacao():
    resposta = '{"violacoes": [{"regra": "SEG-001", "elemento": "", "explicacao": "chave exposta"}]}'
    comentario = montar_comentario_de_avaliacao(resposta)
    assert "SEG-001" in comentario
    assert "chave exposta" in comentario


def test_resposta_irrecuperavel_vira_comentario_de_erro_honesto():
    comentario = montar_comentario_de_avaliacao("lorem ipsum sem json nenhum")
    assert "⚠️" in comentario
    assert "indisponível" in comentario
    # Não inventa violações: nenhum identificador de regra é citado.
    assert "SEG-" not in comentario
    assert "ARQ-" not in comentario




# --- Conferência da linha apontada ------------------------------------------
#
# O modelo informa o NÚMERO da linha; o texto é buscado no código pelo próprio
# sistema. Regressão de dois defeitos observados em medição: apontamentos que
# descreviam código inexistente, e respostas inteiras perdidas porque a linha
# citada continha aspas duplas e o modelo quebrava o JSON para acomodá-las.

CODIGO = (
    "import logging\n"                                                # 1
    "\n"                                                              # 2
    "\n"                                                              # 3
    "def ao_receber(pr, instalacao=None):\n"                          # 4
    "    cabecalhos = {\"Authorization\": \"Bearer sk_live_123\"}\n"   # 5
    "    try:\n"                                                      # 6
    "        revisar(pr, instalacao, cabecalhos)\n"                   # 7
    "    except Exception:\n"                                         # 8
    "        logging.getLogger(__name__).exception('Falhou.')\n"      # 9
)


def _violacao(linha) -> Violacao:
    return Violacao(regra="QUA-001", explicacao="exceção ampla", linha=linha)


def test_linha_valida_recebe_o_texto_vindo_do_codigo():
    (violacao,) = anexar_evidencia([_violacao(8)], CODIGO)
    assert violacao.evidencia == "except Exception:"


def test_linha_fora_do_arquivo_e_descartada():
    assert anexar_evidencia([_violacao(99)], CODIGO) == []


def test_linha_ausente_e_descartada():
    """Zero é o que sobra quando o modelo não aponta nada."""
    assert anexar_evidencia([_violacao(0)], CODIGO) == []


def test_linha_em_branco_nao_sustenta_apontamento():
    assert anexar_evidencia([_violacao(2)], CODIGO) == []


def test_numero_vindo_como_texto_e_aceito():
    resposta = '{"violacoes": [{"regra": "QUA-001", "linha": "8", "explicacao": "x"}]}'
    (violacao,) = interpretar_violacoes(resposta)
    assert violacao.linha == 8


def test_numero_ilegivel_vira_zero_em_vez_de_quebrar():
    resposta = '{"violacoes": [{"regra": "QUA-001", "linha": "oitava", "explicacao": "x"}]}'
    (violacao,) = interpretar_violacoes(resposta)
    assert violacao.linha == 0


def test_sem_codigo_para_conferir_nada_e_descartado():
    """Degrada para o comportamento anterior em vez de apagar a revisão."""
    violacoes = [_violacao(8)]
    assert anexar_evidencia(violacoes, "") == violacoes


def test_linha_com_aspas_duplas_atravessa_intacta():
    """Era o que quebrava o JSON quando se pedia o trecho copiado.

    O número atravessa a resposta sem drama, e o texto — que nunca passou pelo
    modelo — chega ao comentário com as aspas no lugar.
    """
    resposta = '{"violacoes": [{"regra": "SEG-001", "linha": 5, "explicacao": "segredo"}]}'
    comentario = montar_comentario_de_avaliacao(
        resposta, frozenset({"SEG-001"}), codigo_revisado=CODIGO
    )
    assert 'cabecalhos = {"Authorization": "Bearer sk_live_123"}' in comentario


def test_comentario_mostra_numero_e_texto_da_linha():
    resposta = '{"violacoes": [{"regra": "QUA-001", "linha": 8, "explicacao": "ampla"}]}'
    comentario = montar_comentario_de_avaliacao(
        resposta, frozenset({"QUA-001"}), codigo_revisado=CODIGO
    )
    assert "8 | except Exception:" in comentario


def test_comentario_descarta_apontamento_sem_linha_valida():
    resposta = '{"violacoes": [{"regra": "QUA-001", "linha": 99, "explicacao": "ampla"}]}'
    comentario = montar_comentario_de_avaliacao(
        resposta, frozenset({"QUA-001"}), codigo_revisado=CODIGO
    )
    assert "✅" in comentario


def test_sem_codigo_revisado_a_conferencia_nao_e_aplicada():
    """Compatibilidade: quem não passa o código mantém o comportamento antigo."""
    resposta = '{"violacoes": [{"regra": "QUA-001", "linha": 0, "explicacao": "algo"}]}'
    assert "🔴" in montar_comentario_de_avaliacao(resposta, frozenset({"QUA-001"}))


# --- Comentário do Pull Request ---------------------------------------------
#
# Regressão de usabilidade: um PR de dezoito arquivos gerava dezoito blocos,
# quinze repetindo "nenhuma violação". Os achados se perdiam no meio, e os
# arquivos que ficaram SEM avaliação — os únicos que exigem alguém olhar —
# ficavam indistinguíveis dos que passaram.

from app.core.models import ResultadoDoArquivo  # noqa: E402
from app.services.result_service import (  # noqa: E402
    avaliar_resposta,
    montar_comentario_do_pr,
)

_VIOLACAO = Violacao(
    regra="ARQ-003", explicacao="decide no adaptador",
    elemento="criar_router", linha=61, evidencia="if payload...",
)


def test_arquivos_limpos_nao_ocupam_um_bloco_cada():
    limpos = [ResultadoDoArquivo(f"app/m{i}.py") for i in range(15)]
    comentario = montar_comentario_do_pr(limpos)

    assert comentario.count("Nenhuma violação") == 1
    assert "<details>" in comentario
    assert "app/m14.py" in comentario


def test_violacao_fica_fora_do_bloco_recolhido():
    """O que pede ação não pode depender de o leitor clicar para abrir."""
    resultados = [
        ResultadoDoArquivo("app/api/webhook.py", (_VIOLACAO,)),
        ResultadoDoArquivo("app/core/models.py"),
    ]
    comentario = montar_comentario_do_pr(resultados)

    antes_do_recolhido = comentario.split("<details>")[0]
    assert "app/api/webhook.py" in antes_do_recolhido
    assert "ARQ-003" in antes_do_recolhido
    assert "decide no adaptador" in antes_do_recolhido


def test_resumo_conta_violacoes_e_arquivos():
    resultados = [
        ResultadoDoArquivo("a.py", (_VIOLACAO,)),
        ResultadoDoArquivo("b.py"),
        ResultadoDoArquivo("c.py"),
    ]
    assert "1 violação encontrada" in montar_comentario_do_pr(resultados)
    assert "1 de 3 arquivos" in montar_comentario_do_pr(resultados)


def test_nao_avaliado_e_separado_de_sem_apontamento():
    """São informações diferentes: uma pede ação humana, a outra não."""
    resultados = [
        ResultadoDoArquivo("quebrado.py", indisponivel=True),
        ResultadoDoArquivo("ok.py"),
    ]
    comentario = montar_comentario_do_pr(resultados)

    assert "sem avaliação" in comentario
    assert comentario.count("<details>") == 2
    assert "revisor humano" in comentario


def test_tudo_limpo_e_uma_linha_so():
    comentario = montar_comentario_do_pr(
        [ResultadoDoArquivo("a.py"), ResultadoDoArquivo("b.py")]
    )
    assert "✅ Nenhuma violação encontrada nos 2 arquivos analisados." in comentario


def test_erro_de_sintaxe_aparece_destacado():
    resultado = ResultadoDoArquivo("x.py", aviso=formatar_erro_de_sintaxe(3, "ops"))
    comentario = montar_comentario_do_pr([resultado])

    assert "Erro de sintaxe" in comentario.split("<details>")[0]


def test_bloco_de_estrutura_entra_antes_dos_arquivos():
    comentario = montar_comentario_do_pr(
        [ResultadoDoArquivo("a.py", (_VIOLACAO,))],
        blocos_de_estrutura=["**Estrutura** — diretório fora do padrão"],
    )
    assert comentario.index("Estrutura") < comentario.index("a.py")


# --- avaliar_resposta -------------------------------------------------------

def test_resposta_ilegivel_devolve_none_e_nao_lista_vazia():
    """Distinguir as duas é o que permite dizer 'não avaliei' em vez de 'passou'."""
    assert avaliar_resposta("isto nao e json", frozenset({"QUA-001"})) is None


def test_resposta_valida_devolve_as_violacoes_filtradas():
    resposta = (
        '{"violacoes": [{"regra": "QUA-001", "linha": 8, "explicacao": "x"},'
        ' {"regra": "INVENTADA", "linha": 8, "explicacao": "y"}]}'
    )
    violacoes = avaliar_resposta(resposta, frozenset({"QUA-001"}), CODIGO)

    assert [v.regra for v in violacoes] == ["QUA-001"]
