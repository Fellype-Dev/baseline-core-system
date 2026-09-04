

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

    texto: str
    caminho: str = ""
    linguagem: str = ""


def criar_router_conhecimento(conhecimento: QdrantAdapter) -> APIRouter:
    router = APIRouter(prefix="/conhecimento")

    @router.get("")
    def pagina() -> FileResponse:
        return FileResponse(_PAGINA, media_type="text/html")

    @router.get("/dados")
    def dados() -> dict:
        return {
            "colecao": conhecimento.descrever_colecao(),
            "regras": [asdict(regra) for regra in conhecimento.listar_regras()],
        }

    @router.post("/buscar")
    def buscar(consulta: Consulta) -> dict:

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
