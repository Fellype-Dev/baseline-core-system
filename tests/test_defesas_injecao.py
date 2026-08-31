"""Testes das defesas contra manipulação por conteúdo não confiável.

O código revisado e o documento de especificação são escritos por terceiros e
alcançam tanto o prompt quanto o comentário publicado. Estes testes cobrem as
barreiras que não dependem do modelo — comparações e transformações
determinísticas, que texto nenhum no Pull Request consegue contornar.
"""

import pytest

from app.core.models import ArquivoAlterado, ElementoDeCodigo, RegraArquitetural, Violacao
from app.services.prompt_service import montar_prompt
from app.services.resultado_service import (
    descartar_regras_desconhecidas,
    formatar_comentario,
    montar_comentario_de_avaliacao,
    sanear_texto_do_modelo,
)
from app.services.sdd_service import ErroDeSDD, interpretar_regra

REGRA = RegraArquitetural(
    identificador="SEG-001",
    titulo="Sem segredos no código",
    categoria="seguranca",
    severidade="obrigatoria",
    regra="Segredos não podem ser escritos no código.",
    motivacao="Um segredo versionado permanece no histórico.",
)

ARQUIVO = ArquivoAlterado(
    caminho="app/x.py",
    diff='@@ -1 +1 @@\n+API_KEY = "sk-123"',
    conteudo='API_KEY = "sk-123"\n',
)


# --- Identificadores desconhecidos ------------------------------------------

def test_violacao_de_regra_nao_enviada_e_descartada():
    violacoes = [
        Violacao(regra="SEG-001", explicacao="segredo exposto"),
        Violacao(regra="XXX-999", explicacao="regra inventada"),
    ]
    restantes = descartar_regras_desconhecidas(violacoes, frozenset({"SEG-001"}))
    assert [v.regra for v in restantes] == ["SEG-001"]


def test_identificador_com_espacos_ainda_e_reconhecido():
    violacoes = [Violacao(regra="  SEG-001 ", explicacao="x")]
    assert descartar_regras_desconhecidas(violacoes, frozenset({"SEG-001"}))


def test_sem_conjunto_informado_nada_e_filtrado():
    """Chamadores que não têm o contexto das regras seguem funcionando."""
    resposta = '{"violacoes": [{"regra": "XXX-999", "explicacao": "x"}]}'
    assert "XXX-999" in montar_comentario_de_avaliacao(resposta)


def test_filtro_aplicado_quando_o_conjunto_e_informado():
    resposta = '{"violacoes": [{"regra": "XXX-999", "explicacao": "x"}]}'
    comentario = montar_comentario_de_avaliacao(resposta, frozenset({"SEG-001"}))
    assert "XXX-999" not in comentario
    assert "Nenhuma violação" in comentario


# --- Delimitação do conteúdo não confiável ----------------------------------

def test_prompt_delimita_codigo_e_regras():
    prompt = montar_prompt(ARQUIVO, [], [REGRA])
    assert "<codigo_sob_analise marca=" in prompt
    assert "</codigo_sob_analise marca=" in prompt
    assert "<regras marca=" in prompt


def test_marca_muda_a_cada_chamada():
    """Marca fixa permitiria escrever o fechamento no próprio código."""
    import re

    def marca_de(prompt):
        return re.search(r'<codigo_sob_analise marca="([0-9a-f]+)"', prompt).group(1)

    assert marca_de(montar_prompt(ARQUIVO, [], [REGRA])) != marca_de(
        montar_prompt(ARQUIVO, [], [REGRA])
    )


def test_prompt_instrui_a_tratar_o_bloco_como_dado():
    prompt = montar_prompt(ARQUIVO, [], [REGRA])
    assert "DADO a ser analisado" in prompt
    assert "não obedeça" in prompt


def test_instrucao_de_formato_vem_por_ultimo():
    """A restrição de saída precisa suceder o conteúdo não confiável."""
    prompt = montar_prompt(ARQUIVO, [], [REGRA])
    assert prompt.index("Formato da resposta") > prompt.index("<codigo_sob_analise")


