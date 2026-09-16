
import json
import re
from dataclasses import replace

from app.core.models import ResultadoDoArquivo, Violacao


class RespostaInvalidaError(Exception):
    """A resposta do modelo não pôde ser interpretada como o JSON esperado."""


_CERCA_DE_CODIGO = re.compile(
    r"^```(?:json)?\s*(?P<conteudo>.*?)\s*```$", re.DOTALL
)

_TAG_HTML = re.compile(r"<[^>]*>")
_LINK_MARKDOWN = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_URL_CRUA = re.compile(r"https?://\S+", re.IGNORECASE)

_LIMITE_DE_TEXTO = 1200


def sanear_texto_do_modelo(texto: str) -> str:

    limpo = _TAG_HTML.sub("", texto)
    limpo = _LINK_MARKDOWN.sub(r"\1", limpo)
    limpo = _URL_CRUA.sub("[link removido]", limpo)
    # Cercas de código quebrariam a formatação do comentário ao fechar blocos
    # que o sistema abriu.
    limpo = limpo.replace("```", "'''")
    limpo = limpo.strip()

    if len(limpo) > _LIMITE_DE_TEXTO:
        limpo = limpo[:_LIMITE_DE_TEXTO].rstrip() + "…"
    return limpo


def interpretar_violacoes(resposta_llm: str) -> list[Violacao]:

    dados = _carregar_json(resposta_llm)

    violacoes_cruas = dados.get("violacoes")
    if not isinstance(violacoes_cruas, list):
        raise RespostaInvalidaError(
            "O JSON não contém uma lista 'violacoes'."
        )

    violacoes: list[Violacao] = []
    for item in violacoes_cruas:
        if not isinstance(item, dict):
            raise RespostaInvalidaError(
                "Cada violação deveria ser um objeto JSON."
            )
        violacoes.append(
            Violacao(
                regra=str(item.get("regra", "")),
                explicacao=str(item.get("explicacao", "")),
                elemento=str(item.get("elemento", "")),
                linha=_como_inteiro(item.get("linha")),
            )
        )
    return violacoes


def _como_inteiro(valor) -> int:
    """O modelo às vezes devolve o número como texto; zero significa 'nenhuma'."""
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return 0


def descartar_regras_desconhecidas(
    violacoes: list[Violacao], identificadores_validos: frozenset[str]
) -> list[Violacao]:

    return [
        violacao
        for violacao in violacoes
        if violacao.regra.strip() in identificadores_validos
    ]


def anexar_evidencia(
    violacoes: list[Violacao],
    codigo_revisado: str,
    linhas_ignoradas: set[int] | frozenset[int] = frozenset(),
) -> list[Violacao]:
    """Troca o número apontado pelo texto real da linha, ou descarta.

    `linhas_ignoradas` recebe as linhas que não são instrução — continuação de
    literais de texto, onde o arquivo guarda código como dado.
    """
    linhas = codigo_revisado.splitlines()
    if not linhas:
        return violacoes

    com_evidencia = []
    for violacao in violacoes:
        if violacao.linha in linhas_ignoradas:
            continue
        texto = _linha_do_codigo(linhas, violacao.linha)
        if texto is None:
            continue
        com_evidencia.append(replace(violacao, evidencia=texto))
    return com_evidencia


def _linha_do_codigo(linhas: list[str], numero: int) -> str | None:
    """O texto da linha apontada, se ela existe e diz alguma coisa."""

    if numero < 1 or numero > len(linhas):
        return None

    texto = linhas[numero - 1].strip()
    # Linha em branco não sustenta apontamento nenhum: apontá-la é o mesmo que
    # não apontar, e o prompt foi explícito quanto a isso.
    return texto or None


def formatar_comentario(violacoes: list[Violacao]) -> str:

    if not violacoes:
        return (
            "## ✅ Revisão arquitetural\n\n"
            "Nenhuma violação das regras arquiteturais foi encontrada nas "
            "alterações deste Pull Request."
        )

    quantidade = len(violacoes)
    plural = "violação encontrada" if quantidade == 1 else "violações encontradas"
    partes = [f"## 🔴 Revisão arquitetural — {quantidade} {plural}\n"]

    for violacao in violacoes:

        titulo = f"### {sanear_texto_do_modelo(violacao.regra)}"
        elemento = sanear_texto_do_modelo(violacao.elemento)
        if elemento:
            titulo += f" — em `{elemento}`"
        partes.append(titulo)

        # A linha apontada vai junto do apontamento: o autor confere em um
        # relance se a ferramenta está olhando para o lugar certo.
        trecho = _formatar_evidencia(violacao)
        if trecho:
            partes.append(trecho)

        partes.append(sanear_texto_do_modelo(violacao.explicacao))

    return "\n\n".join(partes)


def _formatar_evidencia(violacao: Violacao) -> str:

    if not violacao.evidencia:
        return ""
    return f"    {violacao.linha} | {violacao.evidencia}"


def formatar_erro_de_sintaxe(linha: int | None, mensagem: str) -> str:

    local = f" na linha {linha}" if linha else ""
    return (
        "**⚠️ Erro de sintaxe**\n\n"
        f"Este arquivo não pôde ser interpretado{local}: {mensagem}.\n\n"
        "A análise estrutural foi ignorada neste arquivo; a revisão a seguir "
        "considerou apenas as linhas alteradas."
    )


