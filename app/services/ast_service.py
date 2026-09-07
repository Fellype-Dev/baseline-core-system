
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
                linha_inicio=_primeira_linha(node),
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
                linha_inicio=_primeira_linha(node),
                linha_fim=node.end_lineno or node.lineno,
            )
        )


def _primeira_linha(node) -> int:
    """Onde o elemento realmente começa, contando os decoradores.

    A AST aponta `lineno` para a palavra `def`/`class`, deixando os decoradores
    de fora. Mas o decorador faz parte do elemento e costuma ser justamente o
    que interessa a uma revisão arquitetural — `@router.post` diz que a função
    é um ponto de entrada HTTP. Sem ele, o elemento chega incompleto a quem
    julga.
    """
    decoradores = getattr(node, "decorator_list", [])
    if not decoradores:
        return node.lineno
    return min(node.lineno, *(d.lineno for d in decoradores))


def extrair_esqueleto(codigo: str) -> list[ElementoDeCodigo]:

    arvore = ast.parse(codigo)
    coletor = _ColetorDeElementos()
    coletor.visit(arvore)
    return coletor.elementos


def linhas_de_texto_literal(codigo: str) -> set[int]:
    """Linhas que são continuação de um literal de texto de várias linhas.

    Um arquivo guarda código como DADO com frequência — fixtures de teste,
    exemplos em docstring, gabaritos. Julgar essas linhas como se fossem
    código do arquivo produz apontamento sobre algo que não executa: foi
    assim que um `pass` dentro de uma string de teste virou "exceção
    silenciada".

    A PRIMEIRA linha do literal fica de fora de propósito. É nela que mora um
    segredo escrito no código (`API_KEY = "sk-..."`), e essa é uma violação
    real que precisa continuar sendo apontada. Só as linhas de continuação
    são, necessariamente, conteúdo e não instrução.
    """
    try:
        arvore = ast.parse(codigo)
    except SyntaxError:
        return set()

    linhas: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            fim = no.end_lineno or no.lineno
            linhas.update(range(no.lineno + 1, fim + 1))
    return linhas


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
