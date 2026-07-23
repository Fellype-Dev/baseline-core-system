"""Testes do pipeline de revisão (feature E1).

Todo o encadeamento é exercitado com dublês das três portas — sem rede, sem
banco vetorial, sem modelo de linguagem real.
"""

import json

import pytest

from app.core.models import (
    ArquivoAlterado,
    ConsultaDeRegras,
    PullRequest,
    RegraArquitetural,
)
from app.core.pipeline import analisar_pull_request, revisar_pull_request


# --- Dublês das portas ------------------------------------------------------

class RepositorioFalso:
    def __init__(self, arquivos):
        self._arquivos = arquivos
        self.comentario_publicado = None

    def obter_arquivos_alterados(self, pr):
        return self._arquivos

    def publicar_comentario(self, pr, texto):
        self.comentario_publicado = texto


class ConhecimentoFalso:
    """Devolve sempre as mesmas regras, e registra as consultas recebidas."""

    def __init__(self, regras):
        self._regras = regras
        self.consultas = []

    def buscar_regras_relevantes(self, consulta):
        self.consultas.append(consulta)
        return self._regras


class LLMFalso:
    """Devolve uma resposta fixa e guarda o último prompt recebido."""

    def __init__(self, resposta):
        self._resposta = resposta
        self.prompt_recebido = None

    def avaliar(self, prompt):
        self.prompt_recebido = prompt
        return self._resposta


# --- Dados de exemplo -------------------------------------------------------

REGRA_SEG = RegraArquitetural(
    identificador="SEG-001",
    titulo="Sem segredos no código",
    categoria="seguranca",
    severidade="obrigatoria",
    regra="Segredos não podem ser escritos no código.",
    motivacao="Um segredo versionado vaza no histórico.",
)

ARQUIVO_PY = ArquivoAlterado(
    caminho="app/core/config.py",
    diff='@@ -1,1 +1,2 @@\n import os\n+API_KEY = "sk-123"\n',
    conteudo='import os\nAPI_KEY = "sk-123"\n',
)

RESPOSTA_COM_VIOLACAO = json.dumps(
    {"violacoes": [{"regra": "SEG-001", "elemento": "", "explicacao": "chave exposta"}]}
)


# --- Testes ----------------------------------------------------------------

def test_pipeline_completo_gera_comentario_com_a_violacao():
    repo = RepositorioFalso([ARQUIVO_PY])
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, conhecimento, llm
    )

    assert "app/core/config.py" in comentario
    assert "SEG-001" in comentario
    assert "chave exposta" in comentario


def test_revisar_publica_o_comentario_no_repositorio():
    repo = RepositorioFalso([ARQUIVO_PY])
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)

    revisar_pull_request(PullRequest("dono/repo", 1), repo, conhecimento, llm)

    assert repo.comentario_publicado is not None
    assert "SEG-001" in repo.comentario_publicado


def test_prompt_recebe_as_regras_recuperadas():
    repo = RepositorioFalso([ARQUIVO_PY])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)
    analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), llm
    )
    # A ligação está correta: a regra recuperada chegou ao prompt do modelo.
    assert "SEG-001" in llm.prompt_recebido


def test_consulta_de_regras_usa_caminho_e_linguagem_do_arquivo():
    repo = RepositorioFalso([ARQUIVO_PY])
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    analisar_pull_request(
        PullRequest("dono/repo", 1), repo, conhecimento, LLMFalso(RESPOSTA_COM_VIOLACAO)
    )
    (consulta,) = conhecimento.consultas
    assert isinstance(consulta, ConsultaDeRegras)
    assert consulta.caminho == "app/core/config.py"
    assert consulta.linguagem == "python"


def test_sem_regras_aplicaveis_nao_aciona_o_modelo():
    repo = RepositorioFalso([ARQUIVO_PY])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([]), llm
    )
    assert "Nenhuma regra arquitetural se aplica" in comentario
    # O modelo não deve ser chamado quando não há regra a avaliar.
    assert llm.prompt_recebido is None


def test_arquivo_python_invalido_nao_derruba_a_revisao():
    # Conteúdo com sintaxe quebrada: a AST levanta SyntaxError internamente.
    arquivo = ArquivoAlterado(
        caminho="app/x.py",
        diff="@@ -1 +1 @@\n+def quebrado(",
        conteudo="def quebrado(",
    )
    repo = RepositorioFalso([arquivo])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)

    # Não deve levantar; cai para revisão baseada só no diff.
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), llm
    )
    assert "SEG-001" in comentario


def test_arquivo_nao_python_e_revisado_pelo_diff():
    arquivo = ArquivoAlterado(
        caminho="docs/manual.md",
        diff="@@ -1 +1 @@\n+Lançado em 2026.",
        conteudo="Lançado em 2026.\n",
    )
    repo = RepositorioFalso([arquivo])
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    analisar_pull_request(
        PullRequest("dono/repo", 1), repo, conhecimento, LLMFalso(RESPOSTA_COM_VIOLACAO)
    )
    (consulta,) = conhecimento.consultas
    # Sem AST para markdown: a linguagem não é reconhecida, mas a revisão segue.
    assert consulta.linguagem == ""
    assert consulta.caminho == "docs/manual.md"
