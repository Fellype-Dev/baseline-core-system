
import queue
import threading

from app.core.models import EventoDeProgresso
from app.core.ports import ObservadorPort

_LIMITE_POR_ASSINANTE = 100


class ObservadorSSE(ObservadorPort):

    def __init__(self) -> None:
        self._assinantes: list[queue.Queue] = []
        self._trava = threading.Lock()


    def registrar(self, evento: EventoDeProgresso) -> None:
        with self._trava:
            assinantes = list(self._assinantes)

        for fila in assinantes:
            try:
                fila.put_nowait(evento)
            except queue.Full:

                try:
                    fila.get_nowait()
                    fila.put_nowait(evento)
                except (queue.Empty, queue.Full):
                    pass


    def inscrever(self) -> queue.Queue:
        fila: queue.Queue = queue.Queue(maxsize=_LIMITE_POR_ASSINANTE)
        with self._trava:
            self._assinantes.append(fila)
        return fila

    def cancelar(self, fila: queue.Queue) -> None:
        with self._trava:
            if fila in self._assinantes:
                self._assinantes.remove(fila)

    @property
    def total_de_assinantes(self) -> int:
        with self._trava:
            return len(self._assinantes)
