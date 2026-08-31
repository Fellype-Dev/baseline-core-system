"""
Serviço de leitura do documento SDD (Spec-Driven Development).

Estrutura esperada:

    sdd/
    ├── sdd.config.yml      # vocabulário da organização (categorias, severidades)
    └── regras/
        └── <ID>-<slug>.md  # uma regra por arquivo

Cada arquivo de regra combina frontmatter YAML (metadados legíveis por máquina)
com um corpo em markdown (o conteúdo em linguagem natural, para o LLM). Um
arquivo é, por construção, um fragmento semântico completo — o que dispensa o
recorte arbitrário por número de caracteres usado na maioria dos sistemas RAG.

Lógica pura: só lê arquivos e processa texto.
"""

import re
import unicodedata
from pathlib import Path

import yaml

from app.core.models import RegraArquitetural


class ErroDeSDD(Exception):
    """Problema na leitura ou na validação do documento SDD."""


_CABECALHO_SECAO = re.compile(r"^##\s+(?P<titulo>.+?)\s*$")

# Título da seção (normalizado) -> campo do modelo de domínio.
_SECOES = {
    "regra": "regra",
    "motivacao": "motivacao",
    "como identificar": "como_identificar",
    "exemplo incorreto": "exemplo_incorreto",
    "exemplo correto": "exemplo_correto",
}

_CAMPOS_OBRIGATORIOS = ("id", "titulo", "categoria", "severidade")

# O identificador é interpolado no comentário publicado no Pull Request, então
# não pode conter metacaracteres de markdown nem separadores de caminho. O
# padrão é deliberadamente permissivo quanto à NOMENCLATURA: cabe a cada
# organização escolher como nomeia suas regras (ARQ-001, SEC-1, PERF-12), e
# impor um formato rígido limitaria quem usa a ferramenta sem ganho de
# segurança.
_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,32}$")

# Naturezas de regra reconhecidas. Ver `RegraArquitetural.escopo`.
_ESCOPOS_VALIDOS = frozenset({"arquivo", "estrutura"})

# Limites de tamanho por campo. São generosos de propósito: existem para conter
# entradas absurdas que estourariam a janela de contexto do modelo, e não para
# ditar o estilo de redação das regras.
_LIMITES_DE_CAMPO = {
    "titulo": 200,
    "regra": 4000,
    "motivacao": 4000,
    "como_identificar": 4000,
}


def carregar_sdd(diretorio_base: str | Path) -> list[RegraArquitetural]:
    """Carrega o SDD completo a partir de um diretório do sistema de arquivos.

    Usado pelo script de indexação manual. Regras com status diferente de
    "ativa" são descartadas, para que uma regra descontinuada não gere
    apontamentos.
    """
    base = Path(diretorio_base)
    arquivo_config = base / "sdd.config.yml"
    configuracao = (
        carregar_configuracao(arquivo_config) if arquivo_config.exists() else None
    )

    regras = carregar_regras(base / "regras", configuracao)
    return [regra for regra in regras if regra.status == "ativa"]


def interpretar_sdd(
    arquivos_de_regra: dict[str, str], configuracao_yaml: str | None = None
) -> list[RegraArquitetural]:
    """Interpreta um SDD já lido para a memória, sem tocar no disco.

    Existe porque o SDD pertence à organização, e não à ferramenta: ele é obtido
    do repositório que está sendo revisado, por meio da porta do repositório, e
    chega aqui como texto. Manter a interpretação independente do sistema de
    arquivos é o que permite essa origem.

    Args:
        arquivos_de_regra: nome do arquivo -> conteúdo, um por regra.
        configuracao_yaml: conteúdo do `sdd.config.yml`, quando existir.
    """
    configuracao = yaml.safe_load(configuracao_yaml) or {} if configuracao_yaml else None

    regras = [
        interpretar_regra(nome, texto)
        for nome, texto in sorted(arquivos_de_regra.items())
    ]

    if configuracao:
        _validar_vocabulario(regras, configuracao)

    return [regra for regra in regras if regra.status == "ativa"]


def carregar_configuracao(caminho: str | Path) -> dict:
    """Lê o sdd.config.yml com o vocabulário declarado pela organização."""
    return yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}


def carregar_regras(
    diretorio: str | Path, configuracao: dict | None = None
) -> list[RegraArquitetural]:
    """Lê todas as regras de um diretório, uma por arquivo .md."""
    caminho = Path(diretorio)
    if not caminho.is_dir():
        raise ErroDeSDD(f"diretório de regras não encontrado: {caminho}")

    regras = [
        interpretar_regra(arquivo.name, arquivo.read_text(encoding="utf-8"))
        for arquivo in sorted(caminho.glob("*.md"))
    ]

    if configuracao:
        _validar_vocabulario(regras, configuracao)

    return regras


def interpretar_regra(nome: str, texto: str) -> RegraArquitetural:
    """Converte o conteúdo de um arquivo de regra em modelo de domínio.

    Recebe o texto já lido, e não um caminho, para que a origem da regra seja
    indiferente: ela pode vir do disco ou do repositório sob revisão.
    """
    metadados, corpo = _separar_frontmatter(nome, texto)
    secoes = _extrair_secoes(corpo)

    ausentes = [campo for campo in _CAMPOS_OBRIGATORIOS if not metadados.get(campo)]
    if ausentes:
        raise ErroDeSDD(
            f"{nome}: campos obrigatórios ausentes no frontmatter: "
            + ", ".join(ausentes)
        )

    for secao in ("regra", "motivacao"):
        if not secoes.get(secao):
            raise ErroDeSDD(f"{nome}: seção '{secao}' ausente ou vazia")

    _validar_identificador(nome, str(metadados["id"]))
    _validar_tamanhos(nome, metadados, secoes)

    return RegraArquitetural(
        identificador=metadados["id"],
        titulo=metadados["titulo"],
        categoria=metadados["categoria"],
        severidade=metadados["severidade"],
        regra=secoes["regra"],
        motivacao=secoes["motivacao"],
        linguagens=tuple(metadados.get("linguagens") or ()),
        aplica_se_a=tuple(metadados.get("aplica_se_a") or ()),
        excecoes=tuple(metadados.get("excecoes") or ()),
        status=metadados.get("status", "ativa"),
        escopo=_validar_escopo(nome, metadados.get("escopo", "arquivo")),
        como_identificar=secoes.get("como_identificar", ""),
        exemplo_incorreto=secoes.get("exemplo_incorreto", ""),
        exemplo_correto=secoes.get("exemplo_correto", ""),
    )


