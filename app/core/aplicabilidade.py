"""
Aplicabilidade: decide se uma regra do SDD vale para um determinado arquivo.

Descartar regras inaplicáveis ANTES de enviá-las ao modelo de linguagem é a
principal defesa contra falsos positivos. Uma regra sobre adaptadores não deve
ser cobrada em um arquivo do núcleo, nem uma regra de Python em um markdown.

Lógica pura do núcleo: sem rede, sem banco, testável isoladamente.
"""

import re
from functools import lru_cache

from app.core.models import ConsultaDeRegras, RegraArquitetural


def regra_se_aplica(regra: RegraArquitetural, consulta: ConsultaDeRegras) -> bool:
    """Diz se a regra vale para o arquivo descrito na consulta.

    A ordem das verificações importa: a exceção tem precedência sobre o escopo,
    para que um caminho isento seja descartado mesmo estando dentro da área
    coberta pela regra.
    """
    # 1. Linguagem: lista vazia significa "qualquer linguagem".
    if regra.linguagens and consulta.linguagem not in regra.linguagens:
        return False

    # 2. Exceções explícitas vencem o escopo.
    if any(_corresponde(consulta.caminho, p) for p in regra.excecoes):
        return False

    # 3. Escopo: sem padrões declarados, a regra vale para todo o repositório.
    if not regra.aplica_se_a:
        return True

    return any(_corresponde(consulta.caminho, p) for p in regra.aplica_se_a)


def _corresponde(caminho: str, padrao: str) -> bool:
    """Casa um caminho contra um padrão glob no estilo gitignore."""
    # Normaliza separadores do Windows para que os padrões sejam sempre "a/b".
    caminho_normalizado = caminho.replace("\\", "/")
    return _compilar(padrao).match(caminho_normalizado) is not None


@lru_cache(maxsize=256)
def _compilar(padrao: str) -> re.Pattern:
    """Traduz um padrão glob para expressão regular.

    A biblioteca `fnmatch` não serve aqui porque seu `*` também casa com "/",
    o que faria "app/core/*" casar com subdiretórios indevidamente. Esta
    tradução respeita a fronteira de diretórios:

        **/   -> zero ou mais diretórios
        **    -> qualquer coisa, inclusive "/"
        *     -> qualquer coisa, exceto "/"
        ?     -> um caractere, exceto "/"
    """
    partes: list[str] = []
    i = 0
    while i < len(padrao):
        if padrao.startswith("**/", i):
            partes.append(r"(?:[^/]+/)*")
            i += 3
        elif padrao.startswith("**", i):
            partes.append(r".*")
            i += 2
        elif padrao[i] == "*":
            partes.append(r"[^/]*")
            i += 1
        elif padrao[i] == "?":
            partes.append(r"[^/]")
            i += 1
        else:
            partes.append(re.escape(padrao[i]))
            i += 1

    return re.compile("^" + "".join(partes) + r"\Z")
