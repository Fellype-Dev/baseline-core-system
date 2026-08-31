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
    DocumentoSDD,
    EstruturaDoRepositorio,
    EventoDeProgresso,
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

    @abstractmethod
    def obter_estrutura(self, pr: PullRequest) -> EstruturaDoRepositorio:
        """Descreve a organização de diretórios e o que o Pull Request cria.

        Regras arquiteturais sobre onde o código deve residir não podem ser
        verificadas olhando um arquivo por vez: precisam da visão do conjunto.
        """
        ...

    @abstractmethod
    def obter_documento_sdd(self, pr: PullRequest) -> DocumentoSDD:
        """Lê o documento de especificação versionado no repositório revisado.

        As regras arquiteturais pertencem à organização, não à ferramenta: cada
        repositório declara as suas, versionadas junto ao código. É isso que
        torna a alteração de uma regra um Pull Request auditável como outro
        qualquer, e o que permite que organizações distintas sejam avaliadas por
        critérios distintos pela mesma ferramenta.
        """
        ...


class ConhecimentoPort(ABC):
    """Contrato para recuperar as regras arquiteturais relevantes.

    O núcleo não pede "faça uma busca vetorial"; ele pede "me dê as regras que
    importam para este código". Como isso é resolvido (embeddings, Qdrant) é
    problema do adaptador, invisível aqui.
    """

    @abstractmethod
    def sincronizar_regras(
        self, repositorio: str, regras: list[RegraArquitetural]
    ) -> None:
        """Garante que a base reflita as regras vigentes daquele repositório.

        Como cada repositório traz o seu próprio documento de especificação, a
        base precisa ser atualizada antes de qualquer consulta. Cabe ao
        adaptador evitar trabalho desnecessário quando as regras não mudaram —
        recalcular representações vetoriais a cada Pull Request seria custoso e
        inútil.
        """
        ...

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


class ObservadorPort(ABC):
    """Contrato para acompanhar o progresso de uma revisão.

    O núcleo anuncia cada etapa concluída sem saber quem escuta nem para quê.
    Um adaptador escreve em log, outro transmite para um navegador, e nos testes
    um dublê apenas registra os avisos recebidos.

    Esta porta é opcional por natureza: o pipeline funciona igual quando não há
    ninguém observando (ver `ObservadorNulo`). Observabilidade não pode ser
    requisito de funcionamento.
    """

    @abstractmethod
    def registrar(self, evento: EventoDeProgresso) -> None:
        """Recebe o aviso de que uma etapa do pipeline aconteceu."""
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
