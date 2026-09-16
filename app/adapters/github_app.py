

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
