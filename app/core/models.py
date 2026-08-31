
from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequest:

    repositorio: str  # ex.: "fellype/baseline-core-system"
    numero: int       # ex.: 42


@dataclass(frozen=True)
class ArquivoAlterado:

    caminho: str        # caminho no repositório, ex.: "app/core/pipeline.py"
    diff: str           # o trecho alterado (patch), no formato de diff do git
    conteudo: str = ""  # o arquivo completo na versão do PR (para a AST)


@dataclass(frozen=True)
class RegraArquitetural:


    identificador: str   # ex.: "ARQ-001"
    titulo: str          # enunciado curto da regra
    categoria: str       # ex.: "arquitetura" (declarada no sdd.config.yml)
    severidade: str      # ex.: "obrigatoria" (declarada no sdd.config.yml)
    regra: str           # o enunciado normativo completo
    motivacao: str       # por que a regra existe — alimenta o feedback didático

    linguagens: tuple[str, ...] = ()   # a quais linguagens se aplica
    aplica_se_a: tuple[str, ...] = ()  # padrões de caminho (glob) onde vale
    excecoes: tuple[str, ...] = ()     # padrões de caminho isentos
    status: str = "ativa"              # "ativa" ou "descontinuada"

    # Natureza da regra, e por consequência como ela é avaliada:
    #
    #   "arquivo"   (padrão) julga o conteúdo de cada arquivo alterado
    #   "estrutura"          julga a organização do repositório, uma vez por
    #                        Pull Request
    #
    # A distinção existe porque uma regra sobre onde o código deve residir não
    # tem sentido quando aplicada a um arquivo isolado: ela fala do conjunto.
    escopo: str = "arquivo"
    como_identificar: str = ""         # sinais estruturais observáveis
    exemplo_incorreto: str = ""        # trecho que viola a regra
    exemplo_correto: str = ""          # trecho equivalente em conformidade


@dataclass(frozen=True)
class EstruturaDoRepositorio:


    diretorios: tuple[str, ...]        # os que já existiam no branch padrão
    diretorios_novos: tuple[str, ...]  # os que esta submissão cria

    @property
    def vazia(self) -> bool:
        return not self.diretorios and not self.diretorios_novos


@dataclass(frozen=True)
class DocumentoSDD:
    regras: dict[str, str]          # nome do arquivo -> conteúdo
    configuracao: str | None = None  # conteúdo do sdd.config.yml, se houver

    @property
    def vazio(self) -> bool:
        return not self.regras

@dataclass(frozen=True)
class ConsultaDeRegras:


    texto: str          # descrição do que mudou, usada na busca semântica
    caminho: str        # arquivo alterado, ex.: "app/core/pipeline.py"
    linguagem: str      # ex.: "python"
    repositorio: str = ""  # de qual repositório são as regras a consultar


@dataclass(frozen=True)
class EventoDeProgresso:


    etapa: str       # identificador da etapa, ex.: "ast", "rag", "llm"
    descricao: str   # texto legível descrevendo o que aconteceu


@dataclass(frozen=True)
class Violacao:


    regra: str        # identificador da regra violada, ex.: "SEG-001"
    explicacao: str   # explicação didática do problema, vinda do modelo
    elemento: str = ""  # elemento afetado (função/classe), se informado


@dataclass(frozen=True)
class ElementoDeCodigo:

    tipo: str          # "funcao", "classe" ou "metodo"
    nome: str          # nome qualificado, ex.: "Calculadora.somar"
    assinatura: str    # a linha de declaração, ex.: "def somar(self, a, b)"
    linha_inicio: int  # primeira linha do elemento no arquivo
    linha_fim: int     # última linha do elemento no arquivo
