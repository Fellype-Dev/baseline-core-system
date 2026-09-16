
from app.core.models import EventoDeProgresso
from app.core.ports import ObservadorPort


class ObservadorNulo(ObservadorPort):

    def registrar(self, evento: EventoDeProgresso) -> None:
        return None
