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
Pull Request aberto, atualizado ou reaberto
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

**As regras pertencem à organização, não à ferramenta.** Cada repositório
revisado declara as suas em um diretório `sdd/`, versionado junto ao próprio
código. A ferramenta lê esse diretório do repositório no momento da revisão —
quem usa o sistema não precisa ter acesso ao código-fonte dele.

Duas consequências: alterar uma regra é um Pull Request auditável no
repositório da organização, e organizações distintas são avaliadas por
critérios distintos pela mesma instalação da ferramenta.

> O diretório `sdd/` deste repositório é um **exemplo de referência**, usado
> também como corpus da avaliação empírica. Ele não governa os repositórios
> revisados.

As regras ficam **uma por arquivo**, em `sdd/regras/<ID>-<slug>.md`. Cada
arquivo combina metadados legíveis por máquina com texto em linguagem natural:

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

Baixe o modelo de linguagem e crie a variante usada pela ferramenta:

```bash
ollama pull gpt-oss:20b
ollama create marvin -f Modelfile
```

O segundo comando não é opcional. O Ollama executa com janela de contexto de
4096 tokens por padrão, independente do que o modelo suporta, e **trunca em
silêncio** o prompt que a excede — a revisão sai vazia, ou pior, apoiada em
metade do arquivo. O `Modelfile` na raiz do projeto amplia a janela; o
endpoint compatível com a OpenAI não aceita esse ajuste na requisição.

O SDD de cada repositório é lido automaticamente no momento da revisão, e
reindexado apenas quando muda. O script abaixo serve para indexar um SDD local
— usado pela avaliação empírica, não pelo fluxo de revisão:

