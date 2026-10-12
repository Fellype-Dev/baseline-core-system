# Implantação — Oracle Cloud (ARM, camada gratuita)

Implantação de referência do sistema. A escolha e os compromissos estão em
"Por que esta configuração", ao final.

**Alvo:** instância `VM.Standard.A1.Flex` da camada *Always Free*, com 2 OCPUs
ARM Ampere e 12 GB de memória, executando a aplicação e o modelo de linguagem.

> **Os limites da camada gratuita mudaram em junho de 2026.** Eram 4 OCPUs e
> 24 GB; passaram a ser 2 OCPUs e 12 GB, e a Oracle começou a derrubar
> instâncias acima disso em 18 de agosto de 2026. A mudança não foi anunciada —
> apenas a documentação foi alterada. Guias escritos antes dessa data, inclusive
> uma versão anterior deste, descrevem a configuração antiga.
>
> A consequência prática está em "Por que esta configuração": nos 12 GB **não
> cabe o modelo adotado**, e esta implantação usa a variante reduzida.

---

## Antes de começar

Três coisas que atrasam quem não sabe de antemão:

**A capacidade ARM esgota.** `Out of capacity` é a resposta mais comum nas
regiões populares, e pode persistir por dias. Tente cedo, e tente em mais de um
domínio de disponibilidade da sua região. A instância, uma vez criada, é sua.

**O Oracle bloqueia portas em dois lugares.** Abrir a *Security List* da VCN não
basta: a imagem traz regras de `iptables` que recusam tudo além do SSH. Quem
esquece a segunda passa horas depurando um firewall que parece aberto.

**O modelo desta implantação não é o mesmo da máquina de desenvolvimento.** Os
12 GB não comportam o `gpt-oss:20b`, que é o escolhido por medição. Aqui se usa
o `qwen2.5-coder:7b`, com 4,7 GB de pesos. O custo de qualidade está medido.

---

## 1. Instância

No console da Oracle: *Compute → Instances → Create instance*.

**Imagem.** Clique em *Edit* ao lado de "Image and shape" e depois em
*Change image*: escolha **Canonical Ubuntu 24.04**. Essa versão traz Python 3.12,
a mesma do ambiente de desenvolvimento — ver `requirements.lock.txt`. A imagem
padrão é Oracle Linux, que traz outra versão.

**Shape.** *Change shape → Ampere → `VM.Standard.A1.Flex`*. Ajuste os
seletores para **2 OCPUs e 12 GB**. Esse é o total que a camada *Always Free*
concede em instâncias ARM desde junho de 2026; usar tudo em uma única instância
é permitido, e é o que esta implantação faz — o modelo precisa da memória
contígua, então dividir em duas instâncias de 1 OCPU não ajuda.

**Rede.** Deixe criar uma VCN nova e **marque "Assign a public IPv4 address"**.
Sem isso a instância sobe sem endereço alcançável, e corrigir depois dá mais
trabalho do que marcar agora.

**Chave SSH.** Envie a sua chave pública, ou deixe o console gerar o par —
nesse caso **baixe a chave privada antes de criar**, porque ela não é oferecida
de novo.

Guarde o IP público. O usuário da imagem Ubuntu é `ubuntu`:

```bash
ssh -i CAMINHO_DA_CHAVE ubuntu@SEU_IP
```

### Quando aparecer "Out of capacity"

É a resposta mais comum para o shape ARM gratuito, e não significa que a conta
tenha algum problema. O que costuma funcionar:

- **Tentar outro domínio de disponibilidade** (AD-1, AD-2, AD-3), se a sua
  região tiver mais de um — o seletor fica em "Placement".
- **Tentar em horários diferentes.** A capacidade é liberada conforme outras
  contas destroem instâncias.
- **Trocar a região** só vale se você ainda não criou recursos: a região de
  origem da conta não muda depois.

Há relatos frequentes de que contas em *Pay As You Go* conseguem capacidade com
mais facilidade que contas gratuitas, mantendo os mesmos recursos *Always Free*
sem cobrança. Isso exige cadastrar meio de pagamento, e não é garantia — avalie
se compensa no seu caso.

## 2. Portas

**Na VCN** (*Networking → Virtual Cloud Networks → sua VCN → Security Lists*),
adicione regras de entrada para TCP 80 e 443, origem `0.0.0.0/0`.

