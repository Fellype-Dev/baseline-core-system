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


ARQUIVO_INVALIDO = ArquivoAlterado(
    caminho="app/x.py",
    diff="@@ -1 +1 @@\n+def quebrado(",
    conteudo="def quebrado(",
)


def test_arquivo_python_invalido_e_reportado_como_erro_de_sintaxe():
    repo = RepositorioFalso([ARQUIVO_INVALIDO])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), llm
    )

    assert "Erro de sintaxe" in comentario
    assert "app/x.py" in comentario
    # Codigo invalido nao tem arquitetura a avaliar: o modelo nao e acionado.
    assert llm.prompt_recebido is None


def test_erro_de_sintaxe_nao_derruba_os_demais_arquivos():
    """Um arquivo quebrado no PR não impede a revisão dos outros."""
    repo = RepositorioFalso([ARQUIVO_INVALIDO, ARQUIVO_PY])
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )
    assert "Erro de sintaxe" in comentario
    assert "SEG-001" in comentario


def test_erro_de_sintaxe_e_anunciado_ao_observador():
    observador = ObservadorFalso()
    analisar_pull_request(
        PullRequest("dono/repo", 1),
        RepositorioFalso([ARQUIVO_INVALIDO]),
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
        observador,
    )
    assert "sintaxe" in observador.etapas


class ObservadorFalso:
    """Registra os avisos recebidos, para verificar o que o núcleo anunciou."""

    def __init__(self):
        self.eventos = []

    def registrar(self, evento):
        self.eventos.append(evento)

    @property
    def etapas(self):
        return [evento.etapa for evento in self.eventos]


def test_pipeline_anuncia_as_etapas_na_ordem():
    repo = RepositorioFalso([ARQUIVO_PY])
    observador = ObservadorFalso()

    revisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
        observador,
    )

    assert observador.etapas == [
        "arquivos",
        "ast",
        "rag",
        "llm",
        "avaliado",
        "comentario",
        "concluido",
    ]


def test_evento_do_rag_cita_as_regras_recuperadas():
    repo = RepositorioFalso([ARQUIVO_PY])
    observador = ObservadorFalso()
    analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
        observador,
    )
    (evento_rag,) = [e for e in observador.eventos if e.etapa == "rag"]
    assert "SEG-001" in evento_rag.descricao


def test_falha_do_modelo_e_anunciada():
    observador = ObservadorFalso()
    analisar_pull_request(
        PullRequest("dono/repo", 1),
        RepositorioFalso([ARQUIVO_PY]),
        ConhecimentoFalso([REGRA_SEG]),
        LLMQueFalha(),
        observador,
    )
    assert "erro" in observador.etapas


def test_observador_que_falha_nao_derruba_a_revisao():
    """Observabilidade é acessória: um navegador desconectado não pode quebrar o PR."""

    class ObservadorQuebrado:
        def registrar(self, evento):
            raise RuntimeError("assinante desconectado")

    repo = RepositorioFalso([ARQUIVO_PY])
    revisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
        ObservadorQuebrado(),
    )
    # A revisão seguiu e publicou, apesar de o observador falhar em toda etapa.
    assert repo.comentario_publicado is not None
    assert "SEG-001" in repo.comentario_publicado


def test_pipeline_funciona_sem_observador():
    """O padrão é ninguém observando, e isso não pode mudar o comportamento."""
    repo = RepositorioFalso([ARQUIVO_PY])
    revisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )
    assert "SEG-001" in repo.comentario_publicado


class LLMQueFalha:
    """Simula uma falha de rede/timeout na chamada ao modelo."""

    def avaliar(self, prompt):
        raise RuntimeError("timeout ao chamar a API")


def test_falha_do_modelo_nao_derruba_a_revisao():
    repo = RepositorioFalso([ARQUIVO_PY])
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), LLMQueFalha()
    )
    # Em vez de propagar a exceção, produz um bloco honesto de indisponibilidade.
    assert "indisponível" in comentario
    assert "revisor humano" in comentario


def test_falha_em_um_arquivo_nao_impede_os_demais():
    # Dois arquivos; o modelo falha para ambos, mas cada um vira um bloco — a
    # revisão do PR como um todo continua produzindo comentário.
    outro = ArquivoAlterado(
        caminho="app/outro.py", diff="@@ -1 +1 @@\n+x = 1", conteudo="x = 1\n"
    )
    repo = RepositorioFalso([ARQUIVO_PY, outro])
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), LLMQueFalha()
    )
    assert "app/core/config.py" in comentario
    assert "app/outro.py" in comentario


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
