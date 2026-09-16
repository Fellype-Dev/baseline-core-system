
import re
from functools import lru_cache

from app.core.models import ConsultaDeRegras, RegraArquitetural


def regra_se_aplica(regra: RegraArquitetural, consulta: ConsultaDeRegras) -> bool:

    if regra.linguagens and consulta.linguagem not in regra.linguagens:
        return False

    if any(_corresponde(consulta.caminho, p) for p in regra.excecoes):
        return False

    if not regra.aplica_se_a:
        return True

    return any(_corresponde(consulta.caminho, p) for p in regra.aplica_se_a)


def _corresponde(caminho: str, padrao: str) -> bool:

    caminho_normalizado = caminho.replace("\\", "/")
    return _compilar(padrao).match(caminho_normalizado) is not None


@lru_cache(maxsize=256)
def _compilar(padrao: str) -> re.Pattern:

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
