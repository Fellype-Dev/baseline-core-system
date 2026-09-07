
import json

import pytest

from app.core.models import (
    ArquivoAlterado,
    ConsultaDeRegras,
    DocumentoSDD,
    EstruturaDoRepositorio,
    PullRequest,
    RegraArquitetural,
)
from app.core.pipeline import (
    analisar_pull_request,
    merece_revisao,
    revisar_pull_request,
)


# --- Dublês das portas ------------------------------------------------------

# Documento de especificação mínimo e válido, como viria do repositório
# revisado. Os testes exercitam o caminho real: o pipeline lê o SDD, interpreta
# o markdown e sincroniza a base antes de qualquer revisão.
REGRA_EM_MARKDOWN = """---
id: SEG-001
titulo: Sem segredos no código
categoria: seguranca
severidade: obrigatoria
status: ativa
linguagens: [python]
aplica_se_a: ["**/*.py"]
---

## Regra

Segredos não podem ser escritos diretamente no código.

## Motivação

Um segredo versionado permanece no histórico do controle de versão.
"""


class RepositorioFalso:
    def __init__(self, arquivos, sdd=None, estrutura=None):
        self._arquivos = arquivos
        self._sdd = (
            sdd
            if sdd is not None
            else DocumentoSDD(regras={"SEG-001-sem-segredos.md": REGRA_EM_MARKDOWN})
        )
        self._estrutura = estrutura or EstruturaDoRepositorio(
            diretorios=("app", "app/core"), diretorios_novos=()
        )
        self.comentario_publicado = None

    def obter_arquivos_alterados(self, pr):
        return self._arquivos

    def publicar_comentario(self, pr, texto):
        self.comentario_publicado = texto

    def obter_documento_sdd(self, pr):
        return self._sdd

    def obter_estrutura(self, pr):
        return self._estrutura


class ConhecimentoFalso:
    """Devolve sempre as mesmas regras, e registra as consultas recebidas."""

    def __init__(self, regras):
        self._regras = regras
        self.consultas = []
        self.sincronizacoes = []

    def sincronizar_regras(self, repositorio, regras):
        self.sincronizacoes.append((repositorio, regras))

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
    {
        "violacoes": [
            {
                "regra": "SEG-001",
                "elemento": "",
                "linha": 2,
                "explicacao": "chave exposta",
            }
        ]
    }
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


def test_arquivo_python_invalido_e_reportado_e_ainda_revisado():
    """O erro de sintaxe é avisado, mas não cancela a revisão do arquivo.

    Um caractere faltando em uma linha não invalida as demais: deixar de apontar
    uma violação real por causa disso seria uma troca ruim.
    """
    repo = RepositorioFalso([ARQUIVO_INVALIDO])
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), llm
    )

    assert "Erro de sintaxe" in comentario
    assert "app/x.py" in comentario
    # A revisão prosseguiu: o modelo foi consultado e a violação foi apontada.
    assert llm.prompt_recebido is not None
    assert "SEG-001" in comentario


def test_sem_esqueleto_a_consulta_usa_as_linhas_do_diff():
    """Sem AST, a recuperação de regras se apoia no diff, e não fica vazia."""
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    analisar_pull_request(
        PullRequest("dono/repo", 1),
        RepositorioFalso([ARQUIVO_INVALIDO]),
        conhecimento,
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )
    (consulta,) = conhecimento.consultas
    assert "def quebrado(" in consulta.texto


def test_erro_de_sintaxe_e_reportado_mesmo_sem_regras_aplicaveis():
    """Sem revisão a apresentar, o aviso de sintaxe ainda é informação útil."""
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        RepositorioFalso([ARQUIVO_INVALIDO]),
        ConhecimentoFalso([]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )
    assert "Erro de sintaxe" in comentario


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


def test_regras_sao_lidas_do_repositorio_revisado():
    """O SDD pertence à organização: as regras vêm do repositório sob revisão."""
    repo = RepositorioFalso([ARQUIVO_PY])
    conhecimento = ConhecimentoFalso([REGRA_SEG])

    analisar_pull_request(
        PullRequest("dono/repo", 1), repo, conhecimento, LLMFalso(RESPOSTA_COM_VIOLACAO)
    )

    (repositorio, regras) = conhecimento.sincronizacoes[0]
    assert repositorio == "dono/repo"
    assert [regra.identificador for regra in regras] == ["SEG-001"]


def test_consulta_identifica_o_repositorio_de_origem():
    """Cada organização consulta as suas regras, não as de outra."""
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    analisar_pull_request(
        PullRequest("outra/org", 9),
        RepositorioFalso([ARQUIVO_PY]),
        conhecimento,
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )
    (consulta,) = conhecimento.consultas
    assert consulta.repositorio == "outra/org"


def test_repositorio_sem_sdd_nao_e_revisado():
    """Sem regras declaradas não há o que cobrar — e o autor é avisado disso."""
    repo = RepositorioFalso([ARQUIVO_PY], sdd=DocumentoSDD(regras={}))
    llm = LLMFalso(RESPOSTA_COM_VIOLACAO)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1), repo, ConhecimentoFalso([REGRA_SEG]), llm
    )

    assert "não possui um documento de especificação" in comentario
    assert llm.prompt_recebido is None


def test_sdd_invalido_nao_derruba_a_revisao():
    """Documento malformado é registrado, sem devolver erro técnico ao autor."""
    quebrado = DocumentoSDD(regras={"ruim.md": "isto não tem frontmatter"})
    repo = RepositorioFalso([ARQUIVO_PY], sdd=quebrado)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )

    assert "documento de especificação" in comentario


