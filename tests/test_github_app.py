"""Testes da autenticação como GitHub App (sem rede).

A troca de credenciais em si é feita pela biblioteca; o que se verifica aqui é a
lógica própria da fábrica — reaproveitar o adaptador de cada instalação, manter
instalações isoladas e converter falha de credencial em erro próprio.
"""

import pytest
from github import Auth

from app.adapters.github_adapter import GitHubAdapter
from app.adapters.github_app import ErroDeCredencialDoApp, FabricaDeGitHub
from app.core.ports import RepositorioPort


class _CredencialFalsa:
    """Substitui a autenticação da biblioteca, registrando o que foi pedido."""

    def __init__(self, falhar=False):
        self.instalacoes_pedidas = []
        self._falhar = falhar

    def get_installation_auth(self, instalacao):
        self.instalacoes_pedidas.append(instalacao)
        if self._falhar:
            raise RuntimeError("chave privada recusada")
        # Uma credencial real da própria biblioteca: construí-la não faz chamada
        # de rede, e é o que o cliente do GitHub aceita.
        return Auth.Token(f"token-da-instalacao-{instalacao}")


def _fabrica(falhar=False):
    fabrica = FabricaDeGitHub.__new__(FabricaDeGitHub)
    fabrica._autenticacao = _CredencialFalsa(falhar=falhar)
    fabrica._adaptadores = {}
    return fabrica


def test_adaptador_por_instalacao_satisfaz_o_contrato():
    fabrica = _fabrica()
    assert isinstance(fabrica.para_instalacao(1), RepositorioPort)


def test_instalacoes_distintas_recebem_adaptadores_distintos():
    """Cada organização responde com as credenciais dela, não com as de outra."""
    fabrica = _fabrica()

    primeira = fabrica.para_instalacao(111)
    segunda = fabrica.para_instalacao(222)

    assert primeira is not segunda
    assert fabrica._autenticacao.instalacoes_pedidas == [111, 222]


def test_adaptador_da_mesma_instalacao_e_reaproveitado():
    """A credencial renova o token sozinha: recriar o adaptador seria desperdício."""
    fabrica = _fabrica()

    primeira = fabrica.para_instalacao(111)
    segunda = fabrica.para_instalacao(111)

    assert primeira is segunda
    assert fabrica._autenticacao.instalacoes_pedidas == [111]


def test_falha_de_credencial_vira_erro_proprio():
    fabrica = _fabrica(falhar=True)
    with pytest.raises(ErroDeCredencialDoApp, match="instalação 999"):
        fabrica.para_instalacao(999)


# --- Construção do adaptador -------------------------------------------------

def test_adaptador_aceita_cliente_ja_autenticado():
    """É por aqui que a credencial da instalação chega ao adaptador."""
    adaptador = GitHubAdapter(cliente="cliente-falso")
    assert adaptador._cliente == "cliente-falso"


def test_adaptador_sem_token_e_sem_cliente_e_recusado():
    with pytest.raises(ValueError, match="token ou um cliente"):
        GitHubAdapter()
