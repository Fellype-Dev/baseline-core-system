"""Testes da interpretação e formatação do resultado da avaliação (feature D3)."""

import pytest

from app.core.models import Violacao
from app.services.resultado_service import (
    RespostaInvalidaError,
    formatar_comentario,
    interpretar_violacoes,
    montar_comentario_de_avaliacao,
)


# --- interpretar_violacoes --------------------------------------------------

def test_interpreta_json_puro():
    resposta = '{"violacoes": [{"regra": "SEG-001", "elemento": "carregar", "explicacao": "segredo no código"}]}'
    violacoes = interpretar_violacoes(resposta)
    assert violacoes == [
        Violacao(regra="SEG-001", explicacao="segredo no código", elemento="carregar")
    ]


def test_interpreta_lista_vazia():
    assert interpretar_violacoes('{"violacoes": []}') == []


def test_tolera_cerca_de_codigo_markdown():
    # O modelo embrulhou o JSON em ```json ... ```, apesar da instrução.
    resposta = '```json\n{"violacoes": []}\n```'
    assert interpretar_violacoes(resposta) == []


def test_tolera_texto_em_volta_do_json():
    resposta = 'Claro! Aqui está a análise:\n{"violacoes": []}\nEspero ter ajudado.'
    assert interpretar_violacoes(resposta) == []


def test_elemento_e_opcional():
    resposta = '{"violacoes": [{"regra": "ARQ-001", "explicacao": "núcleo importa adaptador"}]}'
    (violacao,) = interpretar_violacoes(resposta)
    assert violacao.regra == "ARQ-001"
    assert violacao.elemento == ""


def test_resposta_sem_json_levanta_erro():
    with pytest.raises(RespostaInvalidaError):
        interpretar_violacoes("desculpe, não consegui analisar o código")


def test_json_sem_chave_violacoes_levanta_erro():
    with pytest.raises(RespostaInvalidaError):
        interpretar_violacoes('{"resultado": "ok"}')


# --- formatar_comentario ----------------------------------------------------

def test_comentario_de_aprovacao_quando_sem_violacoes():
    comentario = formatar_comentario([])
    assert "✅" in comentario
    assert "Nenhuma violação" in comentario


def test_comentario_lista_cada_violacao_com_o_id_da_regra():
    violacoes = [
        Violacao(regra="SEG-001", explicacao="segredo hardcoded", elemento="carregar"),
        Violacao(regra="ARQ-001", explicacao="núcleo importa adaptador"),
    ]
    comentario = formatar_comentario(violacoes)
    assert "2 violações encontradas" in comentario
    assert "SEG-001" in comentario
    assert "segredo hardcoded" in comentario
    assert "`carregar`" in comentario  # elemento presente vira código inline
    assert "ARQ-001" in comentario


def test_singular_para_uma_violacao():
    comentario = formatar_comentario(
        [Violacao(regra="SEG-001", explicacao="x")]
    )
    assert "1 violação encontrada" in comentario


# --- montar_comentario_de_avaliacao (D3 completo) ---------------------------

def test_fim_a_fim_gera_comentario_de_violacao():
    resposta = '{"violacoes": [{"regra": "SEG-001", "elemento": "", "explicacao": "chave exposta"}]}'
    comentario = montar_comentario_de_avaliacao(resposta)
    assert "SEG-001" in comentario
    assert "chave exposta" in comentario


def test_resposta_irrecuperavel_vira_comentario_de_erro_honesto():
    comentario = montar_comentario_de_avaliacao("lorem ipsum sem json nenhum")
    assert "⚠️" in comentario
    assert "indisponível" in comentario
    # Não inventa violações: nenhum identificador de regra é citado.
    assert "SEG-" not in comentario
    assert "ARQ-" not in comentario
