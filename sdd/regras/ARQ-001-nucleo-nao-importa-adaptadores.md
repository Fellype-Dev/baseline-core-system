---
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

Módulos do núcleo não podem importar adaptadores concretos nem bibliotecas de
acesso a rede, banco de dados ou APIs externas. O núcleo depende apenas de suas
próprias abstrações (portas) e de seus modelos de domínio.

## Motivação

A dependência precisa apontar sempre para dentro: adaptadores conhecem o núcleo,
o núcleo nunca conhece os adaptadores. Isso permite substituir uma tecnologia
sem alterar regra de negócio, e torna o núcleo testável sem infraestrutura.
Quando o núcleo importa um adaptador, essa substituição deixa de ser possível e
os testes passam a exigir rede ou banco.

## Como identificar

Em arquivos sob o diretório do núcleo, procure imports de módulos de adaptadores
ou de bibliotecas de entrada e saída (clientes HTTP, SDKs de nuvem, drivers de
banco).

## Exemplo incorreto

```python
# app/core/pipeline.py
from app.adapters.gemini_adapter import GeminiAdapter

class PipelineDeRevisao:
    def __init__(self):
        self.llm = GeminiAdapter(api_key="...")
```

## Exemplo correto

```python
# app/core/pipeline.py
from app.core.ports import LLMPort

class PipelineDeRevisao:
    def __init__(self, llm: LLMPort):
        self.llm = llm
```