```bash
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

São 219 testes. Os marcados como `integracao` exigem o índice vetorial
construído e o modelo de linguagem em execução; os demais rodam sem rede e são
executados a cada envio pela integração contínua.

## Avaliação empírica

O sistema é medido contra três conjuntos distintos, separação que sustenta os
números relatados:

- `avaliacao/casos.yml` — corpus de **desenvolvimento**, usado para diagnosticar
  o comportamento e escolher entre estratégias de indexação;
- `avaliacao/validacao.yml` — conjunto **reservado**, escrito depois de fixada a
  configuração, com gabarito definido antes da primeira execução;
- `avaliacao/contexto.yml` — conjunto **reservado e adversarial**, com diffs
  parciais no formato que o GitHub entrega. Existe porque os dois primeiros
  declaram apenas o código final e o harness os converte em diff de arquivo
  novo: o modelo recebe o arquivo inteiro, e nenhuma falha de contexto pode
  aparecer neles.

Um conjunto reservado vale uma medição: depois de observado, ele passa a
informar decisões e deixa de ser cego.

```bash
venv\Scripts\python.exe avaliacao\executar.py --corpus validacao
venv\Scripts\python.exe avaliacao\executar.py --corpus contexto --sem-corpo
```

O harness reproduz o caminho de produção, inclusive o descarte de regras que o
modelo cite fora das recuperadas. Quando o serviço está no ar, o índice
embarcado fica travado; use `--dados <caminho>` para dar à avaliação um índice
próprio.

Efeito do contexto enviado ao modelo, cinco repetições, com
`qwen2.5-coder:14b`:

| Configuração | Precisão | Revocação | F1 | Alarme falso |
|---|---|---|---|---|
| Só o diff | 64,5% | 80,0% | 71,4% | 11/30 |
| **Diff + corpo dos elementos** | **96,0%** | **96,0%** | **96,0%** | **1/30** |

O ganho não vem de uma mudança só, e as duas não somam — elas se destravam. A
regra QUA-001 instrui a examinar o corpo do bloco `except` antes de apontar
exceção silenciada; essa instrução é inexecutável quando o prompt recebe apenas
o diff, que pode terminar no cabeçalho do bloco. Com a regra precisa e sem o
corpo, o sistema erra MAIS do que errava com a regra vaga: 71,4% contra 76,4%
na configuração anterior. É a mesma instrução, com e sem a informação que a
torna verificável.

Efeito do modelo, no mesmo corpus, mesmo SDD e mesma configuração de contexto:

| Modelo | Precisão | Revocação | F1 | Alarme falso |
|---|---|---|---|---|
| `qwen2.5-coder:14b` | 96,0% | 96,0% | 96,0% | 1/30 |
| **`gpt-oss:20b`** (adotado) | **100%** | 92,0% | 95,8% | **0/30** |

O F1 empata; o que muda é o caráter do erro. O `gpt-oss:20b` nunca acusou
código em conformidade, e em troca deixou passar uma regra secundária em um
caso que viola duas. Para uma ferramenta que comenta em Pull Request de outra
pessoa, acusar à toa custa mais caro do que calar — daí a escolha.

> Estes números são de **desenvolvimento**, não de teste cego. O conjunto
> `contexto` foi usado para diagnosticar as falhas e ajustar tanto o prompt
> quanto o texto da QUA-001. Um número de validação exige um conjunto escrito
> depois de congelada a configuração, com gabarito fixado antes da primeira
> execução.

Duas alterações de redação de regra, em SEG-001 e ARQ-003, foram propostas para
reduzir apontamento indevido e **revertidas por piorarem a medição** (F1 de
96,0% para 87,3%). A redação de uma regra tem efeito mensurável e não-óbvio
sobre o resultado, às vezes de sinal contrário ao pretendido: convém medi-la,
não apenas revisá-la.

## Limitações conhecidas

- **Apenas Python.** A sanitização usa a biblioteca `ast` nativa; outras
  linguagens exigiriam um analisador como o tree-sitter.
- **Banco vetorial embarcado.** O Qdrant trava o diretório de dados para um
  processo por vez, então reindexar o SDD exige parar o serviço.
- **Truncamento do modelo de embedding.** O modelo utilizado corta a entrada em
  torno de 128 tokens, o que limita quanto do texto de uma regra participa da
  busca.
- **Revisão não é reprodutível.** A defesa contra injeção gera uma marca
  aleatória a cada chamada, então o mesmo Pull Request produz prompts
  diferentes e pode receber revisões diferentes, mesmo com temperatura zero. É
  o preço da defesa: uma marca fixa seria previsível para quem escrevesse o
  código revisado. A consequência prática é que comparar duas configurações
  exige repetição, não uma execução de cada.
- **Sobre-apontamento.** O erro residual do modelo é por excesso: ele aponta
  regras recuperadas que não foram violadas. Reduzido de 11 para 1 alarme em 30
  avaliações de código conforme, mas não eliminado.
- **Recorte por arquivo.** Cada arquivo é avaliado isoladamente, então nenhuma
  questão cujo esclarecimento esteja em outro arquivo é decidível. Um adaptador
  que recebe uma credencial por parâmetro parece guardá-la no código, porque a
  leitura de `os.getenv` está no módulo de configuração; um adaptador que cumpre
  um invariante declarado na porta parece inventá-lo, porque `ports.py` não
  chega ao prompt. Resolver isso exigiria montar o grafo de dependências entre
  os arquivos alterados.
- **A revisão vale o que vale o SDD.** Uma regra ampla, vaga ou fora do domínio
  arquitetural degrada toda a revisão, e não só os apontamentos sobre ela: a
  recuperação devolve um número fixo de regras por arquivo, então uma regra que
  se aplica a tudo ocupa vaga de outra que importava. Foi o caso de uma regra de
  documentação que valia para `**/*.py` — removida do SDD de referência.
- **Processamento em memória.** A revisão roda em segundo plano no próprio
  processo; um reinício durante o processamento perde o trabalho em andamento.
- **Uma revisão por Pull Request.** A cada nova revisão o comentário anterior é
  reescrito, e não há histórico das revisões passadas dentro do PR.

## Licença

Trabalho acadêmico. Uso e redistribuição mediante citação do autor.
