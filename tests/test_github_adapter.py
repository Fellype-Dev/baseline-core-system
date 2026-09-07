"""Testes do GitHubAdapter (sem rede: a API do GitHub é substituída por dublês)."""

from app.adapters.github_adapter import GitHubAdapter
from app.core.models import PullRequest
from app.core.ports import RepositorioPort


def test_github_adapter_satisfaz_o_contrato():
    # Construir o adaptador não faz chamadas de rede, então um token falso basta.
    # Se ele puder ser criado, é porque implementou toda a RepositorioPort.
    adaptador = GitHubAdapter(token="token_falso")
    assert isinstance(adaptador, RepositorioPort)


# --- Dublês da PyGithub -----------------------------------------------------

class _ArquivoFalso:
    def __init__(self, filename, patch, status="modified"):
        self.filename = filename
        self.patch = patch
        self.status = status


class _ConteudoFalso:
    def __init__(self, texto: str):
        self.decoded_content = texto.encode("utf-8")


class _PullFalso:
    def __init__(self, arquivos, sha="abc123"):
        self._arquivos = arquivos
        self.head = type("Head", (), {"sha": sha})()

    def get_files(self):
        return self._arquivos


class _RepoFalso:
    def __init__(self, pull, conteudos):
        self._pull = pull
        self._conteudos = conteudos
        self.refs_pedidas = []

    def get_pull(self, numero):
        return self._pull

    def get_contents(self, caminho, ref):
        self.refs_pedidas.append((caminho, ref))
        return _ConteudoFalso(self._conteudos[caminho])


class _ClienteFalso:
    def __init__(self, repo):
        self._repo = repo

    def get_repo(self, nome):
        return self._repo


def test_obter_arquivos_traz_diff_e_conteudo_completo():
    pull = _PullFalso(
        arquivos=[_ArquivoFalso("app/x.py", patch="@@ -1 +1 @@\n+x = 1")],
        sha="sha_do_head",
    )
    repo = _RepoFalso(pull, conteudos={"app/x.py": "x = 1\ny = 2\n"})

    adaptador = GitHubAdapter(token="falso")
    adaptador._cliente = _ClienteFalso(repo)

    (arquivo,) = adaptador.obter_arquivos_alterados(PullRequest("dono/repo", 7))

    assert arquivo.caminho == "app/x.py"
    assert arquivo.diff == "@@ -1 +1 @@\n+x = 1"
    assert arquivo.conteudo == "x = 1\ny = 2\n"
    # O conteúdo foi buscado na versão (head) do PR, não no branch base.
    assert repo.refs_pedidas == [("app/x.py", "sha_do_head")]


def test_arquivo_removido_nao_tem_conteudo():
    pull = _PullFalso(
        arquivos=[_ArquivoFalso("app/velho.py", patch="@@ -1 +0 @@\n-x = 1", status="removed")]
    )
    repo = _RepoFalso(pull, conteudos={})

    adaptador = GitHubAdapter(token="falso")
    adaptador._cliente = _ClienteFalso(repo)

    (arquivo,) = adaptador.obter_arquivos_alterados(PullRequest("dono/repo", 7))

    assert arquivo.conteudo == ""
    # Não deve tentar buscar o conteúdo de um arquivo que não existe mais.
    assert repo.refs_pedidas == []


def test_marca_de_ordem_de_byte_e_descartada():
    """Arquivos salvos com BOM (comum no Windows) precisam chegar limpos.

    Sem isso, o U+FEFF sobrevive à decodificação e a análise sintática falha na
    primeira linha, mesmo quando o código é válido.
    """
    import ast

    codigo = "def soma(a, b):\n    return a + b\n"
    pull = _PullFalso(arquivos=[_ArquivoFalso("app/x.py", patch="@@ -1 +1 @@\n+x")])
    repo = _RepoFalso(pull, conteudos={"app/x.py": "﻿" + codigo})

    adaptador = GitHubAdapter(token="falso")
    adaptador._cliente = _ClienteFalso(repo)

    (arquivo,) = adaptador.obter_arquivos_alterados(PullRequest("dono/repo", 7))

    assert "﻿" not in arquivo.conteudo
    assert arquivo.conteudo == codigo
    ast.parse(arquivo.conteudo)  # não deve levantar SyntaxError


def test_arquivo_sem_patch_e_ignorado():
    pull = _PullFalso(arquivos=[_ArquivoFalso("imagem.png", patch=None)])
    repo = _RepoFalso(pull, conteudos={})

    adaptador = GitHubAdapter(token="falso")
    adaptador._cliente = _ClienteFalso(repo)

    assert adaptador.obter_arquivos_alterados(PullRequest("dono/repo", 7)) == []


# --- Publicação da revisão --------------------------------------------------
#
# O Pull Request é revisado a cada push, então publicar sempre um comentário
# novo empilharia revisões repetidas. A revisão anterior é reescrita no lugar.

class _ComentarioFalso:
    def __init__(self, body):
        self.body = body
        self.edicoes = []

    def edit(self, corpo):
        self.edicoes.append(corpo)
        self.body = corpo


class _PullComComentarios:
    def __init__(self, comentarios=()):
        self._comentarios = list(comentarios)
        self.criados = []

    def get_issue_comments(self):
        return self._comentarios

    def create_issue_comment(self, corpo):
        comentario = _ComentarioFalso(corpo)
        self.criados.append(comentario)
        self._comentarios.append(comentario)
        return comentario


class _RepoComPull:
    def __init__(self, pull):
        self._pull = pull

    def get_pull(self, numero):
        return self._pull


def _adaptador_para(pull):
    adaptador = GitHubAdapter(token="falso")
    adaptador._cliente = _ClienteFalso(_RepoComPull(pull))
    return adaptador


def test_primeira_revisao_cria_o_comentario():
    pull = _PullComComentarios()
    _adaptador_para(pull).publicar_comentario(PullRequest("dono/repo", 7), "## Revisão")

    (criado,) = pull.criados
    assert "## Revisão" in criado.body


def test_revisao_seguinte_reescreve_a_anterior():
    anterior = _ComentarioFalso("<!-- revisao-arquitetural -->\n## Revisão antiga")
    pull = _PullComComentarios([anterior])

    _adaptador_para(pull).publicar_comentario(PullRequest("dono/repo", 7), "## Revisão nova")

    assert pull.criados == []
    assert "## Revisão nova" in anterior.body
    assert "antiga" not in anterior.body


def test_comentario_de_outra_pessoa_nao_e_sobrescrito():
    """Só a marca da ferramenta identifica a revisão; o resto do PR é alheio."""
    humano = _ComentarioFalso("Boa, mas revisa o nome dessa variável")
    pull = _PullComComentarios([humano])

    _adaptador_para(pull).publicar_comentario(PullRequest("dono/repo", 7), "## Revisão")

    assert humano.edicoes == []
    assert len(pull.criados) == 1


def test_marca_fica_invisivel_no_inicio_do_corpo():
    """Comentário HTML: o GitHub não o renderiza, mas ele permite reencontrar."""
    pull = _PullComComentarios()
    _adaptador_para(pull).publicar_comentario(PullRequest("dono/repo", 7), "## Revisão")

    (criado,) = pull.criados
    assert criado.body.startswith("<!-- revisao-arquitetural -->")
