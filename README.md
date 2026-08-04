# Revisor Arquitetural de Pull Requests

Ferramenta que revisa Pull Requests do GitHub verificando a conformidade do
código com as regras arquiteturais da própria organização, e publica um
feedback didático no próprio PR.

Diferente de um analisador estático, que verifica sintaxe e boas práticas
gerais, esta ferramenta avalia o código contra um documento de especificação
(**SDD**) versionado no repositório — as regras são da organização, não da
ferramenta.

Trabalho de Conclusão de Curso — Centro Universitário Campo Real.
Autor: Fellype Kekis. Orientador: Enrique Augusto da Roza.

---

## Como funciona

```
Pull Request aberto
        │
        ▼
  Webhook (FastAPI)
        │
        ▼
  Arquivos alterados ──────────► GitHub (PyGithub)
        │
        ▼
  Sanitização por AST            extrai só o esqueleto lógico que mudou,
        │                        descartando ruído textual
        ▼
  Recuperação de regras ───────► Qdrant + embeddings locais (RAG)
        │                        busca semântica sobre o SDD
        ▼
  Avaliação ───────────────────► modelo de linguagem aberto, executado local
        │
        ▼
  Comentário publicado no PR
```

Cada etapa é observável em tempo real pela página `/fluxo`.

## Arquitetura

Arquitetura hexagonal (Ports & Adapters). O núcleo declara *portas* segundo a
sua necessidade, e os adaptadores se curvam a esses contratos — nunca o
contrário. A dependência aponta sempre para dentro: `app/adapters` importa de
`app/core`, jamais o inverso.

| Porta | Responsabilidade | Adaptador |
|---|---|---|
| `RepositorioPort` | ler o PR e publicar feedback | `GitHubAdapter` |
| `ConhecimentoPort` | recuperar as regras aplicáveis | `QdrantAdapter` |
| `LLMPort` | avaliar um texto | `LocalLLMAdapter`, `GeminiAdapter` |
| `ObservadorPort` | anunciar o progresso | `ObservadorSSE` |

O benefício deixou de ser teórico: a migração do Gemini (usado como andaime
durante a construção) para um modelo aberto local custou **um novo adaptador e
uma linha no `main.py`**, sem alteração alguma no núcleo.

```
app/
├── core/       modelos, portas e o pipeline — lógica pura, sem infraestrutura
├── services/   filtros do pipeline (AST, diff, SDD, prompt, resultado)
├── adapters/   tradutores para GitHub, Qdrant e modelos de linguagem
└── api/        adaptadores de entrada (webhook, eventos)
sdd/            as regras arquiteturais da organização (a fonte da verdade)
avaliacao/      corpus, gabarito e métricas da avaliação empírica
```

## O documento SDD

As regras ficam versionadas no repositório, **uma por arquivo**, em
`sdd/regras/<ID>-<slug>.md`. Cada arquivo combina metadados legíveis por
máquina com texto em linguagem natural:

```markdown
---
id: SEG-001
titulo: Segredos não podem estar no código-fonte
categoria: seguranca
severidade: obrigatoria
linguagens: [python]
aplica_se_a: ["**/*.py"]
excecoes: ["tests/**"]
---

## Regra
Tokens de acesso, chaves de API e senhas jamais devem ser escritos...

## Motivação
Credenciais no código são publicadas no histórico do controle de versão...
```

Cada campo entrega uma capacidade: `id` dá rastreabilidade ao feedback,
`motivacao` torna o comentário didático, e `aplica_se_a`/`excecoes` descartam
regras inaplicáveis **antes** de acionar o modelo — a principal defesa contra
falsos positivos.

Como um arquivo é, por construção, uma regra completa, o fragmento usado no RAG
é semanticamente íntegro, dispensando o recorte por número de caracteres comum
em sistemas de recuperação.

## Instalação

Requisitos: Python 3.12 e [Ollama](https://ollama.com) (ou qualquer executor com
API compatível com a da OpenAI, como o LM Studio).

```bash
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install -r requirements.lock.txt  # ambiente exato
```

Baixe o modelo e indexe o SDD:

```bash
ollama pull qwen2.5-coder:14b
venv\Scripts\python.exe scripts\indexar_sdd.py --com-exemplos
```

Copie `.env.example` para `.env` e preencha o `GITHUB_TOKEN`
(permissão *Pull requests: Read and write*).

## Execução

```bash
venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

No Windows, `scripts\iniciar_bot.ps1` sobe as três peças (modelo, aplicação e
túnel) e verifica o serviço pelo endereço público.

| Rota | Função |
|---|---|
| `POST /webhook` | recebe os eventos de Pull Request do GitHub |
| `GET /fluxo` | fluxograma do pipeline em tempo real |
| `GET /eventos` | transmissão dos eventos (SSE) |
| `GET /health` | estado do serviço e de suas dependências |

Para expor o serviço ao GitHub em desenvolvimento, um túnel
(`cloudflared tunnel run <nome>`) evita a necessidade de deploy.

## Testes

```bash
venv\Scripts\python.exe -m pytest -m "not integracao"   # rápidos
venv\Scripts\python.exe -m pytest                       # todos
```

São 109 testes. Os marcados como `integracao` exigem o índice vetorial
construído e o modelo de linguagem em execução; os demais rodam sem rede e são
executados a cada envio pela integração contínua.

## Avaliação empírica

O sistema é medido contra dois conjuntos distintos, separação que sustenta os
números relatados:

- `avaliacao/casos.yml` — corpus de **desenvolvimento**, usado para diagnosticar
  o comportamento e escolher entre estratégias de indexação;
- `avaliacao/validacao.yml` — conjunto **reservado**, escrito depois de fixada a
  configuração, com gabarito definido antes da primeira execução.

```bash
venv\Scripts\python.exe avaliacao\executar.py --corpus validacao
```

Resultado no conjunto reservado, com `qwen2.5-coder:14b`:

| Métrica | Valor |
|---|---|
| Precisão | 80,0% |
| Revocação | 100% |
| F1 | 88,9% |
| Alarme falso em código correto | 0% |

Nenhuma violação real passou despercebida, e nenhum arquivo em conformidade
recebeu apontamento indevido. Os erros observados foram todos por excesso: o
modelo tende a apontar regras recuperadas que não foram violadas.

## Limitações conhecidas

- **Apenas Python.** A sanitização usa a biblioteca `ast` nativa; outras
  linguagens exigiriam um analisador como o tree-sitter.
- **Banco vetorial embarcado.** O Qdrant trava o diretório de dados para um
  processo por vez, então reindexar o SDD exige parar o serviço.
- **Truncamento do modelo de embedding.** O modelo utilizado corta a entrada em
  torno de 128 tokens, o que limita quanto do texto de uma regra participa da
  busca.
- **Processamento em memória.** A revisão roda em segundo plano no próprio
  processo; um reinício durante o processamento perde o trabalho em andamento.
- **Apenas eventos de abertura** de Pull Request são tratados.

## Licença

Trabalho acadêmico. Uso e redistribuição mediante citação do autor.
