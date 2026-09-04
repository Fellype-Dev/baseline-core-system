
import asyncio
import json
import queue
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

from app.adapters.sse_adapter import ObservadorSSE

_PAGINA = Path(__file__).resolve().parent.parent.parent / "static" / "fluxo.html"


_INTERVALO_DE_CONSULTA = 0.25

_INTERVALO_DE_BATIMENTO = 10.0


def criar_router_eventos(observador: ObservadorSSE) -> APIRouter:
    router = APIRouter()

    @router.get("/fluxo")
    def pagina_do_fluxo() -> FileResponse:
        return FileResponse(_PAGINA, media_type="text/html")

    @router.get("/eventos")
    async def transmitir_eventos() -> StreamingResponse:
        fila = observador.inscrever()

        async def gerar():

            yield ": conectado\n\n"

            tempo_desde_o_batimento = 0.0
            try:
                while True:
                    try:
                        evento = fila.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(_INTERVALO_DE_CONSULTA)
                        tempo_desde_o_batimento += _INTERVALO_DE_CONSULTA
                        if tempo_desde_o_batimento >= _INTERVALO_DE_BATIMENTO:
                            tempo_desde_o_batimento = 0.0
                            yield ": batimento\n\n"
                        continue

                    tempo_desde_o_batimento = 0.0
                    corpo = json.dumps(
                        {"etapa": evento.etapa, "descricao": evento.descricao},
                        ensure_ascii=False,
                    )
                    yield f"data: {corpo}\n\n"
            finally:

                observador.cancelar(fila)

        return StreamingResponse(
            gerar(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",

                "X-Accel-Buffering": "no",
            },
        )

    return router
