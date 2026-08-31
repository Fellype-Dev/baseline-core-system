"""Testes dos contratos (portas): eles obrigam os adaptadores a se conformarem."""

import pytest

from app.core.models import DocumentoSDD, EstruturaDoRepositorio
from app.core.ports import RepositorioPort


def test_porta_abstrata_nao_pode_ser_instanciada():
    # Uma porta é um contrato, não uma implementação.
    with pytest.raises(TypeError):
        RepositorioPort()


def test_implementacao_completa_satisfaz_o_contrato():
    class RepositorioFake(RepositorioPort):
        def obter_arquivos_alterados(self, pr):
            return []

        def publicar_comentario(self, pr, texto):
            pass

        def obter_documento_sdd(self, pr):
            return DocumentoSDD(regras={})

        def obter_estrutura(self, pr):
            return EstruturaDoRepositorio(diretorios=(), diretorios_novos=())

    fake = RepositorioFake()
    assert isinstance(fake, RepositorioPort)


def test_implementacao_incompleta_e_recusada():
    class RepositorioIncompleto(RepositorioPort):
        def obter_arquivos_alterados(self, pr):
            return []

        # Falta publicar_comentario de propósito.

    # O contrato tem "dentes": sem todos os métodos, o Python recusa criar.
    with pytest.raises(TypeError):
        RepositorioIncompleto()