**Na instância**, as regras locais:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

Confira com `sudo iptables -L INPUT -n --line-numbers` que as duas aparecem
antes da regra `REJECT`.

## 3. Aplicação

```bash
sudo apt update && sudo apt install -y python3.12-venv git nginx

git clone https://github.com/Fellype-Dev/baseline-core-system.git
cd baseline-core-system
python3 -m venv venv
venv/bin/pip install -r requirements.lock.txt
```

O lock instala em Linux sem ajuste: os pacotes exclusivos de Windows levam
marcador de ambiente. Todas as dependências com código compilado — `onnxruntime`,
`tokenizers`, `numpy`, `grpcio`, `pydantic-core` — têm roda pronta para
`aarch64`, então nada é compilado aqui.

Crie o `.env` a partir do `.env.example` e preencha as credenciais **na própria
instância** — elas não devem passar por nenhum outro lugar:

```bash
cp .env.example .env
nano .env
```

Preencha `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH` e
`GITHUB_WEBHOOK_SECRET`. Copie o arquivo `.pem` do App para a instância por
`scp` e aponte o caminho — **fora do diretório do repositório**, para não haver
risco de versioná-lo.

Defina também `LLM_MODELO=marvin-7b`. O padrão do `config.py` é `marvin`, que
aqui não existe — o próximo passo explica por quê.

## 4. Modelo de linguagem

```bash
curl -fsSL https://ollama.com/install.sh | sh    # detecta arm64
ollama pull qwen2.5-coder:7b
cd ~/baseline-core-system && ollama create marvin-7b -f Modelfile.7b
```

**Não é o modelo adotado no trabalho.** O escolhido por medição é o
`gpt-oss:20b`, derivado em `marvin` pelo `Modelfile` da raiz, e ele não cabe
nos 12 GB desta instância. A conta está em "Por que esta configuração".

O `Modelfile.7b` amplia a janela de contexto para 16384. **Sem ele o Ollama usa
4096 e trunca prompts em silêncio** — o motivo está documentado no próprio
arquivo.

### Meça a latência antes de prosseguir

Esta é a informação que decide se a configuração serve, e ela não pode ser
estimada — depende do desempenho de 2 núcleos Ampere A1 com um modelo denso de
7 B:

```bash
LLM_MODELO=marvin-7b venv/bin/python scripts/medir_latencia.py
```

Confira também a memória enquanto o modelo responde, porque a folga calculada
em "Por que esta configuração" é estimativa:

```bash
free -h && ollama ps
```

Se um arquivo pequeno levar mais que uns poucos minutos, releia
"Por que esta configuração" antes de seguir.

## 5. Serviço

`/etc/systemd/system/revisor.service`:

```ini
[Unit]
Description=Revisor Arquitetural de Pull Requests
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/baseline-core-system
ExecStart=/home/ubuntu/baseline-core-system/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now revisor
sudo systemctl status revisor
```

A aplicação escuta apenas em `127.0.0.1`: quem fala com a internet é o nginx.

## 6. Domínio e TLS

Aponte um registro `A` do seu domínio para o IP público — por exemplo
`revisor.fellypekekis.dev`. Depois:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d revisor.fellypekekis.dev
```

O certbot edita a configuração do nginx e renova sozinho. Complete o
`server` com o repasse para a aplicação:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # O /eventos é um fluxo contínuo (SSE): sem isto o nginx segura a
    # resposta em buffer e a página do fluxograma fica parada.
    proxy_buffering off;
    proxy_read_timeout 3600s;
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

Confira de fora da rede: `https://revisor.fellypekekis.dev/health`.

## 7. GitHub App

Em *Settings → Developer settings → GitHub Apps → Marvin → General*, troque a
**Webhook URL** para `https://revisor.fellypekekis.dev/webhook`.

Abra um Pull Request de teste. Se não chegar comentário, a entrega está em
*Advanced*, com o que o servidor respondeu — e o botão **Redeliver**.

---

## Por que esta configuração

**A aplicação é leve e o modelo é pesado.** Medido: 662 MB residentes para a
aplicação com o modelo de embeddings carregado. O modelo de linguagem é a
restrição, e depois do corte de junho de 2026 ele passou a não caber.

