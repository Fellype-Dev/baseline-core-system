
import re

_CABECALHO_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def linhas_alteradas(diff: str) -> set[int]:
    linhas: set[int] = set()
    linha_atual = 0
    dentro_de_hunk = False

    for linha in diff.splitlines():
        cabecalho = _CABECALHO_HUNK.match(linha)
        if cabecalho:
            linha_atual = int(cabecalho.group(1))
            dentro_de_hunk = True
            continue

        if not dentro_de_hunk:
            continue

        if linha.startswith("+"):
            linhas.add(linha_atual)
            linha_atual += 1
        elif linha.startswith("-"):
            pass
        elif linha.startswith(" "):
            linha_atual += 1

    return linhas
