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

# Diretório, no repositório revisado, onde a organização declara suas regras.
DIRETORIO_SDD = "sdd"


def _diretorios_de(caminho: str) -> set[str]:
    """Devolve todos os diretórios ancestrais de um caminho de arquivo.

    Para "app/core/pipeline.py", devolve {"app", "app/core"}. É o que permite
    reconhecer que uma submissão criou um diretório inteiro, e não apenas um
    arquivo dentro de um diretório que já existia.
    """
    partes = caminho.replace("\\", "/").split("/")[:-1]
    return {"/".join(partes[: indice + 1]) for indice in range(len(partes))}


class GitHubAdapter(RepositorioPort):
    """Fala com a API do GitHub para cumprir o contrato RepositorioPort."""

    def __init__(self, token: str) -> None:
        # Auth.Token é a forma recomendada na PyGithub moderna (2.x).
        # Nenhuma chamada de rede acontece aqui — só a configuração do cliente.
        self._cliente = Github(auth=Auth.Token(token))

    def obter_arquivos_alterados(self, pr: PullRequest) -> list[ArquivoAlterado]:
        """Busca no GitHub os arquivos alterados e os traduz para o domínio."""
        repositorio = self._cliente.get_repo(pr.repositorio)
        pull_request = repositorio.get_pull(pr.numero)
        # A versão a analisar é o "head" do PR: o estado proposto pelas mudanças.
        sha_do_pr = pull_request.head.sha

        arquivos: list[ArquivoAlterado] = []
        for arquivo_github in pull_request.get_files():
            # `patch` pode vir vazio (ex.: arquivo binário ou diff grande demais).
            # Sem diff não há o que revisar, então pulamos esses arquivos.
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
        """Lê o conteúdo completo do arquivo na versão `ref` do repositório.

        A AST precisa do arquivo inteiro (não só do diff) para montar o esqueleto
        lógico. Arquivos removidos não existem mais nessa versão — para eles não
        há corpo a analisar, então devolvemos texto vazio; a revisão desses casos
        se apoia apenas no diff.
        """
        if arquivo_github.status == "removed":
            return ""

        conteudo = repositorio.get_contents(arquivo_github.filename, ref=ref)
        # get_contents devolve bytes já decodificados do base64 da API.
        #
        # A decodificação usa "utf-8-sig", e não "utf-8", para descartar a marca
        # de ordem de byte quando ela existe. Arquivos criados em editores do
        # Windows costumam trazê-la, e o caractere resultante (U+FEFF) faria a
        # análise sintática falhar já na primeira linha, mesmo em código válido.
        # O tratamento é indiferente para arquivos sem a marca.
        return conteudo.decoded_content.decode("utf-8-sig")

    def obter_estrutura(self, pr: PullRequest) -> EstruturaDoRepositorio:
        """Monta a árvore de diretórios e identifica os que o PR cria.

        A árvore vem do branch padrão — o estado já aprovado — e os diretórios
        novos são deduzidos dos caminhos alterados no Pull Request. Essa
        diferença é o que permite apontar apenas o que a submissão introduz.
        """
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
        """Lista os diretórios existentes no branch padrão do repositório."""
        try:
            arvore = repositorio.get_git_tree(
                repositorio.default_branch, recursive=True
            )
        except GithubException:
            return set()

        return {item.path for item in arvore.tree if item.type == "tree"}

    def obter_documento_sdd(self, pr: PullRequest) -> DocumentoSDD:
        """Lê o diretório `sdd/` versionado no repositório revisado.

        A leitura é feita no branch padrão, e não no branch do Pull Request:
        as regras vigentes são as que a organização já aprovou, e não as que a
        submissão em avaliação eventualmente proponha. Do contrário, bastaria
        alterar o SDD no próprio Pull Request para escapar de uma regra.
        """
        repositorio = self._cliente.get_repo(pr.repositorio)

        regras = self._ler_diretorio(repositorio, f"{DIRETORIO_SDD}/regras")
        configuracao = self._ler_arquivo(
            repositorio, f"{DIRETORIO_SDD}/sdd.config.yml"
        )
        return DocumentoSDD(regras=regras, configuracao=configuracao)

    def _ler_diretorio(self, repositorio, caminho: str) -> dict[str, str]:
        """Lê os arquivos markdown de um diretório do repositório."""
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
        """Lê um arquivo do repositório, ou None se ele não existir."""
        try:
            return repositorio.get_contents(caminho).decoded_content.decode("utf-8-sig")
        except GithubException:
            return None

    def publicar_comentario(self, pr: PullRequest, texto: str) -> None:
        """Publica o texto do feedback como um comentário no Pull Request."""
        repositorio = self._cliente.get_repo(pr.repositorio)
        pull_request = repositorio.get_pull(pr.numero)
        pull_request.create_issue_comment(texto)
