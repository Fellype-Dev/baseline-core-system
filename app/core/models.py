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
    """Uma regra do documento SDD da organização.

    Cada campo existe para entregar uma capacidade concreta ao sistema:
    o identificador dá rastreabilidade ao feedback ("viola ARQ-001"); a
    motivação torna o comentário didático; `linguagens` e `aplica_se_a`
    permitem descartar regras inaplicáveis, reduzindo falsos positivos; e os
    exemplos servem de referência para o modelo de linguagem.

    Coleções são tuplas (e não listas) para preservar a imutabilidade.
    """

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
    como_identificar: str = ""         # sinais estruturais observáveis
    exemplo_incorreto: str = ""        # trecho que viola a regra
    exemplo_correto: str = ""          # trecho equivalente em conformidade


@dataclass(frozen=True)
class ConsultaDeRegras:
    """O contexto de uma busca por regras no SDD.

    Agrupar os dados num objeto, em vez de passar parâmetros soltos, permite
    acrescentar contexto no futuro (autor do PR, categoria desejada) sem
    alterar a assinatura da porta e sem quebrar os adaptadores existentes.
    """

    texto: str       # descrição do que mudou, usada na busca semântica
    caminho: str     # arquivo alterado, ex.: "app/core/pipeline.py"
    linguagem: str   # ex.: "python"


@dataclass(frozen=True)
class Violacao:
    """Uma violação de regra apontada pelo modelo na avaliação de um PR.

    É o resultado do domínio depois de interpretar a resposta do LLM: cada
    violação amarra um identificador de regra a uma explicação didática. Guardar
    o `elemento` afetado (quando o modelo o informa) ajuda o autor a localizar o
    problema no arquivo.
    """

    regra: str        # identificador da regra violada, ex.: "SEG-001"
    explicacao: str   # explicação didática do problema, vinda do modelo
    elemento: str = ""  # elemento afetado (função/classe), se informado


@dataclass(frozen=True)
class ElementoDeCodigo:
    """Um elemento estrutural extraído de um arquivo via AST.

    É o "esqueleto lógico" que o sistema usa no lugar do texto cru: representa
    uma função, classe ou método, sem os detalhes de formatação do código.
    """

    tipo: str          # "funcao", "classe" ou "metodo"
    nome: str          # nome qualificado, ex.: "Calculadora.somar"
    assinatura: str    # a linha de declaração, ex.: "def somar(self, a, b)"
    linha_inicio: int  # primeira linha do elemento no arquivo
    linha_fim: int     # última linha do elemento no arquivo
