---
id: DOC-001
titulo: Não utilizar anos fixos em títulos e documentação
categoria: documentacao
severidade: recomendada
status: ativa
linguagens: [python]
aplica_se_a:
  - "**/*.py"
  - "**/*.md"
excecoes:
  - "CHANGELOG.md"
---

## Regra

Títulos, cabeçalhos e textos de documentação não devem conter anos fixos, como
"Relatório 2025" ou "Guia 2024". Utilize termos atemporais ou datas geradas
dinamicamente.

## Motivação

Referências temporais fixas tornam o material desatualizado na virada do ano e
criam manutenção recorrente em vários pontos do projeto. Textos atemporais
permanecem corretos sem revisão, e datas realmente necessárias devem vir do
sistema, não de literais.

## Como identificar

Literais de texto e títulos em markdown contendo um ano de quatro dígitos,
especialmente próximos de palavras como relatório, guia, versão ou manual.

## Exemplo incorreto

```python
TITULO_DO_RELATORIO = "Relatório de Conformidade 2025"
```

## Exemplo correto

```python
from datetime import date

TITULO_DO_RELATORIO = f"Relatório de Conformidade {date.today().year}"
```
