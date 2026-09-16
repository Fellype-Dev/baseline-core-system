

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


    @abstractmethod
    def obter_arquivos_alterados(self, pr: PullRequest) -> list[ArquivoAlterado]:
        ...

    @abstractmethod
    def publicar_revisao(self, pr: PullRequest, texto: str) -> None:

        ...

    @abstractmethod
    def obter_estrutura(self, pr: PullRequest) -> EstruturaDoRepositorio:

        ...

    @abstractmethod
    def obter_documento_sdd(self, pr: PullRequest) -> DocumentoSDD:

        ...


class ConhecimentoPort(ABC):


    @abstractmethod
    def sincronizar_regras(
        self, repositorio: str, regras: list[RegraArquitetural]
    ) -> None:

        ...

    @abstractmethod
    def buscar_regras_relevantes(
        self, consulta: ConsultaDeRegras
    ) -> list[RegraArquitetural]:

        ...


class ObservadorPort(ABC):


    @abstractmethod
    def registrar(self, evento: EventoDeProgresso) -> None:
        ...


class LLMPort(ABC):


    @abstractmethod
    def avaliar(self, prompt: str) -> str:
        ...
