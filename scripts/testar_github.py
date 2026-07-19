"""
Teste manual (Nível 1): exercita o GitHubAdapter contra um PR REAL.

Não usa webhook nem servidor. Chama diretamente a MESMA função que o webhook
chamaria (main.revisar_pull_request), provando a ida-e-volta com o GitHub:
buscar os arquivos do PR e postar o comentário de teste.

Uso:
    venv/Scripts/python.exe scripts/testar_github.py <usuario/repo> <numero_pr>

Exemplo:
    venv/Scripts/python.exe scripts/testar_github.py fellype/teste-pr 1
"""

import os
import sys

# Garante que a raiz do projeto esteja no caminho de imports, mesmo executando
# este arquivo de dentro da pasta scripts/.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from app.core.models import PullRequest  # noqa: E402
from main import revisar_pull_request     # noqa: E402


def principal() -> None:
    if len(sys.argv) != 3:
        print("Uso: python scripts/testar_github.py <usuario/repo> <numero_pr>")
        print("Exemplo: python scripts/testar_github.py fellype/teste-pr 1")
        sys.exit(1)

    repositorio = sys.argv[1]
    numero_pr = int(sys.argv[2])

    pr = PullRequest(repositorio=repositorio, numero=numero_pr)
    print(f"Testando contra {pr.repositorio}, PR #{pr.numero}\n")

    revisar_pull_request(pr)

    print("\nPronto. Confira o comentário no PR pelo navegador.")


if __name__ == "__main__":
    principal()
