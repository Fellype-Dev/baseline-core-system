# Implantação — Oracle Cloud (ARM, camada gratuita)

Implantação de referência do sistema. A escolha e os compromissos estão em
"Por que esta configuração", ao final.

**Alvo:** instância `VM.Standard.A1.Flex` da camada *Always Free*, com 4 OCPUs
ARM Ampere e 24 GB de memória, executando a aplicação e o modelo de linguagem.

---

## Antes de começar

Três coisas que atrasam quem não sabe de antemão:

**A capacidade ARM esgota.** `Out of capacity` é a resposta mais comum nas
regiões populares, e pode persistir por dias. Tente cedo, e tente em mais de um
domínio de disponibilidade da sua região. A instância, uma vez criada, é sua.

**O Oracle bloqueia portas em dois lugares.** Abrir a *Security List* da VCN não
basta: a imagem traz regras de `iptables` que recusam tudo além do SSH. Quem
esquece a segunda passa horas depurando um firewall que parece aberto.

**O modelo ocupa 12,8 GB em disco.** O volume gratuito de 50 GB comporta, mas
confira o espaço antes de baixar.

---

## 1. Instância

No console da Oracle: *Compute → Instances → Create instance*.

- **Imagem:** Ubuntu 24.04 (traz Python 3.12, a mesma versão do ambiente de
  desenvolvimento — ver `requirements.lock.txt`)
- **Shape:** `VM.Standard.A1.Flex`, 4 OCPUs, 24 GB
- **Rede:** atribua IP público
- **Chave SSH:** a sua

Guarde o IP público. Daqui em diante, `ssh ubuntu@SEU_IP`.

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

## 4. Modelo de linguagem

```bash
curl -fsSL https://ollama.com/install.sh | sh    # detecta arm64
ollama pull gpt-oss:20b
cd ~/baseline-core-system && ollama create marvin -f Modelfile
```

O `Modelfile` amplia a janela de contexto para 16384. **Sem ele o Ollama usa
4096 e trunca prompts em silêncio** — o motivo está documentado no próprio
arquivo.

### Meça a latência antes de prosseguir

Esta é a informação que decide se a configuração serve, e ela não pode ser
estimada — depende do desempenho do Ampere A1 com a quantização MXFP4:

```bash
venv/bin/python scripts/medir_latencia.py
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
aplicação com o modelo de embeddings carregado; 12,8 GB para o modelo de
linguagem. Os 24 GB da camada gratuita acomodam os dois com folga.

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
a frio. A escolha pela camada gratuita privilegia custo nulo e execução própria,
assumindo a latência como compromisso declarado.

**O que a arquitetura garante.** Nenhuma dessas alternativas exigiria alterar o
núcleo: o modelo é acessado através da `LLMPort`, e trocar de execução local
para provedor é configurar endereço e credencial no `LLMHttpAdapter`. A decisão
é de implantação, não de projeto.
