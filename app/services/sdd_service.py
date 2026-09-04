
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


_IDENTIFICADOR_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,32}$")

_ESCOPOS_VALIDOS = frozenset({"arquivo", "estrutura"})


_LIMITES_DE_CAMPO = {
    "titulo": 200,
    "regra": 4000,
    "motivacao": 4000,
    "como_identificar": 4000,
}


def carregar_sdd(diretorio_base: str | Path) -> list[RegraArquitetural]:

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

    configuracao = yaml.safe_load(configuracao_yaml) or {} if configuracao_yaml else None

    regras = [
        interpretar_regra(nome, texto)
        for nome, texto in sorted(arquivos_de_regra.items())
    ]

    if configuracao:
        _validar_vocabulario(regras, configuracao)

    return [regra for regra in regras if regra.status == "ativa"]


def carregar_configuracao(caminho: str | Path) -> dict:
    return yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}


def carregar_regras(
    diretorio: str | Path, configuracao: dict | None = None
) -> list[RegraArquitetural]:
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

    valor = str(escopo).strip().lower()
    if valor not in _ESCOPOS_VALIDOS:
        raise ErroDeSDD(
            f"{nome}: escopo '{escopo}' desconhecido. Use um destes: "
            + ", ".join(sorted(_ESCOPOS_VALIDOS))
        )
    return valor


def _validar_identificador(nome: str, identificador: str) -> None:

    if not _IDENTIFICADOR_VALIDO.match(identificador):
        raise ErroDeSDD(
            f"{nome}: identificador '{identificador}' inválido. Use apenas "
            "letras, números, ponto, hífen ou sublinhado (até 32 caracteres)."
        )


def _validar_tamanhos(nome: str, metadados: dict, secoes: dict) -> None:
    for campo, limite in _LIMITES_DE_CAMPO.items():
        valor = str(secoes.get(campo) or metadados.get(campo) or "")
        if len(valor) > limite:
            raise ErroDeSDD(
                f"{nome}: campo '{campo}' tem {len(valor)} caracteres e excede "
                f"o limite de {limite}."
            )


def _separar_frontmatter(nome: str, texto: str) -> tuple[dict, str]:
    if not texto.lstrip().startswith("---"):
        raise ErroDeSDD(f"{nome}: arquivo de regra sem frontmatter YAML")

    partes = texto.split("---", 2)
    if len(partes) < 3:
        raise ErroDeSDD(f"{nome}: frontmatter YAML não foi fechado com '---'")


    try:
        metadados = yaml.safe_load(partes[1]) or {}
    except yaml.YAMLError as erro:
        raise ErroDeSDD(f"{nome}: frontmatter YAML inválido: {erro}") from erro

    if not isinstance(metadados, dict):
        raise ErroDeSDD(f"{nome}: o frontmatter deve ser um mapeamento de campos")

    return metadados, partes[2]


def _extrair_secoes(corpo: str) -> dict[str, str]:

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
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return sem_acento.strip().lower()
