"""
Serviço de leitura de diff (patch do git).

Responsabilidade única: dado o patch de um arquivo, descobrir QUAIS linhas do
arquivo novo foram adicionadas ou modificadas. Esse conjunto de linhas é depois
cruzado com o esqueleto da AST para isolar só os elementos que mudaram.

É lógica pura (só processa texto), testável sem GitHub.
"""

import re

# Cabeçalho de um "hunk": "@@ -12,3 +14,5 @@". O número que interessa é o
# início no arquivo NOVO (o grupo capturado após o '+').
_CABECALHO_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def linhas_alteradas(diff: str) -> set[int]:
    """Retorna os números das linhas adicionadas/modificadas no arquivo novo."""
    linhas: set[int] = set()
    linha_atual = 0
    dentro_de_hunk = False

    for linha in diff.splitlines():
        cabecalho = _CABECALHO_HUNK.match(linha)
        if cabecalho:
            # Um novo hunk começa: reposiciona o contador na linha indicada.
            linha_atual = int(cabecalho.group(1))
            dentro_de_hunk = True
            continue

        if not dentro_de_hunk:
            # Ainda não vimos nenhum hunk: ignora cabeçalhos de arquivo.
            continue

        if linha.startswith("+"):
            # Linha adicionada/modificada: existe no arquivo novo -> registra.
            linhas.add(linha_atual)
            linha_atual += 1
        elif linha.startswith("-"):
            # Linha removida: não existe no arquivo novo -> não avança.
            pass
        elif linha.startswith(" "):
            # Linha de contexto (inalterada): avança sem registrar.
            linha_atual += 1
        # Outras (ex.: "\ No newline at end of file") são ignoradas.

    return linhas
