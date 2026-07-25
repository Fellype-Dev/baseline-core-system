"""
Script de setup: indexa o documento SDD no banco vetorial.

Executado manualmente sempre que o SDD mudar. É uma operação de ciclo de vida
do adaptador — o núcleo nunca indexa nada, apenas consulta.

Uso:
    venv/Scripts/python.exe scripts/indexar_sdd.py [diretorio_do_sdd]

Padrão: sdd/
"""

import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from app.adapters.qdrant_adapter import QdrantAdapter  # noqa: E402
from app.services.sdd_service import carregar_sdd  # noqa: E402

SDD_PADRAO = os.path.join(RAIZ, "sdd")


def principal() -> None:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    com_exemplos = "--com-exemplos" in sys.argv[1:]
    caminho_sdd = argumentos[0] if argumentos else SDD_PADRAO

    print(f"Lendo SDD: {caminho_sdd}")
    regras = carregar_sdd(caminho_sdd)
    print(f"{len(regras)} regra(s) ativa(s):")
    for regra in regras:
        print(f"  [{regra.severidade:12}] {regra.identificador} - {regra.titulo}")

    embutido = "COM exemplos de codigo" if com_exemplos else "SO linguagem natural"
    print(f"\nGerando embeddings ({embutido}) e indexando no Qdrant...")
    adaptador = QdrantAdapter(indexar_exemplos=com_exemplos)
    try:
        adaptador.indexar_regras(regras)
        print("Indexacao concluida.")
    finally:
        # Sempre libera o lock do banco embarcado, mesmo se algo falhar.
        adaptador.fechar()


if __name__ == "__main__":
    principal()