def test_regras_descontinuadas_sao_ignoradas():
    descontinuada = REGRA_EM_MARKDOWN.replace("status: ativa", "status: descontinuada")
    repo = RepositorioFalso([ARQUIVO_PY], sdd=DocumentoSDD(regras={"x.md": descontinuada}))
    conhecimento = ConhecimentoFalso([REGRA_SEG])

    analisar_pull_request(
        PullRequest("dono/repo", 1), repo, conhecimento, LLMFalso(RESPOSTA_COM_VIOLACAO)
    )

    assert conhecimento.sincronizacoes == []


# --- Regras de escopo estrutural --------------------------------------------

REGRA_ESTRUTURAL_EM_MARKDOWN = """---
id: ARQ-100
titulo: Separação entre cliente e servidor
categoria: arquitetura
severidade: obrigatoria
escopo: estrutura
---

## Regra

O código de interface não deve residir dentro do diretório do servidor.

## Motivação

Aninhar o cliente no servidor confunde as fronteiras de implantação.
"""

SDD_COM_ESTRUTURAL = DocumentoSDD(
    regras={
        "SEG-001.md": REGRA_EM_MARKDOWN,
        "ARQ-100.md": REGRA_ESTRUTURAL_EM_MARKDOWN,
    }
)

RESPOSTA_ESTRUTURAL = json.dumps(
    {
        "violacoes": [
            {
                "regra": "ARQ-100",
                "elemento": "server/frontend",
                "explicacao": "interface dentro do servidor",
            }
        ]
    }
)


def test_regra_estrutural_nao_vai_para_a_busca_semantica():
    """Regras do repositório inteiro não têm relevância por arquivo a calcular."""
    conhecimento = ConhecimentoFalso([REGRA_SEG])
    analisar_pull_request(
        PullRequest("dono/repo", 1),
        RepositorioFalso([ARQUIVO_PY], sdd=SDD_COM_ESTRUTURAL),
        conhecimento,
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )
    (_, indexadas) = conhecimento.sincronizacoes[0]
    assert [r.identificador for r in indexadas] == ["SEG-001"]


def test_diretorio_novo_e_avaliado_contra_regra_estrutural():
    estrutura = EstruturaDoRepositorio(
        diretorios=("server", "client"), diretorios_novos=("server/frontend",)
    )
    repo = RepositorioFalso([ARQUIVO_PY], sdd=SDD_COM_ESTRUTURAL, estrutura=estrutura)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_ESTRUTURAL),
    )

    assert "Estrutura do repositório" in comentario
    assert "ARQ-100" in comentario


def test_sem_diretorio_novo_a_estrutura_nao_e_avaliada():
    """Deriva anterior é contexto, não achado: repeti-la cansaria a equipe."""
    estrutura = EstruturaDoRepositorio(
        diretorios=("server", "server/frontend"), diretorios_novos=()
    )
    repo = RepositorioFalso([ARQUIVO_PY], sdd=SDD_COM_ESTRUTURAL, estrutura=estrutura)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )

    assert "Estrutura do repositório" not in comentario


def test_sem_regra_estrutural_a_estrutura_nao_e_consultada():
    estrutura = EstruturaDoRepositorio(
        diretorios=("app",), diretorios_novos=("utils",)
    )
    repo = RepositorioFalso([ARQUIVO_PY], estrutura=estrutura)

    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(RESPOSTA_COM_VIOLACAO),
    )

    assert "Estrutura do repositório" not in comentario


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
        "sdd",       # as regras vêm do repositório revisado, antes de tudo
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


# --- Conferência da linha apontada ------------------------------------------

ARQUIVO_COM_FUNCAO = ArquivoAlterado(
    caminho="app/servicos/credenciais.py",
    diff='@@ -1,2 +1,3 @@\n def carregar():\n+    return "sk-abc123"\n',
    conteudo='def carregar():\n    return "sk-abc123"\n',
)


def _resposta_apontando(linha: int) -> str:
    return json.dumps(
        {"violacoes": [{"regra": "SEG-001", "linha": linha, "explicacao": "chave"}]}
    )


def test_linha_apontada_vira_trecho_no_comentario():
    """O texto exibido vem do arquivo, não da resposta do modelo."""
    repo = RepositorioFalso([ARQUIVO_COM_FUNCAO])
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(_resposta_apontando(2)),
    )
    assert '2 | return "sk-abc123"' in comentario


def test_apontamento_com_linha_inexistente_nao_chega_ao_autor():
    repo = RepositorioFalso([ARQUIVO_COM_FUNCAO])
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(_resposta_apontando(99)),
    )
    assert "SEG-001" not in comentario


def test_sem_elementos_isolados_a_linha_nao_e_cobrada():
    """Sem listagem numerada no prompt, exigir número descartaria achado válido."""
    repo = RepositorioFalso([ARQUIVO_PY])
    comentario = analisar_pull_request(
        PullRequest("dono/repo", 1),
        repo,
        ConhecimentoFalso([REGRA_SEG]),
        LLMFalso(_resposta_apontando(0)),
    )
    assert "SEG-001" in comentario


# --- Política de quando revisar ---------------------------------------------
#
# Antes, "só revisamos na abertura" era uma condição dentro do adaptador de
# webhook — decisão de produto escondida em quem fala o protocolo do GitHub.
# A própria ferramenta apontou isso no seu código, contra a regra ARQ-003.

def test_abertura_pede_revisao():
    assert merece_revisao("aberto")


def test_push_em_pr_aberto_pede_revisao():
    """Sem isto a ferramenta aponta uma vez e nunca verifica a correção."""
    assert merece_revisao("atualizado")


def test_reabertura_pede_revisao():
    assert merece_revisao("reaberto")


def test_pr_fechado_nao_pede_revisao():
    assert not merece_revisao("fechado")


def test_evento_desconhecido_nao_pede_revisao():
    assert not merece_revisao("qualquer_outra_coisa")
