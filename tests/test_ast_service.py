"""Testes do serviço de AST (linguagem, esqueleto e isolamento do que mudou)."""

import pytest

from app.services.ast_service import (
    elementos_alterados,
    extrair_esqueleto,
    identificar_linguagem,
)

# Arquivo de exemplo. Números de linha (importam para os testes de intervalo):
#   1 def soma(a, b):
#   2     return a + b
#   3
#   4 class Calculadora:
#   5     def __init__(self, base):
#   6         self.base = base
#   7
#   8     async def calcular(self, x, y=0):
#   9         return x + y + self.base
CODIGO = (
    "def soma(a, b):\n"
    "    return a + b\n"
    "\n"
    "class Calculadora:\n"
    "    def __init__(self, base):\n"
    "        self.base = base\n"
    "\n"
    "    async def calcular(self, x, y=0):\n"
    "        return x + y + self.base\n"
)


def test_identificar_linguagem_reconhece_python():
    assert identificar_linguagem("app/core/pipeline.py") == "python"


def test_identificar_linguagem_ignora_nao_suportadas():
    assert identificar_linguagem("README.md") is None
    assert identificar_linguagem("script.js") is None


def test_esqueleto_encontra_todos_os_elementos_em_ordem():
    nomes = [e.nome for e in extrair_esqueleto(CODIGO)]
    assert nomes == [
        "soma",
        "Calculadora",
        "Calculadora.__init__",
        "Calculadora.calcular",
    ]


def test_esqueleto_classifica_os_tipos():
    por_nome = {e.nome: e for e in extrair_esqueleto(CODIGO)}
    assert por_nome["soma"].tipo == "funcao"
    assert por_nome["Calculadora"].tipo == "classe"
    assert por_nome["Calculadora.__init__"].tipo == "metodo"


def test_esqueleto_preserva_async_e_valores_padrao_na_assinatura():
    por_nome = {e.nome: e for e in extrair_esqueleto(CODIGO)}
    assert (
        por_nome["Calculadora.calcular"].assinatura
        == "async def calcular(self, x, y=0)"
    )


def test_esqueleto_recusa_codigo_invalido():
    with pytest.raises(SyntaxError):
        extrair_esqueleto("def quebrado(:")


def test_elementos_alterados_isola_apenas_o_que_mudou():
    # A linha 9 (dentro de calcular) foi alterada.
    nomes = {e.nome for e in elementos_alterados(CODIGO, {9})}
    # A classe que contém o método também aparece (contexto proposital).
    assert nomes == {"Calculadora", "Calculadora.calcular"}
    assert "soma" not in nomes
    assert "Calculadora.__init__" not in nomes
