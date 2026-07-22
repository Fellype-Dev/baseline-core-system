---
id: ARQ-003
titulo: Adaptadores não devem conter regras de negócio
categoria: arquitetura
severidade: obrigatoria
status: ativa
linguagens: [python]
aplica_se_a:
  - "app/adapters/**"
  - "app/api/**"
excecoes: []
---

## Regra

A responsabilidade de um adaptador é traduzir entre o mundo externo e o
vocabulário do domínio. Decisões de negócio, cálculos e validações que definem o
comportamento do produto pertencem ao núcleo.

## Motivação

Um adaptador que decide o que o sistema faz, e não apenas como ele se comunica,
acumula responsabilidade indevida. A regra de negócio fica presa a uma
tecnologia, deixa de ser reaproveitável e só pode ser testada com a
infraestrutura ligada.

## Como identificar

Em adaptadores, procure condicionais que decidam comportamento do produto,
montagem de prompts, cálculos de domínio ou validações de negócio — em vez de
apenas conversão de formatos e chamadas ao serviço externo.

## Exemplo incorreto

```python
class GeminiAdapter(LLMPort):
    def avaliar(self, codigo: str) -> str:
        # O adaptador decidindo COMO revisar: isso é regra de negócio.
        prompt = f"Revise este código considerando as regras da empresa: {codigo}"
        if len(codigo) > 1000:
            prompt += " Seja breve."
        return self._modelo.generate_content(prompt).text
```

## Exemplo correto

```python
class GeminiAdapter(LLMPort):
    def avaliar(self, prompt: str) -> str:
        # Só traduz: recebe texto pronto do núcleo e devolve a resposta.
        return self._modelo.generate_content(prompt).text
```
