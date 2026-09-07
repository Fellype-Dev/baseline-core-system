
import logging

from app.core.models import (
    ArquivoAlterado,
    ConsultaDeRegras,
    EventoDeProgresso,
    PullRequest,
    RegraArquitetural,
    ResultadoDoArquivo,
)
from app.core.observador import ObservadorNulo
from app.core.ports import (
    ConhecimentoPort,
    LLMPort,
    ObservadorPort,
    RepositorioPort,
)
from app.services.ast_service import (
    elementos_alterados,
    extrair_esqueleto,
    identificar_linguagem,
    linhas_de_texto_literal,
)
from app.services.diff_service import linhas_alteradas
from app.services.prompt_service import montar_prompt, montar_prompt_de_estrutura
from app.services.resultado_service import (
    avaliar_resposta,
    formatar_erro_de_sintaxe,
    montar_comentario_de_avaliacao,
    montar_comentario_do_pr,
)
from app.services.sdd_service import ErroDeSDD, interpretar_sdd

_log = logging.getLogger(__name__)


# O que o produto considera motivo para revisar. Mora no núcleo porque é decisão
# de produto: mudar de ideia sobre quando revisar não pode exigir alterar quem
# fala o protocolo do GitHub. Um Pull Request fechado chega até aqui e é
# recusado nesta linha, e não numa condição escondida no adaptador de entrada.
EVENTOS_QUE_PEDEM_REVISAO = frozenset({"aberto", "reaberto", "atualizado"})


def merece_revisao(evento: str) -> bool:
    """Diz se o que aconteceu com o Pull Request pede uma revisão nova.

    Revisar de novo a cada push é o que fecha o ciclo: sem isso a ferramenta
    aponta uma vez, na abertura, e nunca verifica a correção que ela mesma
    provocou.
    """
    return evento in EVENTOS_QUE_PEDEM_REVISAO


def revisar_pull_request(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
    observador: ObservadorPort | None = None,
) -> None:
    observador = observador or ObservadorNulo()

    comentario = analisar_pull_request(
        pr, repositorio, conhecimento, llm, observador
    )
    repositorio.publicar_revisao(pr, comentario)
    _anunciar(observador, "comentario", f"Comentário publicado no PR #{pr.numero}.")
    _anunciar(observador, "concluido", "Revisão concluída.")


def analisar_pull_request(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
    observador: ObservadorPort | None = None,
) -> str:

    observador = observador or ObservadorNulo()

    # As regras vêm do repositório revisado, e não da ferramenta: cada
    # organização declara as suas, versionadas junto ao próprio código.
    regras = _carregar_regras_do_repositorio(pr, repositorio, conhecimento, observador)
    if regras is None:
        return (
            "# Revisão Arquitetural\n\n"
            "Este repositório não possui um documento de especificação "
            "arquitetural em `sdd/`, ou nenhuma de suas regras está ativa. "
            "Nenhuma verificação foi realizada."
        )

    blocos_de_estrutura = _revisar_estrutura(
        pr, repositorio, llm, regras, observador
    )

    arquivos = repositorio.obter_arquivos_alterados(pr)
    _anunciar(
        observador,
        "arquivos",
        f"{len(arquivos)} arquivo(s) alterado(s) obtido(s) do repositório.",
    )

    resultados: list[ResultadoDoArquivo] = []
    for arquivo in arquivos:
        resultado = _revisar_arquivo(
            arquivo, pr.repositorio, conhecimento, llm, observador
        )
        if resultado is not None:
            resultados.append(resultado)

    if not resultados and not blocos_de_estrutura:
        return (
            "# Revisão Arquitetural\n\n"
            "Nenhuma regra arquitetural se aplica às alterações deste "
            "Pull Request."
        )

    return montar_comentario_do_pr(resultados, blocos_de_estrutura)


