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

Blocos que capturam exceções não podem descartá-las sem tratamento ou registro. Toda exceção capturada deve ser tratada, registrada em log ou repropagada com contexto adicional.

A amplitude da captura não é o critério. Um `except Exception` que registra o erro em log, o repropaga ou o converte em erro de domínio está em conformidade. O que esta regra proíbe é o erro desaparecer sem deixar rastro.

## Motivação

Capturar uma exceção genérica e seguir a execução silenciosamente esconde falhas: o sistema aparenta funcionar enquanto opera com estado inválido, e o diagnóstico do problema real fica muito mais caro. O custo aparece longe da causa, geralmente em produção.

## Como identificar

Examine o CORPO do bloco `except`, não a exceção capturada. Há violação quando o corpo é apenas `pass`, ou quando retorna, continua ou segue adiante sem registrar o erro em lugar nenhum.

Não há violação quando o corpo contém chamada de log, `raise`, ou a conversão da exceção em um erro de domínio — mesmo que a captura seja de `Exception`. Se o corpo do bloco não estiver visível no trecho recebido, não aponte esta regra.

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