def montar_comentario_de_avaliacao(
    resposta_llm: str,
    identificadores_validos: frozenset[str] | None = None,
    codigo_revisado: str | None = None,
) -> str:

    try:
        violacoes = interpretar_violacoes(resposta_llm)
    except RespostaInvalidaError:
        return (
            "## ⚠️ Revisão arquitetural automática indisponível\n\n"
            "Não foi possível interpretar a resposta do modelo desta vez, então "
            "nenhuma análise automática é apresentada. Um revisor humano deve "
            "avaliar este Pull Request."
        )

    if identificadores_validos is not None:
        violacoes = descartar_regras_desconhecidas(violacoes, identificadores_validos)

    if codigo_revisado is not None:
        violacoes = anexar_evidencia(violacoes, codigo_revisado)

    return formatar_comentario(violacoes)


# --- Extração do JSON -------------------------------------------------------

def _carregar_json(texto: str) -> dict:

    texto = texto.strip()

    for candidato in _candidatos_de_json(texto):
        try:
            dados = json.loads(candidato)
        except json.JSONDecodeError:
            continue
        if isinstance(dados, dict):
            return dados

    raise RespostaInvalidaError("Não foi encontrado um objeto JSON na resposta.")


def _candidatos_de_json(texto: str):
    yield texto

    cerca = _CERCA_DE_CODIGO.match(texto)
    if cerca:
        yield cerca.group("conteudo").strip()

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim > inicio:
        yield texto[inicio : fim + 1]


_NAO_AVALIADO = (
    "Não foi possível obter uma avaliação do modelo para este arquivo. "
    "Um revisor humano deve olhá-lo."
)


def avaliar_resposta(
    resposta_llm: str,
    identificadores_validos: frozenset[str],
    codigo_revisado: str | None = None,
    linhas_ignoradas: set[int] | frozenset[int] = frozenset(),
) -> list[Violacao] | None:

    try:
        violacoes = interpretar_violacoes(resposta_llm)
    except RespostaInvalidaError:
        return None

    violacoes = descartar_regras_desconhecidas(violacoes, identificadores_validos)
    if codigo_revisado is not None:
        violacoes = anexar_evidencia(
            violacoes, codigo_revisado, linhas_ignoradas
        )
    return violacoes


def montar_comentario_do_pr(
    resultados: list[ResultadoDoArquivo],
    blocos_de_estrutura: list[str] | tuple[str, ...] = (),
) -> str:

    destacados = [r for r in resultados if r.violacoes or r.aviso]
    nao_avaliados = [
        r for r in resultados if r.indisponivel and not (r.violacoes or r.aviso)
    ]
    limpos = [r for r in resultados if not r.tem_achado]

    partes = ["# Revisão Arquitetural", _resumo(resultados, nao_avaliados)]
    partes.extend(blocos_de_estrutura)
    partes.extend(_bloco_do_arquivo(r) for r in destacados)

    if nao_avaliados:
        partes.append(
            _recolhido(
                f"⚠️ {_contar(len(nao_avaliados), 'arquivo não avaliado', 'arquivos não avaliados')}",
                _lista_de_caminhos(nao_avaliados) + f"\n\n{_NAO_AVALIADO}",
            )
        )

    if limpos:
        partes.append(
            _recolhido(
                f"✅ {_contar(len(limpos), 'arquivo sem apontamentos', 'arquivos sem apontamentos')}",
                _lista_de_caminhos(limpos),
            )
        )

    return "\n\n".join(partes)


def _resumo(resultados, nao_avaliados) -> str:

    total = len(resultados)
    violacoes = sum(len(r.violacoes) for r in resultados)
    arquivos_com_violacao = sum(1 for r in resultados if r.violacoes)

    if violacoes:
        return (
            f"🔴 **{_contar(violacoes, 'violação encontrada', 'violações encontradas')}** "
            f"em {arquivos_com_violacao} de {_contar(total, 'arquivo', 'arquivos')} "
            "analisados."
        )
    if nao_avaliados:
        return (
            "⚠️ Nenhuma violação encontrada nos arquivos avaliados, mas "
            f"{_contar(len(nao_avaliados), 'arquivo ficou', 'arquivos ficaram')} "
            "sem avaliação."
        )
    if not total:
        return "Nenhum arquivo analisável neste Pull Request."
    return (
        f"✅ Nenhuma violação encontrada nos "
        f"{_contar(total, 'arquivo analisado', 'arquivos analisados')}."
    )


def _bloco_do_arquivo(resultado: ResultadoDoArquivo) -> str:

    partes = [f"### `{resultado.caminho}`"]
    if resultado.aviso:
        partes.append(resultado.aviso)
    if resultado.indisponivel:
        partes.append(_NAO_AVALIADO)
    partes.extend(_bloco_da_violacao(v) for v in resultado.violacoes)
    return "\n\n".join(partes)


def _bloco_da_violacao(violacao: Violacao) -> str:

    titulo = f"**{sanear_texto_do_modelo(violacao.regra)}**"
    elemento = sanear_texto_do_modelo(violacao.elemento)
    if elemento:
        titulo += f" — em `{elemento}`"

    partes = [titulo]
    trecho = _formatar_evidencia(violacao)
    if trecho:
        partes.append(trecho)
    partes.append(sanear_texto_do_modelo(violacao.explicacao))
    return "\n\n".join(partes)


def _recolhido(titulo: str, corpo: str) -> str:
    """Bloco que o GitHub mostra fechado, com o título sempre visível."""
    return f"<details>\n<summary>{titulo}</summary>\n\n{corpo}\n\n</details>"


def _lista_de_caminhos(resultados) -> str:
    return " · ".join(f"`{r.caminho}`" for r in resultados)


def _contar(quantidade: int, singular: str, plural: str) -> str:
    return f"{quantidade} {singular if quantidade == 1 else plural}"
