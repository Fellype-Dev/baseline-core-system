"""
Observador nulo: o comportamento padrão quando ninguém está acompanhando.

Aplicação do padrão Objeto Nulo. Sem ele, cada ponto do pipeline que anuncia
progresso precisaria perguntar antes se existe um observador, espalhando
verificações de `None` por toda a lógica de negócio.

Vive no núcleo, e não entre os adaptadores, porque não traduz nada para o mundo
externo: é a ausência de tradução, escrita de forma explícita.
"""

from app.core.models import EventoDeProgresso
from app.core.ports import ObservadorPort


class ObservadorNulo(ObservadorPort):
    """Descarta os avisos de progresso.

    É o padrão do pipeline: um sistema sem ninguém observando deve funcionar
    exatamente como um sistema observado.
    """

    def registrar(self, evento: EventoDeProgresso) -> None:
        return None
