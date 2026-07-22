---
id: SEG-001
titulo: Segredos não podem estar no código-fonte
categoria: seguranca
severidade: obrigatoria
status: ativa
linguagens: [python]
aplica_se_a:
  - "**/*.py"
excecoes:
  - "tests/**"
---

## Regra

Tokens de acesso, chaves de API, senhas e strings de conexão jamais devem ser
escritos diretamente no código. Devem ser lidos de variáveis de ambiente ou de
arquivo de configuração não versionado.

## Motivação

Credenciais escritas no código são publicadas no histórico do controle de
versão. Uma vez enviadas ao repositório, precisam ser revogadas mesmo que sejam
removidas depois, porque permanecem acessíveis em commits anteriores. Manter
segredos fora do código também permite usar credenciais diferentes por ambiente.

## Como identificar

Atribuições de literais de texto a variáveis com nomes como token, key,
api_key, secret, password ou senha; e literais com formato reconhecível de
credencial.

## Exemplo incorreto

```python
GITHUB_TOKEN = "github_pat_11ABCDE_exemplo_de_token_exposto"
cliente = Github(auth=Auth.Token(GITHUB_TOKEN))
```

## Exemplo correto

```python
import os

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
cliente = Github(auth=Auth.Token(GITHUB_TOKEN))
```
