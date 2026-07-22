---
id: QUA-001
titulo: Exceções não devem ser silenciadas
categoria: qualidade
severidade: recomendada
status: ativa
linguagens: [python]
aplica_se_a:
  - "**/*.py"
excecoes: []
---

## Regra

Blocos que capturam exceções não podem descartá-las sem tratamento ou registro.
Toda exceção capturada deve ser tratada, registrada em log ou repropagada com
contexto adicional.

## Motivação

Capturar uma exceção genérica e seguir a execução silenciosamente esconde
falhas: o sistema aparenta funcionar enquanto opera com estado inválido, e o
diagnóstico do problema real fica muito mais caro. O custo aparece longe da
causa, geralmente em produção.

## Como identificar

Blocos `except` cujo corpo seja apenas `pass`, ou que capturem `Exception` de
forma ampla sem registrar nem repropagar.

## Exemplo incorreto

```python
try:
    publicar_comentario(pr, texto)
except Exception:
    pass
```

## Exemplo correto

```python
try:
    publicar_comentario(pr, texto)
except GithubException as erro:
    logger.error("Falha ao publicar comentário no PR %s: %s", pr.numero, erro)
    raise
```
