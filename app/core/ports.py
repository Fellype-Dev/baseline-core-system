

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
        """Publica a revisão do Pull Request.

        Há no máximo UMA revisão por Pull Request: publicar substitui a
        anterior. A revisão é um retrato do estado atual do código, não um
        histórico — o autor corrige, envia, e recebe a mesma revisão
        atualizada, em vez de uma pilha de comentários que o obriga a
        descobrir qual vale.

        Este invariante é do produto, e por isso está declarado aqui, no
        contrato. COMO cada plataforma realiza a substituição — editar um
        comentário, arquivar o anterior, versionar — é problema do adaptador.

        O método se chamava `publicar_comentario`, e a diferença não é
        cosmética: enquanto o contrato falava do mecanismo, ele não dizia
        quantas revisões um Pull Request tem, e o adaptador acabou decidindo
        sozinho. Foi a própria ferramenta que apontou isso, contra a ARQ-003.
        """
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
