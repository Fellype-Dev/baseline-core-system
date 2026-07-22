"""
Serviço de interpretação do resultado da avaliação (feature D3 do Conjunto D).

Fecha o ciclo do Motor LLM: pega o TEXTO devolvido pelo modelo (via `LLMPort`) e
o transforma no comentário que será postado no Pull Request. Duas etapas:

1. **Interpretar** — extrair do texto o JSON `{"violacoes": [...]}` e convertê-lo
   em objetos `Violacao` do domínio.
2. **Formatar** — renderizar essas violações como um comentário em markdown,
   didático e legível.

Tudo é lógica PURA (só processa texto), testável sem rede.

Robustez: apesar de o prompt pedir "apenas JSON", modelos de linguagem às vezes
embrulham a resposta em cercas de código (```json ... ```) ou acrescentam texto
em volta. A interpretação tolera esses casos comuns. Quando ainda assim não for
possível extrair um JSON válido, NÃO inventamos violações: a função de alto nível
produz um comentário honesto avisando que a análise automática falhou, deixando a
palavra final para o revisor humano.
"""

import json
import re

from app.core.models import Violacao


class RespostaInvalidaError(Exception):
    """A resposta do modelo não pôde ser interpretada como o JSON esperado."""


# Cerca de código markdown, opcionalmente com a linguagem: ```json ... ```
_CERCA_DE_CODIGO = re.compile(
    r"^```(?:json)?\s*(?P<conteudo>.*?)\s*```$", re.DOTALL
)


def interpretar_violacoes(resposta_llm: str) -> list[Violacao]:
    """Extrai as violações do texto devolvido pelo modelo.

    Levanta `RespostaInvalidaError` se não houver um JSON com a estrutura
    esperada — cabe a quem chama decidir o que fazer (ver
    `montar_comentario_de_avaliacao`, que trata isso como comentário de erro).
    """
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
            )
        )
    return violacoes


def formatar_comentario(violacoes: list[Violacao]) -> str:
    """Renderiza as violações como o comentário em markdown do PR.

    Lista vazia significa conformidade — um comentário de aprovação. Do
    contrário, uma seção por violação, citando o identificador da regra para dar
    rastreabilidade ao feedback.
    """
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
        titulo = f"### {violacao.regra}"
        if violacao.elemento:
            titulo += f" — em `{violacao.elemento}`"
        partes.append(titulo)
        partes.append(violacao.explicacao)

    return "\n\n".join(partes)


def montar_comentario_de_avaliacao(resposta_llm: str) -> str:
    """Feature D3 completa: interpreta a resposta do modelo e formata o comentário.

    Em caso de resposta irrecuperável, devolve um comentário honesto de falha —
    sem inventar violações — para que o revisor humano assuma.
    """
    try:
        violacoes = interpretar_violacoes(resposta_llm)
    except RespostaInvalidaError:
        return (
            "## ⚠️ Revisão arquitetural automática indisponível\n\n"
            "Não foi possível interpretar a resposta do modelo desta vez, então "
            "nenhuma análise automática é apresentada. Um revisor humano deve "
            "avaliar este Pull Request."
        )
    return formatar_comentario(violacoes)


# --- Extração do JSON -------------------------------------------------------

def _carregar_json(texto: str) -> dict:
    """Tenta obter um objeto JSON do texto, tolerando embrulhos comuns.

    Estratégia, da mais confiável à mais tolerante:
    1. o texto todo já é JSON;
    2. o texto é uma cerca de código markdown (```json ... ```);
    3. há um objeto `{...}` em algum lugar do texto (pega do primeiro '{' ao
       último '}').
    """
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
    """Gera, em ordem de preferência, trechos que podem ser o JSON."""
    yield texto

    cerca = _CERCA_DE_CODIGO.match(texto)
    if cerca:
        yield cerca.group("conteudo").strip()

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim > inicio:
        yield texto[inicio : fim + 1]
