"""Testes do filtro de aplicabilidade (linguagem, escopo de caminho e exceções)."""

import pytest

from app.core.aplicabilidade import regra_se_aplica
from app.core.models import ConsultaDeRegras, RegraArquitetural


def _regra(**ajustes) -> RegraArquitetural:
    """Cria uma regra com valores padrão, sobrescrevendo o que o teste precisa."""
    campos = {
        "identificador": "ARQ-001",
        "titulo": "Regra de teste",
        "categoria": "arquitetura",
        "severidade": "obrigatoria",
        "regra": "Enunciado.",
        "motivacao": "Motivo.",
        "linguagens": ("python",),
        "aplica_se_a": (),
        "excecoes": (),
    }
    campos.update(ajustes)
    return RegraArquitetural(**campos)


def _consulta(caminho: str, linguagem: str = "python") -> ConsultaDeRegras:
    return ConsultaDeRegras(texto="qualquer", caminho=caminho, linguagem=linguagem)


# --- Linguagem ---------------------------------------------------------------


def test_regra_de_outra_linguagem_nao_se_aplica():
    regra = _regra(linguagens=("java",))
    assert not regra_se_aplica(regra, _consulta("app/core/x.py"))


def test_regra_sem_linguagem_declarada_vale_para_qualquer_uma():
    regra = _regra(linguagens=())
    assert regra_se_aplica(regra, _consulta("README.md", linguagem="markdown"))


# --- Escopo de caminho -------------------------------------------------------


def test_regra_sem_escopo_vale_para_todo_o_repositorio():
    regra = _regra(aplica_se_a=())
    assert regra_se_aplica(regra, _consulta("qualquer/lugar.py"))


def test_escopo_de_diretorio_cobre_subdiretorios():
    regra = _regra(aplica_se_a=("app/core/**",))
    assert regra_se_aplica(regra, _consulta("app/core/pipeline.py"))
    assert regra_se_aplica(regra, _consulta("app/core/sub/outro.py"))


def test_escopo_de_diretorio_nao_vaza_para_outros():
    regra = _regra(aplica_se_a=("app/core/**",))
    assert not regra_se_aplica(regra, _consulta("app/adapters/github.py"))


def test_padrao_de_extensao_cobre_arquivo_na_raiz():
    # Caso clássico que o fnmatch erraria: "**/" precisa casar com zero diretórios.
    regra = _regra(aplica_se_a=("**/*.py",))
    assert regra_se_aplica(regra, _consulta("main.py"))
    assert regra_se_aplica(regra, _consulta("app/core/pipeline.py"))


def test_padrao_de_extensao_nao_casa_outra_extensao():
    regra = _regra(aplica_se_a=("**/*.py",), linguagens=())
    assert not regra_se_aplica(regra, _consulta("docs/manual.md"))


def test_asterisco_simples_nao_atravessa_diretorio():
    regra = _regra(aplica_se_a=("app/*.py",))
    assert regra_se_aplica(regra, _consulta("app/main.py"))
    assert not regra_se_aplica(regra, _consulta("app/core/main.py"))


# --- Exceções ----------------------------------------------------------------


def test_excecao_tem_precedencia_sobre_o_escopo():
    regra = _regra(aplica_se_a=("**/*.py",), excecoes=("tests/**",))
    assert regra_se_aplica(regra, _consulta("app/core/x.py"))
    assert not regra_se_aplica(regra, _consulta("tests/test_x.py"))


# --- Windows -----------------------------------------------------------------


def test_caminho_com_barra_invertida_do_windows_e_normalizado():
    regra = _regra(aplica_se_a=("app/core/**",))
    assert regra_se_aplica(regra, _consulta("app\\core\\pipeline.py"))
