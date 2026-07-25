"""
Teste manual do pipeline completo contra um PR REAL (sem webhook nem servidor).

Chama o mesmo núcleo que o webhook chamaria, com os adaptadores reais montados
no composition root (GitHub + Qdrant + Gemini). Serve para validar o fluxo AST →
RAG → LLM de ponta a ponta antes de expor o serviço.

Dois modos:
    (padrão)   ENSAIO — lê o PR e imprime o comentário no terminal, sem postar.
    --postar   PUBLICA o comentário no PR (escreve no GitHub).

Uso:
    venv/Scripts/python.exe scripts/testar_github.py <usuario/repo> <numero_pr> [--postar]

Exemplo:
    venv/Scripts/python.exe scripts/testar_github.py fellype/teste-pr 1
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from app.core.models import PullRequest  # noqa: E402
from app.core.pipeline import analisar_pull_request, revisar_pull_request  # noqa: E402


def principal() -> None:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    postar = "--postar" in sys.argv[1:]

    if len(argumentos) != 2:
        print("Uso: python scripts/testar_github.py <usuario/repo> <numero_pr> [--postar]")
        print("Exemplo: python scripts/testar_github.py fellype/teste-pr 1")
        sys.exit(1)

    pr = PullRequest(repositorio=argumentos[0], numero=int(argumentos[1]))

    # Importar aqui (e não no topo) adia o carregamento pesado do modelo de
    # embeddings do QdrantAdapter para depois da checagem de argumentos.
    from main import conhecimento, llm, repositorio  # noqa: E402

    modo = "PUBLICANDO no PR" if postar else "ENSAIO (sem postar)"
    print(f"Revisando {pr.repositorio} PR #{pr.numero} — {modo}\n")

    try:
        if postar:
            revisar_pull_request(pr, repositorio, conhecimento, llm)
            print("\nComentário publicado. Confira o PR no navegador.")
        else:
            comentario = analisar_pull_request(pr, repositorio, conhecimento, llm)
            print("--- Comentário que SERIA publicado ---\n")
            print(comentario)
    finally:
        # Libera o lock do banco embarcado (evita o traceback de shutdown).
        conhecimento.fechar()


if __name__ == "__main__":
    principal()
