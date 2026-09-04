

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


    from main import conhecimento, llm, repositorio 

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
        conhecimento.fechar()


if __name__ == "__main__":
    principal()
