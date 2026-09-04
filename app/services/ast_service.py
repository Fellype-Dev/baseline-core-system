
import ast
import os

from app.core.models import ElementoDeCodigo

_LINGUAGENS_POR_EXTENSAO = {".py": "python"}


def identificar_linguagem(caminho: str) -> str | None:

    _, extensao = os.path.splitext(caminho)
    return _LINGUAGENS_POR_EXTENSAO.get(extensao.lower())


class _ColetorDeElementos(ast.NodeVisitor):


    def __init__(self) -> None:
        self.elementos: list[ElementoDeCodigo] = []

        self._classe_atual: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.elementos.append(
            ElementoDeCodigo(
                tipo="classe",
                nome=node.name,
                assinatura=f"class {node.name}",
                linha_inicio=node.lineno,
                linha_fim=node.end_lineno or node.lineno,
            )
        )
        classe_anterior = self._classe_atual
        self._classe_atual = node.name
        self.generic_visit(node)
        self._classe_atual = classe_anterior

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._registrar_funcao(node, prefixo="def")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._registrar_funcao(node, prefixo="async def")

    def _registrar_funcao(self, node, prefixo: str) -> None:
        dentro_de_classe = self._classe_atual is not None
        tipo = "metodo" if dentro_de_classe else "funcao"
        nome = f"{self._classe_atual}.{node.name}" if dentro_de_classe else node.name

        assinatura = f"{prefixo} {node.name}({ast.unparse(node.args)})"

        self.elementos.append(
            ElementoDeCodigo(
                tipo=tipo,
                nome=nome,
                assinatura=assinatura,
                linha_inicio=node.lineno,
                linha_fim=node.end_lineno or node.lineno,
            )
        )


def extrair_esqueleto(codigo: str) -> list[ElementoDeCodigo]:

    arvore = ast.parse(codigo)
    coletor = _ColetorDeElementos()
    coletor.visit(arvore)
    return coletor.elementos


def elementos_alterados(
    codigo: str, linhas: set[int]
) -> list[ElementoDeCodigo]:

    esqueleto = extrair_esqueleto(codigo)
    return [
        elemento
        for elemento in esqueleto
        if any(
            elemento.linha_inicio <= n <= elemento.linha_fim for n in linhas
        )
    ]