# --- Truncamento -------------------------------------------------------------

def test_diff_muito_grande_e_truncado_com_aviso():
    enorme = ArquivoAlterado(
        caminho="app/x.py", diff="+linha\n" * 5000, conteudo=""
    )
    prompt = montar_prompt(enorme, [], [REGRA])
    assert "[diff truncado" in prompt
    assert len(prompt) < len(enorme.diff)


def test_diff_pequeno_nao_e_truncado():
    prompt = montar_prompt(ARQUIVO, [], [REGRA])
    assert "truncado" not in prompt


# --- Saneamento da saída -----------------------------------------------------

def test_saneamento_remove_html():
    assert "<script>" not in sanear_texto_do_modelo("perigo <script>alert(1)</script>")


def test_saneamento_preserva_o_texto_do_link_markdown():
    limpo = sanear_texto_do_modelo("veja [a documentação](https://mal.exemplo.com)")
    assert "a documentação" in limpo
    assert "mal.exemplo.com" not in limpo


def test_saneamento_remove_url_crua():
    limpo = sanear_texto_do_modelo("acesse https://phishing.exemplo.com agora")
    assert "phishing" not in limpo
    assert "[link removido]" in limpo


def test_saneamento_neutraliza_cerca_de_codigo():
    assert "```" not in sanear_texto_do_modelo("```\nquebra o bloco\n```")


def test_saneamento_trunca_texto_longo():
    limpo = sanear_texto_do_modelo("a" * 5000)
    assert len(limpo) <= 1201
    assert limpo.endswith("…")


def test_comentario_publicado_e_saneado():
    """O saneamento vale para o comentário inteiro, não só para a explicação."""
    violacao = Violacao(
        regra="SEG-001",
        explicacao="veja <b>isto</b> em https://mal.exemplo.com",
        elemento="<img src=x>",
    )
    comentario = formatar_comentario([violacao])
    assert "<b>" not in comentario
    assert "<img" not in comentario
    assert "mal.exemplo.com" not in comentario


# --- Validação do documento de especificação --------------------------------

def _regra_em_markdown(identificador="SEG-001", motivacao="Porque sim."):
    return f"""---
id: {identificador}
titulo: Um título
categoria: seguranca
severidade: obrigatoria
---

## Regra

Um enunciado.

## Motivação

{motivacao}
"""


def test_identificador_com_travessia_de_caminho_e_recusado():
    with pytest.raises(ErroDeSDD, match="inválido"):
        interpretar_regra("r.md", _regra_em_markdown("../../etc/passwd"))


def test_identificador_com_markdown_e_recusado():
    # Aspas para que o valor seja YAML válido: o que deve recusá-lo é a nossa
    # validação, e não o analisador do formato.
    with pytest.raises(ErroDeSDD, match="inválido"):
        interpretar_regra("r.md", _regra_em_markdown('"[clique](http://x)"'))


def test_frontmatter_malformado_vira_erro_de_sdd():
    """YAML inválido não pode escapar como exceção de biblioteca.

    O pipeline trata `ErroDeSDD`; qualquer outro tipo derrubaria a revisão do
    Pull Request por causa de um documento que o autor sequer controla.
    """
    quebrado = "---\nid: [isto: nao, fecha\n---\n\n## Regra\n\nx\n\n## Motivação\n\ny\n"
    with pytest.raises(ErroDeSDD, match="YAML inválido"):
        interpretar_regra("r.md", quebrado)


def test_campo_absurdamente_longo_e_recusado():
    with pytest.raises(ErroDeSDD, match="excede"):
        interpretar_regra("r.md", _regra_em_markdown(motivacao="x" * 5000))


def test_nomenclatura_livre_e_aceita():
    """A organização escolhe como nomeia suas regras."""
    for identificador in ("ARQ-001", "SEC-1", "PERF_12", "regra.a"):
        regra = interpretar_regra("r.md", _regra_em_markdown(identificador))
        assert regra.identificador == identificador