O orçamento de memória, com janela de contexto de 16384:

| | gpt-oss:20b | qwen2.5-coder:14b | qwen2.5-coder:7b |
|---|---|---|---|
| Pesos | 13,0 GB | 9,0 GB | 4,7 GB |
| Cache de atenção | ~0,8 GB | ~3,0 GB | ~0,9 GB |
| Aplicação e embeddings | 0,7 GB | 0,7 GB | 0,7 GB |
| Sistema | ~0,5 GB | ~0,5 GB | ~0,5 GB |
| **Total** | **~15,0 GB** | **~13,2 GB** | **~6,8 GB** |

Os valores de cache são calculados a partir dos parâmetros de arquitetura de
cada modelo, não medidos — confirme na instância.

O resultado contraintuitivo está na coluna do meio. **O `qwen2.5-coder:14b`
também não cabe**, apesar de ocupar menos disco que o `gpt-oss:20b`: tem 48
camadas com cabeças de 128 dimensões, contra 24 camadas de 64, e o cache de
atenção fica quase quatro vezes maior. Reduzir o cache pela metade com
`OLLAMA_KV_CACHE_TYPE=q8_0` deixa cerca de 300 MB de margem, o que estoura na
primeira carga.

Daí a variante de 7B, que cabe com folga de 5 GB.

**Sem GPU, o custo é latência.** Medição comparativa no ambiente de
desenvolvimento, com o mesmo prompt:

| | Prompt (prefill) | Geração |
|---|---|---|
| GPU (Radeon RX 9070) | 1.694 tok/s | 79 tok/s |
| CPU | 60 tok/s | 12,7 tok/s |

A penalidade é de 28× no processamento do prompt e 6× na geração. A diferença
não é uniforme porque as duas fases são limitadas por recursos distintos —
prefill é limitado por computação, geração por banda de memória. E a carga
deste sistema é prefill-pesada: prompt longo (regras, diff e corpo numerado),
resposta curta e estruturada. É o formato que mais penaliza execução em CPU.

Essa medição foi feita com 16 núcleos. **A instância tem 2**, e o corte de
junho de 2026 tirou metade do que havia antes. Some-se um detalhe que agrava: o
`gpt-oss:20b` é um modelo de mistura de especialistas, com 3,6 B de parâmetros
ativos por token, enquanto o `qwen2.5-coder:7b` é denso e ativa todos os 7 B.
Em memória o 7B é menos da metade; em cálculo por token é quase o dobro. Meça
na instância antes de assumir qualquer número — é o que o passo seguinte pede.

**Por que mesmo assim.** Revisão de Pull Request é assíncrona: ninguém aguarda
a resposta na tela, e um comentário que chega em alguns minutos cumpre a mesma
função que um revisor humano cumpriria em horas. Em troca, o código revisado e
as regras da organização não deixam a infraestrutura onde o sistema está
implantado — propriedade que seria perdida ao delegar a inferência a um
provedor, e que sustenta parte da justificativa do trabalho.

**Alternativas consideradas.** Instância com GPU dedicada resolve a latência,
mas custa cerca de duas ordens de grandeza mais por mês. Provedor de inferência
com API compatível custaria centavos por Pull Request e seria mais rápido, ao
preço de submeter o código revisado a terceiros. Inferência *serverless* com
GPU preservaria parte da propriedade e o custo, ao preço de latência de partida
a frio.

Depois do corte, uma quarta alternativa passou a merecer consideração séria:
**VPS ARM pago com memória suficiente para o modelo adotado**. Um Hetzner CAX31
dá 8 vCPUs e 16 GB por cerca de €21 ao mês, o que acomoda o `gpt-oss:20b` e
quadruplica a CPU disponível. Mantém a configuração medida no trabalho, ao
preço de deixar de ser gratuito.

A escolha pela camada gratuita privilegia custo nulo e execução própria,
assumindo como compromissos declarados a latência e o modelo reduzido.

**O que a arquitetura garante.** Nenhuma dessas alternativas exigiria alterar o
núcleo: o modelo é acessado através da `LLMPort`, e trocar de execução local
para provedor é configurar endereço e credencial no `LLMHttpAdapter`. A decisão
é de implantação, não de projeto.
