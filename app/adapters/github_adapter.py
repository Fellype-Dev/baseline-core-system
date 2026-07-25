"""
Adaptador do GitHub: implementa a RepositorioPort usando a biblioteca PyGithub.

Este é um adaptador de SAÍDA: o núcleo o aciona para ler o Pull Request e
publicar o comentário. Seu único papel é TRADUZIR entre o mundo do GitHub
(objetos da PyGithub) e o vocabulário do domínio (PullRequest, ArquivoAlterado).

Repare na direção dos imports: este arquivo importa do núcleo (`app.core`), mas
o núcleo nunca importa daqui. A dependência aponta para dentro.
"""

from github import Github, Auth

from app.core.models import ArquivoAlterado, PullRequest
from app.core.ports import RepositorioPort


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
        return conteudo.decoded_content.decode("utf-8")

    def publicar_comentario(self, pr: PullRequest, texto: str) -> None:
        """Publica o texto do feedback como um comentário no Pull Request."""
        repositorio = self._cliente.get_repo(pr.repositorio)
        pull_request = repositorio.get_pull(pr.numero)
        pull_request.create_issue_comment(texto)
