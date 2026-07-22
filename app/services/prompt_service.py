"""
Serviço de montagem do prompt de avaliação (feature D1 do Conjunto D).

Aqui mora a *inteligência do produto*: como combinar o código que mudou com as
regras arquiteturais recuperadas, e o que pedir ao modelo de linguagem. Por
decisão de arquitetura, quem monta o prompt é o NÚCLEO — a `LLMPort` só sabe
"receber texto, devolver texto" (ver `app/core/ports.py`). Consequência prática:
esta lógica é PURA (sem rede, sem chave de API, sem banco vetorial) e, portanto,
inteiramente testável com objetos de exemplo.

O prompt combina duas visões complementares do que mudou:

* os **elementos alterados** (assinaturas extraídas via AST) — dão o *onde*:
  em qual função, classe ou método a mudança aconteceu;
* o **diff** (linhas adicionadas/removidas) — dá o *quê*: o conteúdo real do
  corpo, necessário para regras que vivem dentro da função (ex.: um segredo
  escrito no código só aparece no corpo, nunca na assinatura).

Nota importante (e distinta do RAG): ao montar a *consulta de embeddings* nós
evitamos mandar código cru, porque a busca casa código contra regras em
português. Aqui é o contrário — o modelo precisa VER o código para julgá-lo, e
mostrar as linhas exatas é o comportamento correto.

O formato de saída pedido é JSON estruturado (e não markdown livre) por dois
motivos: desacopla a formatação do comentário (feature D3, que vira só
"renderizar JSON") e torna as violações CONTÁVEIS por categoria de regra — o
insumo do capítulo de Resultados do TCC.
"""

import json

from app.core.models import ArquivoAlterado, ElementoDeCodigo, RegraArquitetural


def montar_prompt(
    arquivo: ArquivoAlterado,
    elementos_alterados: list[ElementoDeCodigo],
    regras: list[RegraArquitetural],
    *,
    incluir_exemplos: bool = False,
) -> str:
    """Constrói o prompt que será enviado ao modelo de linguagem.

    Args:
        arquivo: o arquivo do PR sob análise (caminho + diff).
        elementos_alterados: o esqueleto AST dos elementos que mudaram — dá ao
            modelo o contexto estrutural de "onde".
        regras: as regras do SDD já filtradas como aplicáveis a este arquivo.
            Cabe ao chamador não invocar o modelo quando esta lista é vazia
            (avaliar contra nenhuma regra não faz sentido); ainda assim a função
            é robusta a esse caso para permanecer simples de testar.
        incluir_exemplos: se True, injeta os pares de exemplo incorreto/correto
            de cada regra como "few-shot". É o EXPERIMENTO planejado para o
            capítulo de Resultados: medir se os exemplos melhoram a precisão.
            Fica como um parâmetro (e não como duas funções) justamente para que
            o experimento seja uma linha de teste, não uma refatoração.

    Returns:
        O prompt completo, em português, terminando com a instrução de formato.
    """
    secoes = [
        _INSTRUCAO_DE_PAPEL,
        _formatar_regras(regras, incluir_exemplos=incluir_exemplos),
        _formatar_codigo(arquivo, elementos_alterados),
        _instrucao_de_saida(),
    ]
    # Duas quebras de linha entre seções deixam o prompt legível para humanos
    # (útil ao depurar) e bem delimitado para o modelo.
    return "\n\n".join(secoes)


# --- Blocos do prompt -------------------------------------------------------

_INSTRUCAO_DE_PAPEL = (
    "Você é um revisor de arquitetura de software. Sua tarefa é avaliar as "
    "alterações de um Pull Request EXCLUSIVAMENTE contra as regras "
    "arquiteturais fornecidas abaixo. Não invente regras nem aponte questões "
    "de estilo que não estejam listadas. Para cada violação encontrada, cite o "
    "identificador da regra correspondente e explique o problema de forma "
    "didática, para que o autor entenda o motivo — não apenas o que corrigir."
)


def _formatar_regras(
    regras: list[RegraArquitetural], *, incluir_exemplos: bool
) -> str:
    """Renderiza o bloco com as regras aplicáveis."""
    if not regras:
        return "## Regras arquiteturais aplicáveis\n\n(Nenhuma regra aplicável.)"

    blocos = [_formatar_regra(r, incluir_exemplos=incluir_exemplos) for r in regras]
    return "## Regras arquiteturais aplicáveis\n\n" + "\n\n".join(blocos)


def _formatar_regra(regra: RegraArquitetural, *, incluir_exemplos: bool) -> str:
    """Renderiza uma única regra em linguagem natural para o modelo.

    Inclui os campos que ajudam o julgamento (a norma, o porquê e os sinais
    observáveis) e, opcionalmente, os exemplos como few-shot. Campos vazios são
    omitidos para não poluir o prompt.
    """
    linhas = [f"### {regra.identificador} — {regra.titulo}"]
    linhas.append(f"Regra: {regra.regra}")
    linhas.append(f"Motivação: {regra.motivacao}")

    if regra.como_identificar:
        linhas.append(f"Como identificar: {regra.como_identificar}")

    if incluir_exemplos and (regra.exemplo_incorreto or regra.exemplo_correto):
        if regra.exemplo_incorreto:
            linhas.append(f"Exemplo incorreto:\n{regra.exemplo_incorreto}")
        if regra.exemplo_correto:
            linhas.append(f"Exemplo correto:\n{regra.exemplo_correto}")

    return "\n".join(linhas)


def _formatar_codigo(
    arquivo: ArquivoAlterado, elementos: list[ElementoDeCodigo]
) -> str:
    """Renderiza o bloco com o código alterado: estrutura (AST) + diff."""
    linhas = ["## Código alterado", f"Arquivo: {arquivo.caminho}"]

    if elementos:
        linhas.append("\nElementos estruturais alterados (contexto de onde):")
        for elemento in elementos:
            linhas.append(f"- {elemento.tipo} `{elemento.nome}`: {elemento.assinatura}")
    else:
        # Arquivo sem estrutura isolável (ex.: linguagem não suportada pela AST,
        # ou mudança fora de qualquer função). O diff, sozinho, ainda serve.
        linhas.append(
            "\n(Nenhum elemento estrutural isolado; avalie pelas linhas alteradas.)"
        )

    linhas.append("\nAlterações (diff no formato do git):")
    linhas.append(arquivo.diff)
    return "\n".join(linhas)


def _instrucao_de_saida() -> str:
    """Instrui o modelo a responder SÓ com o JSON no formato esperado.

    O exemplo do formato é gerado com `json.dumps` a partir de um dicionário
    real: assim o texto do prompt nunca destoa do que o parser da feature D3
    vai esperar — a estrutura é definida em um só lugar.
    """
    formato = {
        "violacoes": [
            {
                "regra": "ID-DA-REGRA",
                "elemento": "nome do elemento afetado (ou vazio)",
                "explicacao": "explicação didática da violação",
            }
        ]
    }
    exemplo = json.dumps(formato, ensure_ascii=False, indent=2)
    return (
        "## Formato da resposta\n"
        "Responda APENAS com um objeto JSON válido, sem texto antes ou depois, "
        "seguindo exatamente esta estrutura:\n"
        f"{exemplo}\n"
        "Se o código estiver em conformidade com todas as regras, retorne a "
        'lista vazia: {"violacoes": []}.'
    )
