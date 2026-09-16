---
id: ARQ-004
titulo: O núcleo recebe suas dependências, não as escolhe
categoria: arquitetura
severidade: obrigatoria
status: ativa
linguagens: [python]
aplica_se_a:
  - "app/core/**"
excecoes: []
---

## Regra

Funções e classes do núcleo recebem por parâmetro as portas de que precisam. O núcleo não lê variáveis de ambiente, não lê arquivos de configuração e não decide qual implementação usar: essa montagem pertence ao ponto de composição da aplicação.

## Motivação

Importar um adaptador é uma forma de acoplamento; escolher um é outra. Um núcleo que lê `os.environ` para decidir entre duas implementações continua preso à infraestrutura mesmo sem importar adaptador algum — só que o acoplamento fica escondido atrás de uma condicional. Receber a dependência pronta mantém a decisão em um único lugar do sistema, torna o núcleo verificável sem ambiente configurado, e faz com que trocar de tecnologia seja alterar a montagem, não a regra de negócio.

## Como identificar

No núcleo, procure leitura de ambiente (`os.getenv`, `os.environ`), leitura de arquivos de configuração, e condicionais que selecionam entre implementações concretas. Procure também dependências obtidas de variáveis de módulo em vez de chegarem pela assinatura da função.

## Exemplo incorreto

```python
# app/core/pipeline.py
import os

def revisar(pr: PullRequest) -> None:
    if os.getenv("USAR_MODELO_LOCAL"):
        llm = LocalLLMAdapter()
    else:
        llm = GeminiAdapter(api_key=os.environ["GEMINI_API_KEY"])
    avaliar(pr, llm)
```

## Exemplo correto

```python
# app/core/pipeline.py
def revisar(pr: PullRequest, llm: LLMPort) -> None:
    avaliar(pr, llm)
```