def _carregar_regras_do_repositorio(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    observador: ObservadorPort,
) -> list[RegraArquitetural] | None:

    documento = repositorio.obter_documento_sdd(pr)
    if documento.vazio:
        _anunciar(
            observador, "sdd", "O repositório não declara regras arquiteturais."
        )
        return None

    try:
        regras = interpretar_sdd(documento.regras, documento.configuracao)
    except ErroDeSDD:
        _log.exception("Documento de especificação inválido em %s.", pr.repositorio)
        _anunciar(observador, "erro", "Documento de especificação inválido.")
        return None

    if not regras:
        _anunciar(observador, "sdd", "Nenhuma regra ativa no documento.")
        return None

    de_arquivo = [regra for regra in regras if regra.escopo == "arquivo"]
    conhecimento.sincronizar_regras(pr.repositorio, de_arquivo)
    _anunciar(
        observador,
        "sdd",
        f"{len(regras)} regra(s) ativa(s) carregada(s) de `{pr.repositorio}`.",
    )
    return regras


def _revisar_estrutura(
    pr: PullRequest,
    repositorio: RepositorioPort,
    llm: LLMPort,
    regras: list[RegraArquitetural],
    observador: ObservadorPort,
) -> list[str]:

    estruturais = [regra for regra in regras if regra.escopo == "estrutura"]
    if not estruturais:
        return []

    estrutura = repositorio.obter_estrutura(pr)
    if not estrutura.diretorios_novos:
        _anunciar(
            observador, "estrutura", "Nenhum diretório novo nesta submissão."
        )
        return []

    _anunciar(
        observador,
        "estrutura",
        f"{len(estrutura.diretorios_novos)} diretório(s) criado(s): "
        + ", ".join(f"`{d}`" for d in estrutura.diretorios_novos),
    )

    prompt = montar_prompt_de_estrutura(estrutura, estruturais)
    try:
        resposta = llm.avaliar(prompt)
    except Exception:
        _log.exception("Falha ao avaliar a estrutura de %s.", pr.repositorio)
        _anunciar(observador, "erro", "Estrutura não pôde ser avaliada.")
        return []

    comentario = montar_comentario_de_avaliacao(
        resposta, frozenset(regra.identificador for regra in estruturais)
    )
    if "✅" in comentario:
        return []

    return [f"**Estrutura do repositório**\n\n{comentario}"]


