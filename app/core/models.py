"""
Modelos de domínio: o vocabulário do núcleo.

Estas são as estruturas de dados com que o núcleo raciocina. Elas descrevem o
*problema* (revisar um Pull Request), e não a *tecnologia* (GitHub, Qdrant,
Gemini). Nenhum detalhe de infraestrutura aparece aqui — de propósito.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequest:
    """Identifica um Pull Request a ser revisado.

    Guarda apenas o necessário para localizá-lo. É `frozen` (imutável) porque a
    identidade de um PR não muda durante a revisão.
    """

    repositorio: str  # ex.: "fellype/baseline-core-system"
    numero: int       # ex.: 42


@dataclass(frozen=True)
class ArquivoAlterado:
    """Um arquivo modificado dentro de um Pull Request."""

    caminho: str  # caminho no repositório, ex.: "app/core/pipeline.py"
    diff: str     # o trecho alterado (patch), no formato de diff do git


@dataclass(frozen=True)
class RegraArquitetural:
    """Uma regra do documento SDD, recuperada como relevante para um trecho de código."""

    identificador: str  # de onde a regra veio no SDD (ex.: "secao-3.2")
    conteudo: str       # o texto da regra, em linguagem natural
