"""
Portas: os contratos entre o núcleo e o mundo externo.

Cada porta é uma interface (classe abstrata) que o núcleo *declara* segundo a
sua própria necessidade. Os adaptadores (GitHub, Qdrant, LLM) é que se curvam a
estes contratos — nunca o contrário.

Por isso este arquivo NÃO importa nada de `app/adapters`: a dependência aponta
sempre para dentro do núcleo. Se um dia aparecer um `import` de adaptador aqui,
a arquitetura hexagonal foi quebrada.
"""

from abc import ABC, abstractmethod

from app.core.models import (
    ArquivoAlterado,
    ConsultaDeRegras,
    PullRequest,
    RegraArquitetural,
)


class RepositorioPort(ABC):
    """Contrato para conversar com o repositório de código (hoje, o GitHub).

    O núcleo precisa de duas coisas do repositório: ler o que mudou num PR e
    devolver o feedback como comentário. A palavra "GitHub" não aparece — o
    núcleo fala de "repositório", não de uma plataforma específica.
    """

    @abstractmethod
    def obter_arquivos_alterados(self, pr: PullRequest) -> list[ArquivoAlterado]:
        """Retorna os arquivos modificados no Pull Request informado."""
        ...

    @abstractmethod
    def publicar_comentario(self, pr: PullRequest, texto: str) -> None:
        """Publica um comentário de feedback no Pull Request."""
        ...


class ConhecimentoPort(ABC):
    """Contrato para recuperar as regras arquiteturais relevantes.

    O núcleo não pede "faça uma busca vetorial"; ele pede "me dê as regras que
    importam para este código". Como isso é resolvido (embeddings, Qdrant) é
    problema do adaptador, invisível aqui.
    """

    @abstractmethod
    def buscar_regras_relevantes(
        self, consulta: ConsultaDeRegras
    ) -> list[RegraArquitetural]:
        """Retorna as regras APLICÁVEIS ao arquivo e relevantes para o código.

        "Aplicável" faz parte do contrato: cabe ao adaptador descartar regras de
        outra linguagem ou fora do escopo de caminho declarado no SDD, para que
        o núcleo nunca receba uma regra que não deveria ser cobrada ali.
        """
        ...


class LLMPort(ABC):
    """Contrato para avaliar um texto com um modelo de linguagem.

    Proposital: recebe um prompt (texto) e devolve texto. QUEM constrói o prompt
    (combinando código + regras) é o núcleo — essa é a inteligência do produto e
    fica testável no núcleo. O adaptador só sabe "mandar texto, receber texto",
    seja ele o Gemini hoje ou um modelo open source amanhã.
    """

    @abstractmethod
    def avaliar(self, prompt: str) -> str:
        """Envia o prompt ao modelo e retorna a resposta em texto."""
        ...
