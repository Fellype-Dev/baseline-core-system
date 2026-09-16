

#   1. Ollama       serve o modelo de linguagem local (porta 11434)
#   2. uvicorn      a aplicacao FastAPI que recebe o webhook (porta 8000)
#   3. cloudflared  o tunel que publica o servico em revisor.fellypekekis.dev

$ErrorActionPreference = "Stop"

$RAIZ = Split-Path -Parent $PSScriptRoot
$PYTHON = Join-Path $RAIZ "venv\Scripts\python.exe"
$OLLAMA = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
$CLOUDFLARED = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$ENDERECO = "https://revisor.fellypekekis.dev"

function Esta-Escutando($porta) {
    [bool](Get-NetTCPConnection -LocalPort $porta -State Listen -ErrorAction SilentlyContinue)
}

Write-Host "=== Revisor Arquitetural - inicializacao ===" -ForegroundColor Cyan

# 1. Modelo de linguagem
if (Esta-Escutando 11434) {
    Write-Host "[1/3] Ollama ja estava no ar." -ForegroundColor Green
} else {
    Write-Host "[1/3] Iniciando o Ollama..."
    Start-Process $OLLAMA -ArgumentList "serve" -WindowStyle Minimized
    Start-Sleep -Seconds 5
    if (Esta-Escutando 11434) {
        Write-Host "      Ollama no ar." -ForegroundColor Green
    } else {
        Write-Host "      FALHA: o Ollama nao subiu." -ForegroundColor Red
        exit 1
    }
}

# 2. Aplicacao
if (Esta-Escutando 8000) {
    Write-Host "[2/3] Servidor da aplicacao ja estava no ar." -ForegroundColor Green
} else {
    Write-Host "[2/3] Iniciando a aplicacao. Carrega o modelo de embeddings, demora."
    Start-Process $PYTHON -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","8000" -WorkingDirectory $RAIZ
    # Espera a porta aceitar conexao em vez de assumir um tempo fixo.
    for ($i = 0; $i -lt 30; $i++) {
        if (Esta-Escutando 8000) { break }
        Start-Sleep -Seconds 2
    }
    if (Esta-Escutando 8000) {
        Write-Host "      Aplicacao no ar." -ForegroundColor Green
    } else {
        Write-Host "      FALHA: a aplicacao nao subiu. Veja a janela do uvicorn." -ForegroundColor Red
        exit 1
    }
}

# 3. Tunel
if (Get-Process cloudflared -ErrorAction SilentlyContinue) {
    Write-Host "[3/3] Tunel ja estava no ar." -ForegroundColor Green
} else {
    Write-Host "[3/3] Iniciando o tunel..."
    # --protocol http2 em vez do QUIC padrao. O QUIC roda sobre UDP, e o Windows
    # esgota o buffer de envio quando ha stream longo (o SSE de /eventos),
    # derrubando a conexao com WSAENOBUFS. O tunel se recupera sozinho, mas uma
    # entrega de webhook que caia nesse intervalo se perde: o GitHub nao repete.
    # HTTP/2 usa TCP e nao passa por esse buffer.
    Start-Process $CLOUDFLARED -ArgumentList "tunnel","--protocol","http2","run","revisor-arquitetural" -WindowStyle Minimized
    Start-Sleep -Seconds 10
    Write-Host "      Tunel iniciado." -ForegroundColor Green
}

# Verificacao fim a fim, pelo endereco publico
Write-Host ""
Write-Host "Verificando pelo endereco publico..."
$pronto = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $saude = Invoke-RestMethod -Uri "$ENDERECO/health" -TimeoutSec 10
        $pronto = $true
        break
    } catch {
        Start-Sleep -Seconds 5
    }
}

Write-Host ""
if ($pronto) {
    Write-Host "=== TUDO NO AR ===" -ForegroundColor Green
    Write-Host "  servico......: $($saude.servico)"
    Write-Host "  modelo.......: $($saude.modelo) ($($saude.llm))"
    Write-Host "  conhecimento.: $($saude.conhecimento)"
    Write-Host "  pronto.......: $($saude.pronto)"
    Write-Host ""
    Write-Host "  Webhook: $ENDERECO/webhook"
    Write-Host "  Conferir de qualquer lugar: $ENDERECO/health"
    Write-Host ""
    Write-Host "  IMPORTANTE: nao deixe o computador suspender." -ForegroundColor Yellow
} else {
    Write-Host "O endereco publico nao respondeu." -ForegroundColor Red
    Write-Host "Confira a janela do cloudflared e as portas 8000 e 11434."
}
