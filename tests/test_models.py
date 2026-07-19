"""Testes dos modelos de domínio (igualdade por valor e imutabilidade)."""

import dataclasses

import pytest

from app.core.models import PullRequest


def test_pullrequest_compara_por_valor():
    # Dois PRs com os mesmos dados são considerados iguais (dataclass).
    assert PullRequest("dono/repo", 1) == PullRequest("dono/repo", 1)


def test_pullrequest_e_imutavel():
    pr = PullRequest("dono/repo", 1)
    # frozen=True: tentar alterar deve falhar.
    with pytest.raises(dataclasses.FrozenInstanceError):
        pr.numero = 2
