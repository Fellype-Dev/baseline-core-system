"""
Adaptador de transmissão: implementa a ObservadorPort publicando os eventos do
pipeline para navegadores conectados.

Usa Server-Sent Events (SSE), e não WebSocket, por corresponder exatamente ao
formato do problema: o fluxo é de mão única (o servidor conta o que aconteceu, o
navegador só escuta), o protocolo é HTTP comum — atravessando o túnel sem
configuração adicional — e o navegador reconecta sozinho ao perder o sinal.

Detalhe de concorrência que justifica o desenho: a revisão roda em uma thread
de segundo plano (BackgroundTasks do FastAPI), enquanto a transmissão acontece
no laço assíncrono. A entrega entre os dois é feita por `queue.Queue`, que é
segura entre threads; cada navegador conectado tem a sua, para que um assinante
lento não atrase os demais.
"""

import queue
import threading

from app.core.models import EventoDeProgresso
from app.core.ports import ObservadorPort

# Se um navegador parar de consumir, sua fila não pode crescer sem limite e
# consumir a memória do servidor. Ao encher, os eventos mais antigos são
# descartados: para acompanhar um fluxo ao vivo, o evento recente é o que
# importa.
_LIMITE_POR_ASSINANTE = 100


class ObservadorSSE(ObservadorPort):
    """Distribui os eventos do pipeline para todos os navegadores conectados."""

    def __init__(self) -> None:
        self._assinantes: list[queue.Queue] = []
        self._trava = threading.Lock()

    # -- Lado do núcleo: recebe os avisos -------------------------------------

    def registrar(self, evento: EventoDeProgresso) -> None:
        """Entrega o evento a cada navegador conectado."""
        with self._trava:
            assinantes = list(self._assinantes)

        for fila in assinantes:
            try:
                fila.put_nowait(evento)
            except queue.Full:
                # Assinante lento: descarta o evento mais antigo e insiste, para
                # que ele continue recebendo o estado mais recente do fluxo.
                try:
                    fila.get_nowait()
                    fila.put_nowait(evento)
                except (queue.Empty, queue.Full):
                    pass

    # -- Lado da transmissão: gerencia os assinantes --------------------------

    def inscrever(self) -> queue.Queue:
        """Registra um novo navegador e devolve a fila por onde ele será servido."""
        fila: queue.Queue = queue.Queue(maxsize=_LIMITE_POR_ASSINANTE)
        with self._trava:
            self._assinantes.append(fila)
        return fila

    def cancelar(self, fila: queue.Queue) -> None:
        """Remove um navegador que se desconectou."""
        with self._trava:
            if fila in self._assinantes:
                self._assinantes.remove(fila)

    @property
    def total_de_assinantes(self) -> int:
        with self._trava:
            return len(self._assinantes)