def _revisar_arquivo(
    arquivo: ArquivoAlterado,
    repositorio: str,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
    observador: ObservadorPort,
) -> ResultadoDoArquivo | None:
    """O que a revisão apurou sobre este arquivo, ou None se não houve o que ver.

    Devolve estrutura, e não texto formatado: é o que permite ao chamador
    resumir o Pull Request inteiro — separar o que pede ação do que não pede
    exige saber o que aconteceu, não ler o markdown que descreve.
    """
    linguagem = identificar_linguagem(arquivo.caminho)


    erro_de_sintaxe = _erro_de_sintaxe(arquivo, linguagem)
    if erro_de_sintaxe is not None:
        aviso = formatar_erro_de_sintaxe(
            erro_de_sintaxe.lineno, erro_de_sintaxe.msg or "sintaxe inválida"
        )
        elementos = []
        _anunciar(
            observador,
            "sintaxe",
            f"`{arquivo.caminho}`: código inválido — revisão seguirá pelo diff.",
        )
    else:
        aviso = None
        elementos = _extrair_elementos_alterados(arquivo, linguagem)
        _anunciar(
            observador,
            "ast",
            f"`{arquivo.caminho}`: {len(elementos)} elemento(s) alterado(s) "
            "isolado(s) pela análise sintática.",
        )

    consulta = ConsultaDeRegras(
        texto=_descrever_mudanca(arquivo, elementos),
        caminho=arquivo.caminho,
        linguagem=linguagem or "",
        repositorio=repositorio,
    )
    regras = conhecimento.buscar_regras_relevantes(consulta)
    if not regras:
        _anunciar(
            observador,
            "rag",
            f"`{arquivo.caminho}`: nenhuma regra aplicável — arquivo ignorado.",
        )
        # Sem regra não houve avaliação; só o aviso de sintaxe, se houver,
        # ainda é informação útil ao autor.
        if aviso:
            return ResultadoDoArquivo(arquivo.caminho, aviso=aviso)
        return None

    identificadores = ", ".join(regra.identificador for regra in regras)
    _anunciar(
        observador,
        "rag",
        f"`{arquivo.caminho}`: regras recuperadas — {identificadores}.",
    )

    prompt = montar_prompt(arquivo, elementos, regras)
    _anunciar(
        observador, "llm", f"Consultando o modelo sobre `{arquivo.caminho}`..."
    )
    try:
        resposta = llm.avaliar(prompt)
    except Exception:

        _log.exception("Falha ao avaliar %s com o modelo.", arquivo.caminho)
        _anunciar(
            observador,
            "erro",
            f"`{arquivo.caminho}`: o modelo não pôde ser consultado.",
        )
        return ResultadoDoArquivo(
            arquivo.caminho, aviso=aviso or "", indisponivel=True
        )

    # A conferência da linha só faz sentido quando o modelo recebeu a listagem
    # numerada. Sem elementos isolados não há numeração no prompt, e cobrar um
    # número que não foi oferecido descartaria apontamentos legítimos.
    violacoes = avaliar_resposta(
        resposta,
        frozenset(regra.identificador for regra in regras),
        codigo_revisado=arquivo.conteudo if elementos else None,
        linhas_ignoradas=(
            linhas_de_texto_literal(arquivo.conteudo) if elementos else frozenset()
        ),
    )

    if violacoes is None:
        _log.warning(
            "Resposta ilegível do modelo ao avaliar %s.", arquivo.caminho
        )
        _anunciar(
            observador,
            "erro",
            f"`{arquivo.caminho}`: resposta do modelo ilegível.",
        )
        return ResultadoDoArquivo(
            arquivo.caminho, aviso=aviso or "", indisponivel=True
        )

    _anunciar(
        observador, "avaliado", f"`{arquivo.caminho}`: avaliação concluída."
    )
    return ResultadoDoArquivo(
        arquivo.caminho, tuple(violacoes), aviso=aviso or ""
    )


def _anunciar(observador: ObservadorPort, etapa: str, descricao: str) -> None:

    try:
        observador.registrar(EventoDeProgresso(etapa=etapa, descricao=descricao))
    except Exception:
        _log.exception("Falha ao notificar o observador na etapa '%s'.", etapa)


def _erro_de_sintaxe(
    arquivo: ArquivoAlterado, linguagem: str | None
) -> SyntaxError | None:

    if linguagem != "python" or not arquivo.conteudo:
        return None

    try:
        extrair_esqueleto(arquivo.conteudo)
    except SyntaxError as erro:
        return erro
    return None


def _extrair_elementos_alterados(arquivo: ArquivoAlterado, linguagem: str | None):

    if linguagem != "python" or not arquivo.conteudo:
        return []

    linhas = linhas_alteradas(arquivo.diff)
    return elementos_alterados(arquivo.conteudo, linhas)


def _descrever_mudanca(arquivo: ArquivoAlterado, elementos) -> str:

    if elementos:
        assinaturas = "; ".join(elemento.assinatura for elemento in elementos)
        return f"Alterações no arquivo {arquivo.caminho}. Elementos modificados: {assinaturas}"

    adicionadas = _linhas_adicionadas(arquivo.diff)
    return f"Alterações no arquivo {arquivo.caminho}. Trecho modificado: {adicionadas}"


def _linhas_adicionadas(diff: str) -> str:
    linhas = [
        linha[1:]
        for linha in diff.splitlines()
        if linha.startswith("+") and not linha.startswith("+++")
    ]
    return " ".join(linhas)
