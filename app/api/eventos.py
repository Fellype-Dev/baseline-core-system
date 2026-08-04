"""
Adaptador de ENTRADA: serve o fluxograma e transmite os eventos do pipeline.

Duas rotas complementares:

* `/fluxo`    entrega a página do fluxograma;
* `/eventos`  mantém a conexão aberta e envia cada etapa conforme ela acontece.

A página é servida pela própria aplicação de propósito. Hospedá-la em outro
lugar exigiria liberar requisições entre origens diferentes, e a página já fica
publicamente acessível pelo mesmo endereço do webhook — não há o que ganhar em
separá-la.
"""

import asyncio
import json
import queue
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, StreamingResponse

from app.adapters.sse_adapter import ObservadorSSE

_PAGINA = Path(__file__).resolve().parent.parent.parent / "static" / "fluxo.html"

# De quanto em quanto tempo a fila é consultada quando não há eventos. Como a
# espera bloqueante da fila travaria o laço assíncrono, a consulta é feita sem
# bloquear, intercalada com uma pausa curta.
_INTERVALO_DE_CONSULTA = 0.25

# Sem tráfego, servidores intermediários encerram conexões ociosas. Um
# comentário periódico mantém o canal vivo sem poluir a página. O valor é
# conservador porque o túnel derruba conexões silenciosas.
_INTERVALO_DE_BATIMENTO = 10.0


def criar_router_eventos(observador: ObservadorSSE) -> APIRouter:
    """Cria as rotas de acompanhamento, ligadas ao observador informado."""
    router = APIRouter()

    @router.get("/fluxo")
    def pagina_do_fluxo() -> FileResponse:
        """Entrega o fluxograma que acompanha a revisão em tempo real."""
        return FileResponse(_PAGINA, media_type="text/html")

    @router.get("/eventos")
    async def transmitir_eventos() -> StreamingResponse:
        """Mantém a conexão aberta, enviando cada etapa do pipeline."""
        fila = observador.inscrever()

        async def gerar():
            # Primeiro byte imediato, antes de qualquer espera. Intermediários
            # (o túnel, no caso) só entregam a resposta ao navegador depois que
            # algo chega: sem isto, a conexão fica pendurada até o primeiro
            # batimento e a página parece nunca conectar.
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
                # Vale tanto para a desconexão do navegador quanto para o
                # encerramento do servidor: sem isto, filas órfãs se acumulariam.
                observador.cancelar(fila)

        return StreamingResponse(
            gerar(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                # Evita que intermediários acumulem a resposta antes de entregá-la,
                # o que anularia o efeito de tempo real.
                "X-Accel-Buffering": "no",
            },
        )

    return router
