"""
Serviço de sanitização estrutural via AST (Árvore Sintática Abstrata).

Transforma código-fonte Python no seu "esqueleto lógico": a lista de funções,
classes e métodos, sem o ruído de formatação, comentários e corpo. É lógica
PURA — não faz rede nem I/O — então vive no lado do núcleo e é testável com
strings de exemplo, sem depender do GitHub.

Usa a biblioteca `ast`, nativa do Python (Python Software Foundation).
"""

import ast
import os

from app.core.models import ElementoDeCodigo

# Linguagens que o sistema sabe analisar via AST. Por ora, só Python (a lib
# `ast` é nativa do Python). Outras linguagens exigiriam tree-sitter — decisão
# de escopo registrada no TCC.
_LINGUAGENS_POR_EXTENSAO = {".py": "python"}


def identificar_linguagem(caminho: str) -> str | None:
    """Descobre a linguagem de um arquivo pela extensão.

    Retorna o nome da linguagem (ex.: "python") ou None se não for suportada.
    Funciona como um portão: só arquivos reconhecidos seguem para a análise AST.
    """
    _, extensao = os.path.splitext(caminho)
    return _LINGUAGENS_POR_EXTENSAO.get(extensao.lower())


class _ColetorDeElementos(ast.NodeVisitor):
    """Percorre a árvore sintática coletando funções, classes e métodos.

    Um NodeVisitor chama automaticamente o método `visit_<TipoDoNo>` para cada
    nó correspondente que encontra ao descer pela árvore. Aqui reagimos a
    definições de classe e de função.
    """

    def __init__(self) -> None:
        self.elementos: list[ElementoDeCodigo] = []
        # Guarda o nome da classe em que estamos, para saber se uma função é,
        # na verdade, um método (função declarada dentro de uma classe).
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
        # Entra na classe para coletar seus métodos, e depois restaura o contexto.
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

        # ast.unparse reconstrói os argumentos (com anotações e defaults) em texto.
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
        # Não descemos para dentro do corpo da função: funções aninhadas são um
        # caso raro e ficam fora do escopo desta versão (simplificação consciente).


def extrair_esqueleto(codigo: str) -> list[ElementoDeCodigo]:
    """Extrai o esqueleto lógico (funções, classes e métodos) de um código Python.

    Levanta SyntaxError se o código não for Python válido — cabe a quem chama
    decidir o que fazer (ex.: cair para o diff bruto). Esse tratamento entra no
    Conjunto E (resiliência).
    """
    arvore = ast.parse(codigo)
    coletor = _ColetorDeElementos()
    coletor.visit(arvore)
    return coletor.elementos


def elementos_alterados(
    codigo: str, linhas: set[int]
) -> list[ElementoDeCodigo]:
    """Isola, do esqueleto do arquivo, apenas os elementos que foram alterados.

    Um elemento é considerado alterado se pelo menos uma das linhas modificadas
    cai dentro do seu intervalo (linha_inicio..linha_fim).

    Observação: como um método está contido em sua classe, alterar um método faz
    tanto o método quanto a classe que o contém aparecerem no resultado. Isso é
    proposital — o LLM ganha o contexto de "onde" a mudança aconteceu.
    """
    esqueleto = extrair_esqueleto(codigo)
    return [
        elemento
        for elemento in esqueleto
        if any(
            elemento.linha_inicio <= n <= elemento.linha_fim for n in linhas
        )
    ]
