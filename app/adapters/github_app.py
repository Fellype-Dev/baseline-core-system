"""
Autenticação como GitHub App: produz um adaptador por instalação.

Um token pessoal pertence a uma pessoa e só alcança os repositórios dela. Um
GitHub App tem identidade própria e é **instalado** por cada organização, que
concede as permissões nos seus próprios repositórios. É o que permite atender
repositórios de terceiros sem que ninguém precise compartilhar credenciais.

A consequência para a arquitetura é que a credencial deixa de ser fixa: ela
depende de qual instalação disparou o evento. Por isso o adaptador de
repositório passa a ser criado por requisição, e não uma única vez na
inicialização — mudança que acontece inteiramente no composition root, sem
alcançar o núcleo.

A troca de credenciais é feita pela própria PyGithub: a partir da chave privada
do App ela gera o JWT, obtém o token de instalação e o renova quando expira
(tokens de instalação valem uma hora). Não há gestão manual de expiração aqui.
"""

from github import Auth, Github

from app.adapters.github_adapter import GitHubAdapter


class ErroDeCredencialDoApp(Exception):
    """Não foi possível autenticar como a instalação informada."""


class FabricaDeGitHub:
    """Produz um adaptador de repositório autenticado para cada instalação."""

    def __init__(self, app_id: str, chave_privada: str) -> None:
        # Nenhuma chamada de rede acontece aqui: apenas a preparação da
        # credencial, espelhando o comportamento dos demais adaptadores.
        self._autenticacao = Auth.AppAuth(app_id, chave_privada)
        # Um adaptador por instalação. Reaproveitar é seguro porque a própria
        # credencial renova o token quando ele expira — o que se guarda aqui é a
        # capacidade de obter token, não um token já emitido.
        self._adaptadores: dict[int, GitHubAdapter] = {}

    def para_instalacao(self, instalacao: int) -> GitHubAdapter:
        """Devolve o adaptador autenticado como aquela instalação do App."""
        if instalacao in self._adaptadores:
            return self._adaptadores[instalacao]

        try:
            credencial = self._autenticacao.get_installation_auth(instalacao)
            adaptador = GitHubAdapter(cliente=Github(auth=credencial))
        except Exception as erro:
            raise ErroDeCredencialDoApp(
                f"não foi possível autenticar como a instalação {instalacao}: {erro}"
            ) from erro

        self._adaptadores[instalacao] = adaptador
        return adaptador
