"""Testes da leitura do SDD (frontmatter YAML + seções markdown, um arquivo por regra)."""

from pathlib import Path

import pytest

from app.services.sdd_service import (
    ErroDeSDD,
    carregar_regras,
    carregar_sdd,
)

RAIZ_DO_PROJETO = Path(__file__).parent.parent

REGRA_COMPLETA = """---
id: ARQ-001
titulo: O núcleo não deve importar adaptadores
categoria: arquitetura
severidade: obrigatoria
status: ativa
linguagens: [python]
aplica_se_a:
  - "app/core/**"
excecoes: []
---

## Regra

Módulos do núcleo não podem importar adaptadores concretos.

## Motivação

A dependência precisa apontar sempre para dentro.

## Como identificar

Imports de `app.adapters` em arquivos sob `app/core/`.

## Exemplo incorreto

```python
from app.adapters.gemini_adapter import GeminiAdapter
```

## Exemplo correto

```python
from app.core.ports import LLMPort
```
"""


def _escrever_regra(diretorio: Path, nome: str, conteudo: str) -> Path:
    arquivo = diretorio / nome
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_le_metadados_do_frontmatter(tmp_path):
    _escrever_regra(tmp_path, "ARQ-001.md", REGRA_COMPLETA)

    regra = carregar_regras(tmp_path)[0]

    assert regra.identificador == "ARQ-001"
    assert regra.categoria == "arquitetura"
    assert regra.severidade == "obrigatoria"
    assert regra.linguagens == ("python",)
    assert regra.aplica_se_a == ("app/core/**",)


def test_le_secoes_do_corpo(tmp_path):
    _escrever_regra(tmp_path, "ARQ-001.md", REGRA_COMPLETA)

    regra = carregar_regras(tmp_path)[0]

    assert regra.regra.startswith("Módulos do núcleo")
    assert regra.motivacao.startswith("A dependência")
    assert "app.adapters" in regra.como_identificar
    assert "GeminiAdapter" in regra.exemplo_incorreto
    assert "LLMPort" in regra.exemplo_correto


def test_colecoes_sao_tuplas_para_manter_imutabilidade(tmp_path):
    _escrever_regra(tmp_path, "ARQ-001.md", REGRA_COMPLETA)

    regra = carregar_regras(tmp_path)[0]

    assert isinstance(regra.linguagens, tuple)
    assert isinstance(regra.aplica_se_a, tuple)


def test_arquivo_sem_frontmatter_e_rejeitado(tmp_path):
    _escrever_regra(tmp_path, "ruim.md", "## Regra\n\nSem frontmatter.\n")

    with pytest.raises(ErroDeSDD, match="frontmatter"):
        carregar_regras(tmp_path)


def test_campo_obrigatorio_ausente_e_rejeitado(tmp_path):
    sem_severidade = REGRA_COMPLETA.replace("severidade: obrigatoria\n", "")
    _escrever_regra(tmp_path, "ruim.md", sem_severidade)

    with pytest.raises(ErroDeSDD, match="severidade"):
        carregar_regras(tmp_path)


def test_secao_regra_ausente_e_rejeitada(tmp_path):
    sem_regra = REGRA_COMPLETA.replace("## Regra", "## Outra coisa")
    _escrever_regra(tmp_path, "ruim.md", sem_regra)

    with pytest.raises(ErroDeSDD, match="regra"):
        carregar_regras(tmp_path)


def test_categoria_fora_do_vocabulario_e_rejeitada(tmp_path):
    _escrever_regra(tmp_path, "ARQ-001.md", REGRA_COMPLETA)
    configuracao = {"categorias": ["seguranca"], "severidades": ["obrigatoria"]}

    with pytest.raises(ErroDeSDD, match="categoria"):
        carregar_regras(tmp_path, configuracao)


def test_regra_descontinuada_nao_e_carregada(tmp_path):
    (tmp_path / "regras").mkdir()
    _escrever_regra(tmp_path / "regras", "ativa.md", REGRA_COMPLETA)
    _escrever_regra(
        tmp_path / "regras",
        "velha.md",
        REGRA_COMPLETA.replace("id: ARQ-001", "id: ARQ-999").replace(
            "status: ativa", "status: descontinuada"
        ),
    )

    identificadores = [r.identificador for r in carregar_sdd(tmp_path)]

    assert identificadores == ["ARQ-001"]


def test_sdd_do_projeto_e_valido():
    """O SDD real do repositório deve carregar e validar sem erros."""
    regras = carregar_sdd(RAIZ_DO_PROJETO / "sdd")

    assert len(regras) == 6
    identificadores = {r.identificador for r in regras}
    assert identificadores == {
        "ARQ-001",
        "ARQ-002",
        "ARQ-003",
        "SEG-001",
        "QUA-001",
        "DOC-001",
    }
    # Toda regra precisa ter enunciado e motivação preenchidos.
    assert all(r.regra and r.motivacao for r in regras)
