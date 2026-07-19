"""
Composition root: o único lugar que monta o sistema inteiro.

Aqui — e somente aqui — os adaptadores concretos (GitHubAdapter e, futuramente,
Qdrant e LLM) são criados e ligados às portas que o núcleo usa. É a "ponta solta"
onde a arquitetura hexagonal se resolve: trocar uma tecnologia significa mudar
uma linha AQUI, e nada mais.

Estado atual: "esqueleto ambulante" (walking skeleton). Recebe o webhook, busca
os arquivos do PR e posta um comentário de teste — ainda sem AST/RAG/LLM.
"""

import uvicorn
from fastapi import FastAPI

import config
from app.adapters.github_adapter import GitHubAdapter
from app.api.webhook import criar_router_webhook
from app.core.models import PullRequest

# Falha cedo, com mensagem clara, se as chaves não estiverem no .env.
config.validar_configuracao()

# --- Montagem das dependências (o "wiring" da arquitetura) ---
# O GitHubAdapter é criado aqui e usado através da porta RepositorioPort.
repositorio = GitHubAdapter(token=config.GITHUB_TOKEN)


def revisar_pull_request(pr: PullRequest) -> None:
    """Ação executada quando um PR chega (versão esqueleto ambulante).

    Por enquanto só exercita a ida-e-volta com o GitHub: lê os arquivos
    alterados e devolve um comentário de teste. O pipeline real (AST → RAG →
    LLM) será plugado aqui nas próximas etapas.

    Observação: esta função é síncrona e bloqueante. Para um protótipo com
    baixo volume tudo bem; mover o trabalho pesado para fora do laço de eventos
    (BackgroundTasks) é uma melhoria planejada para o Conjunto E (resiliência).
    """
    print(f"Processando PR #{pr.numero} em {pr.repositorio}...")

    arquivos = repositorio.obter_arquivos_alterados(pr)
    print(f"  {len(arquivos)} arquivo(s) com alterações encontrados.")

    lista = "\n".join(f"- `{a.caminho}`" for a in arquivos)
    comentario = (
        "Revisão automática em construção.\n\n"
        f"Recebi este Pull Request e identifiquei {len(arquivos)} arquivo(s) "
        "com alterações:\n\n"
        f"{lista}\n\n"
        "As análises de arquitetura (AST, RAG e LLM) serão adicionadas nas "
        "próximas etapas do desenvolvimento."
    )
    repositorio.publicar_comentario(pr, comentario)
    print("  Comentário de teste publicado no PR.")


# --- Aplicação web ---
app = FastAPI(title="Revisor Arquitetural de Pull Requests")
app.include_router(criar_router_webhook(revisar_pull_request))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
