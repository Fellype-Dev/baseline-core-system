
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


@dataclass(frozen=True)
class ElementoDeCodigo:

    tipo: str          
    nome: str          
    assinatura: str    
    linha_inicio: int  
    linha_fim: int     
