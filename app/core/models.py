
from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequest:

    repositorio: str 
    numero: int       


@dataclass(frozen=True)
class ArquivoAlterado:

    caminho: str        
    diff: str           
    conteudo: str = "" 


@dataclass(frozen=True)
class RegraArquitetural:


    identificador: str   
    titulo: str         
    categoria: str       
    severidade: str      
    regra: str           
    motivacao: str       

    linguagens: tuple[str, ...] = ()   
    aplica_se_a: tuple[str, ...] = ()  
    excecoes: tuple[str, ...] = ()     
    status: str = "ativa"              

    escopo: str = "arquivo"
    como_identificar: str = ""         
    exemplo_incorreto: str = ""        
    exemplo_correto: str = ""          


@dataclass(frozen=True)
class EstruturaDoRepositorio:


    diretorios: tuple[str, ...]        
    diretorios_novos: tuple[str, ...]  

    @property
    def vazia(self) -> bool:
        return not self.diretorios and not self.diretorios_novos


@dataclass(frozen=True)
class DocumentoSDD:
    regras: dict[str, str]          
    configuracao: str | None = None  

    @property
    def vazio(self) -> bool:
        return not self.regras

@dataclass(frozen=True)
class ConsultaDeRegras:


    texto: str          
    caminho: str       
    linguagem: str      
    repositorio: str = ""  


@dataclass(frozen=True)
class EventoDeProgresso:


    etapa: str       
    descricao: str   


@dataclass(frozen=True)
class Violacao:


    regra: str
    explicacao: str
    elemento: str = ""

    # A linha que sustenta o apontamento. O modelo informa apenas o NÚMERO; o
    # texto é buscado no código pelo próprio sistema. Assim o trecho exibido
    # vem do repositório, e não da saída do modelo — e um número não quebra o
    # JSON da resposta, como quebrava a linha de código copiada literalmente.
    linha: int = 0
    evidencia: str = ""


@dataclass(frozen=True)
class ResultadoDoArquivo:
    """O que a revisão apurou sobre um arquivo.

    Existe para que o núcleo raciocine sobre O QUE aconteceu, e não sobre o
    texto que descreve o que aconteceu. Antes, saber se um arquivo tinha achado
    exigia procurar um emoji no markdown já montado — o que impedia, por
    exemplo, resumir um Pull Request de dezoito arquivos sem reprocessar texto.
    """

    caminho: str
    violacoes: tuple[Violacao, ...] = ()

    # Aviso de sintaxe: o arquivo não pôde ser interpretado, mas a revisão
    # seguiu pelo diff.
    aviso: str = ""

    # O modelo não pôde ser consultado, ou respondeu algo ilegível. Diferente
    # de "nenhuma violação": aqui não houve avaliação, e um humano precisa
    # olhar.
    indisponivel: bool = False

    @property
    def tem_achado(self) -> bool:
        return bool(self.violacoes) or bool(self.aviso) or self.indisponivel


@dataclass(frozen=True)
class ElementoDeCodigo:

    tipo: str          
    nome: str          
    assinatura: str    
    linha_inicio: int  
    linha_fim: int     