def _validar_escopo(nome: str, escopo) -> str:
    """Confere a natureza declarada da regra.

    Um escopo desconhecido é recusado em vez de tratado como padrão: uma regra
    estrutural interpretada como regra de arquivo seria avaliada contra cada
    arquivo alterado, produzindo apontamentos repetidos e sem sentido.
    """
    valor = str(escopo).strip().lower()
    if valor not in _ESCOPOS_VALIDOS:
        raise ErroDeSDD(
            f"{nome}: escopo '{escopo}' desconhecido. Use um destes: "
            + ", ".join(sorted(_ESCOPOS_VALIDOS))
        )
    return valor


def _validar_identificador(nome: str, identificador: str) -> None:
    """Recusa identificadores que não sejam seguros para publicação.

    O identificador é impresso no comentário do Pull Request. Caracteres de
    markdown, quebras de linha ou separadores de caminho permitiriam distorcer o
    comentário publicado a partir do conteúdo do documento.
    """
    if not _IDENTIFICADOR_VALIDO.match(identificador):
        raise ErroDeSDD(
            f"{nome}: identificador '{identificador}' inválido. Use apenas "
            "letras, números, ponto, hífen ou sublinhado (até 32 caracteres)."
        )


def _validar_tamanhos(nome: str, metadados: dict, secoes: dict) -> None:
    """Recusa campos longos demais para caber no prompt com folga."""
    for campo, limite in _LIMITES_DE_CAMPO.items():
        valor = str(secoes.get(campo) or metadados.get(campo) or "")
        if len(valor) > limite:
            raise ErroDeSDD(
                f"{nome}: campo '{campo}' tem {len(valor)} caracteres e excede "
                f"o limite de {limite}."
            )


def _separar_frontmatter(nome: str, texto: str) -> tuple[dict, str]:
    """Divide o conteúdo entre o frontmatter YAML e o corpo em markdown."""
    if not texto.lstrip().startswith("---"):
        raise ErroDeSDD(f"{nome}: arquivo de regra sem frontmatter YAML")

    # O frontmatter fica entre o primeiro e o segundo '---'.
    partes = texto.split("---", 2)
    if len(partes) < 3:
        raise ErroDeSDD(f"{nome}: frontmatter YAML não foi fechado com '---'")

    # O frontmatter vem de um repositório de terceiros e pode estar malformado.
    # Converter a falha do analisador YAML em ErroDeSDD é o que mantém o
    # tratamento sob um único tipo de exceção: sem isso, um documento inválido
    # escaparia do tratamento do pipeline e derrubaria a revisão inteira.
    try:
        metadados = yaml.safe_load(partes[1]) or {}
    except yaml.YAMLError as erro:
        raise ErroDeSDD(f"{nome}: frontmatter YAML inválido: {erro}") from erro

    if not isinstance(metadados, dict):
        raise ErroDeSDD(f"{nome}: o frontmatter deve ser um mapeamento de campos")

    return metadados, partes[2]


def _extrair_secoes(corpo: str) -> dict[str, str]:
    """Mapeia as seções '## Título' do corpo para os campos do modelo.

    Seções desconhecidas são ignoradas, o que permite à organização acrescentar
    anotações próprias ao arquivo sem quebrar a leitura.
    """
    secoes: dict[str, str] = {}
    campo_atual: str | None = None
    linhas: list[str] = []

    for linha in corpo.splitlines():
        cabecalho = _CABECALHO_SECAO.match(linha)
        if cabecalho:
            if campo_atual:
                secoes[campo_atual] = "\n".join(linhas).strip()
            campo_atual = _SECOES.get(_normalizar(cabecalho.group("titulo")))
            linhas = []
        elif campo_atual:
            linhas.append(linha)

    if campo_atual:
        secoes[campo_atual] = "\n".join(linhas).strip()

    return secoes


def _validar_vocabulario(
    regras: list[RegraArquitetural], configuracao: dict
) -> None:
    """Garante que categorias e severidades usadas foram declaradas na configuração.

    Isso mantém a taxonomia da organização consistente e denuncia erros de
    digitação já na leitura, em vez de deixá-los aparecer no feedback ao usuário.
    """
    categorias = set(configuracao.get("categorias") or ())
    severidades = set(configuracao.get("severidades") or ())

    for regra in regras:
        if categorias and regra.categoria not in categorias:
            raise ErroDeSDD(
                f"{regra.identificador}: categoria '{regra.categoria}' "
                "não declarada em sdd.config.yml"
            )
        if severidades and regra.severidade not in severidades:
            raise ErroDeSDD(
                f"{regra.identificador}: severidade '{regra.severidade}' "
                "não declarada em sdd.config.yml"
            )


def _normalizar(texto: str) -> str:
    """Minúsculas e sem acentos, para casar títulos de seção com tolerância."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.strip().lower()
