"""Teste de contrato do GitHubAdapter (sem rede)."""

from app.adapters.github_adapter import GitHubAdapter
from app.core.ports import RepositorioPort


def test_github_adapter_satisfaz_o_contrato():
    # Construir o adaptador não faz chamadas de rede, então um token falso basta.
    # Se ele puder ser criado, é porque implementou toda a RepositorioPort.
    adaptador = GitHubAdapter(token="token_falso")
    assert isinstance(adaptador, RepositorioPort)
