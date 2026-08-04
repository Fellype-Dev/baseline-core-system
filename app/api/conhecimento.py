"""
Adaptador de ENTRADA: expõe o conteúdo do banco de conhecimento para inspeção.

O banco vetorial é embarcado e, por isso, invisível: não há interface para ver o
que está indexado nem para entender por que uma regra foi recuperada. Estas
rotas tornam essa etapa observável.

* `/conhecimento`         a página de inspeção;
* `/conhecimento/dados`   o inventário do que está indexado;
* `/conhecimento/buscar`  executa uma consulta semântica e devolve as pontuações.

A busca exposta aqui NÃO descarta candidatas: ela mostra a lista completa com a
similaridade de cada regra e se o filtro de aplicabilidade a aceitaria. É o que
permite distinguir uma falha de recuperação (a regra certa ficou mal
classificada) de uma falha de avaliação (a regra chegou ao modelo e ele não a
apontou) — distinção que, sem isto, seria invisível.
"""

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.adapters.qdrant_adapter import QdrantAdapter
from app.core.models import ConsultaDeRegras
from app.services.ast_service import identificar_linguagem

_PAGINA = (
    Path(__file__).resolve().parent.parent.parent / "static" / "conhecimento.html"
)


class Consulta(BaseModel):
    """Parâmetros de uma busca de inspeção."""

    texto: str
    caminho: str = ""
    linguagem: str = ""


def criar_router_conhecimento(conhecimento: QdrantAdapter) -> APIRouter:
    """Cria as rotas de inspeção do banco de conhecimento."""
    router = APIRouter(prefix="/conhecimento")

    @router.get("")
    def pagina() -> FileResponse:
        return FileResponse(_PAGINA, media_type="text/html")

    @router.get("/dados")
    def dados() -> dict:
        """Inventário do índice: estatísticas e as regras armazenadas."""
        return {
            "colecao": conhecimento.descrever_colecao(),
            "regras": [asdict(regra) for regra in conhecimento.listar_regras()],
        }

    @router.post("/buscar")
    def buscar(consulta: Consulta) -> dict:
        """Executa a busca semântica e devolve o ranking com as pontuações."""
        # O contexto de arquivo é opcional: sem ele, mostramos apenas o ranking
        # semântico; com ele, também se vê o que o filtro de aplicabilidade faria.
        #
        # A linguagem é deduzida do caminho quando não informada, como acontece
        # no pipeline. Sem isso, informar apenas o caminho descartaria todas as
        # regras (nenhuma casaria com uma linguagem vazia) e a tela sugeriria um
        # comportamento que não é o real.
        contexto = None
        if consulta.caminho or consulta.linguagem:
            linguagem = consulta.linguagem or identificar_linguagem(consulta.caminho)
            contexto = ConsultaDeRegras(
                texto=consulta.texto,
                caminho=consulta.caminho,
                linguagem=linguagem or "",
            )

        resultados = conhecimento.buscar_com_pontuacao(consulta.texto, contexto)
        return {
            "com_filtro": contexto is not None,
            "resultados": [
                {
                    "identificador": regra.identificador,
                    "titulo": regra.titulo,
                    "categoria": regra.categoria,
                    "severidade": regra.severidade,
                    "pontuacao": round(pontuacao, 4),
                    "aplicavel": aplicavel,
                }
                for regra, pontuacao, aplicavel in resultados
            ],
        }

    return router
