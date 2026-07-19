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
                )
            )
        return arquivos

    def publicar_comentario(self, pr: PullRequest, texto: str) -> None:
        """Publica o texto do feedback como um comentário no Pull Request."""
        repositorio = self._cliente.get_repo(pr.repositorio)
        pull_request = repositorio.get_pull(pr.numero)
        pull_request.create_issue_comment(texto)
