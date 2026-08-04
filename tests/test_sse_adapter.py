"""Testes do adaptador de transmissão de eventos (sem rede)."""

import queue

from app.adapters.sse_adapter import ObservadorSSE
from app.core.models import EventoDeProgresso
from app.core.ports import ObservadorPort


def evento(etapa="ast", descricao="teste"):
    return EventoDeProgresso(etapa=etapa, descricao=descricao)


def test_adaptador_satisfaz_o_contrato():
    assert isinstance(ObservadorSSE(), ObservadorPort)


def test_evento_chega_ao_assinante():
    observador = ObservadorSSE()
    fila = observador.inscrever()

    observador.registrar(evento("rag", "regras recuperadas"))

    recebido = fila.get_nowait()
    assert recebido.etapa == "rag"
    assert recebido.descricao == "regras recuperadas"


def test_todos_os_assinantes_recebem():
    """Vários navegadores podem acompanhar a mesma revisão simultaneamente."""
    observador = ObservadorSSE()
    primeira = observador.inscrever()
    segunda = observador.inscrever()

    observador.registrar(evento())

    assert primeira.get_nowait().etapa == "ast"
    assert segunda.get_nowait().etapa == "ast"


def test_cancelar_para_de_entregar():
    observador = ObservadorSSE()
    fila = observador.inscrever()
    observador.cancelar(fila)

    observador.registrar(evento())

    assert fila.empty()
    assert observador.total_de_assinantes == 0


def test_sem_assinantes_nao_quebra():
    """O pipeline anuncia mesmo quando ninguém abriu o fluxograma."""
    ObservadorSSE().registrar(evento())


def test_assinante_lento_descarta_os_eventos_antigos():
    """Uma fila cheia não pode crescer sem limite nem travar o pipeline."""
    observador = ObservadorSSE()
    fila = observador.inscrever()

    # Enche além do limite; o mais recente precisa sobreviver.
    for indice in range(150):
        observador.registrar(evento("ast", f"evento {indice}"))

    assert fila.qsize() <= 100
    descricoes = []
    while True:
        try:
            descricoes.append(fila.get_nowait().descricao)
        except queue.Empty:
            break
    assert descricoes[-1] == "evento 149"
