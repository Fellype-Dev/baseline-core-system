"""
Adaptador do GitHub: implementa a RepositorioPort usando a biblioteca PyGithub.

Este é um adaptador de SAÍDA: o núcleo o aciona para ler o Pull Request e
publicar o comentário. Seu único papel é TRADUZIR entre o mundo do GitHub
(objetos da PyGithub) e o vocabulário do domínio (PullRequest, ArquivoAlterado).

Repare na direção dos imports: este arquivo importa do núcleo (`app.core`), mas
o núcleo nunca importa daqui. A dependência aponta para dentro.
"""

from github import Auth, Github, GithubException

from app.core.models import (
    ArquivoAlterado,
    DocumentoSDD,
    EstruturaDoRepositorio,
    PullRequest,
)
from app.core.ports import RepositorioPort

DIRETORIO_SDD = "sdd"


def _diretorios_de(caminho: str) -> set[str]:

    partes = caminho.replace("\\", "/").split("/")[:-1]
    return {"/".join(partes[: indice + 1]) for indice in range(len(partes))}


class GitHubAdapter(RepositorioPort):

    def __init__(self, token: str | None = None, *, cliente: Github | None = None) -> None:
        """Cria o adaptador a partir de um token OU de um cliente já autenticado.

        As duas formas existem porque há duas maneiras de autenticar no GitHub.
        Com token pessoal, o adaptador monta o cliente sozinho. Com GitHub App, a
        credencial depende de qual instalação disparou o evento, e o cliente é
        montado fora — pela fábrica, que sabe fazer essa troca.
        """
        if cliente is not None:
            self._cliente = cliente
        elif token is not None:
            self._cliente = Github(auth=Auth.Token(token))
        else:
            raise ValueError(
                "informe um token ou um cliente já autenticado para criar o adaptador"
            )

    def obter_arquivos_alterados(self, pr: PullRequest) -> list[ArquivoAlterado]:
        repositorio = self._cliente.get_repo(pr.repositorio)
        pull_request = repositorio.get_pull(pr.numero)
        sha_do_pr = pull_request.head.sha

        arquivos: list[ArquivoAlterado] = []
        for arquivo_github in pull_request.get_files():

            if not arquivo_github.patch:
                continue

            arquivos.append(
                ArquivoAlterado(
                    caminho=arquivo_github.filename,
                    diff=arquivo_github.patch,
                    conteudo=self._obter_conteudo(
                        repositorio, arquivo_github, sha_do_pr
                    ),
                )
            )
        return arquivos

    def _obter_conteudo(self, repositorio, arquivo_github, ref: str) -> str:

        if arquivo_github.status == "removed":
            return ""

        conteudo = repositorio.get_contents(arquivo_github.filename, ref=ref)

        return conteudo.decoded_content.decode("utf-8-sig")

    def obter_estrutura(self, pr: PullRequest) -> EstruturaDoRepositorio:

        repositorio = self._cliente.get_repo(pr.repositorio)
        existentes = self._diretorios_do_branch_padrao(repositorio)

        pull_request = repositorio.get_pull(pr.numero)
        alterados: set[str] = set()
        for arquivo in pull_request.get_files():
            alterados.update(_diretorios_de(arquivo.filename))

        return EstruturaDoRepositorio(
            diretorios=tuple(sorted(existentes)),
            diretorios_novos=tuple(sorted(alterados - existentes)),
        )

    def _diretorios_do_branch_padrao(self, repositorio) -> set[str]:
        try:
            arvore = repositorio.get_git_tree(
                repositorio.default_branch, recursive=True
            )
        except GithubException:
            return set()

        return {item.path for item in arvore.tree if item.type == "tree"}

    def obter_documento_sdd(self, pr: PullRequest) -> DocumentoSDD:

        repositorio = self._cliente.get_repo(pr.repositorio)

        regras = self._ler_diretorio(repositorio, f"{DIRETORIO_SDD}/regras")
        configuracao = self._ler_arquivo(
            repositorio, f"{DIRETORIO_SDD}/sdd.config.yml"
        )
        return DocumentoSDD(regras=regras, configuracao=configuracao)

    def _ler_diretorio(self, repositorio, caminho: str) -> dict[str, str]:
        try:
            itens = repositorio.get_contents(caminho)
        except GithubException:
            # Repositório sem documento de especificação: não é erro, apenas
            # significa que não há regras declaradas a cobrar.
            return {}

        return {
            item.name: item.decoded_content.decode("utf-8-sig")
            for item in itens
            if item.type == "file" and item.name.endswith(".md")
        }

    def _ler_arquivo(self, repositorio, caminho: str) -> str | None:
        try:
            return repositorio.get_contents(caminho).decoded_content.decode("utf-8-sig")
        except GithubException:
            return None

    def publicar_comentario(self, pr: PullRequest, texto: str) -> None:
        repositorio = self._cliente.get_repo(pr.repositorio)
        pull_request = repositorio.get_pull(pr.numero)
        pull_request.create_issue_comment(texto)
