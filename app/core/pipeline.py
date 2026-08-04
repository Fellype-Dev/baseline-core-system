"""
Pipeline de revisão: o encadeamento dos filtros (feature E1 do Conjunto E).

Este é o caso de uso central do produto — o "miolo" que orquestra todos os
filtros já construídos, na ordem do documento de arquitetura:

    arquivos alterados (RepositorioPort)
      └─ para cada arquivo:
           identificar linguagem            (ast_service)
           linhas alteradas do diff         (diff_service)
           esqueleto dos elementos mudados  (ast_service)
           regras aplicáveis                (ConhecimentoPort)
           montar o prompt                  (prompt_service)
           avaliar com o modelo             (LLMPort)
           interpretar e formatar           (resultado_service)
      └─ publicar o comentário agregado     (RepositorioPort)

Repare que o pipeline recebe as PORTAS por parâmetro — nunca cria adaptadores.
Quem monta os adaptadores concretos é o composition root (`main.py`). Assim o
núcleo permanece testável com dublês, sem GitHub, sem Qdrant e sem LLM real.

A resiliência mais fina (rodar fora do laço de eventos, política de novas
tentativas, timeouts) é a feature E2; aqui já tratamos o caso mais comum de
falha estrutural: um arquivo Python que não parseia cai para a revisão baseada
apenas no diff, em vez de derrubar a revisão inteira.
"""

import logging

from app.core.models import (
    ArquivoAlterado,
    ConsultaDeRegras,
    EventoDeProgresso,
    PullRequest,
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
)
from app.services.diff_service import linhas_alteradas
from app.services.prompt_service import montar_prompt
from app.services.resultado_service import (
    formatar_erro_de_sintaxe,
    montar_comentario_de_avaliacao,
)

_log = logging.getLogger(__name__)

# Bloco honesto usado quando o modelo não pôde avaliar um arquivo. Igual à
# filosofia do resultado_service: nunca inventar um veredito — admitir a falha.
_MODELO_INDISPONIVEL = (
    "## ⚠️ Revisão arquitetural indisponível para este arquivo\n\n"
    "O modelo de linguagem não pôde ser consultado desta vez. Um revisor "
    "humano deve avaliar as alterações deste arquivo."
)


def revisar_pull_request(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
    observador: ObservadorPort | None = None,
) -> None:
    """Revisa o PR de ponta a ponta e publica o comentário com o resultado."""
    observador = observador or ObservadorNulo()

    comentario = analisar_pull_request(
        pr, repositorio, conhecimento, llm, observador
    )
    repositorio.publicar_comentario(pr, comentario)
    _anunciar(observador, "comentario", f"Comentário publicado no PR #{pr.numero}.")
    _anunciar(observador, "concluido", "Revisão concluída.")


def analisar_pull_request(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
    observador: ObservadorPort | None = None,
) -> str:
    """Produz o texto do comentário da revisão, sem publicá-lo.

    Separar a análise (que gera texto) da publicação (efeito colateral) deixa o
    encadeamento testável: dá para verificar o comentário sem simular a postagem.
    """
    observador = observador or ObservadorNulo()

    arquivos = repositorio.obter_arquivos_alterados(pr)
    _anunciar(
        observador,
        "arquivos",
        f"{len(arquivos)} arquivo(s) alterado(s) obtido(s) do repositório.",
    )

    blocos: list[str] = []
    for arquivo in arquivos:
        comentario = _revisar_arquivo(arquivo, conhecimento, llm, observador)
        if comentario is not None:
            blocos.append(f"**Arquivo:** `{arquivo.caminho}`\n\n{comentario}")

    if not blocos:
        return (
            "# Revisão Arquitetural\n\n"
            "Nenhuma regra arquitetural se aplica às alterações deste "
            "Pull Request."
        )

    corpo = "\n\n---\n\n".join(blocos)
    return f"# Revisão Arquitetural de Pull Request\n\n{corpo}"


def _revisar_arquivo(
    arquivo: ArquivoAlterado,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
    observador: ObservadorPort,
) -> str | None:
    """Revisa um único arquivo. Devolve o comentário, ou None se não há regra.

    Quando nenhuma regra é aplicável ao arquivo, não faz sentido acionar o
    modelo: o arquivo é simplesmente omitido da revisão.
    """
    linguagem = identificar_linguagem(arquivo.caminho)

    # Um arquivo que não parseia é reportado como tal, e não avaliado. Antes,
    # o erro era engolido e a revisão seguia com o diff — o autor nunca ficava
    # sabendo que havia submetido código inválido.
    erro_de_sintaxe = _erro_de_sintaxe(arquivo, linguagem)
    if erro_de_sintaxe is not None:
        _anunciar(
            observador,
            "sintaxe",
            f"`{arquivo.caminho}`: código inválido — revisão não realizada.",
        )
        return formatar_erro_de_sintaxe(
            erro_de_sintaxe.lineno, erro_de_sintaxe.msg or "sintaxe inválida"
        )

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
    )
    regras = conhecimento.buscar_regras_relevantes(consulta)
    if not regras:
        _anunciar(
            observador,
            "rag",
            f"`{arquivo.caminho}`: nenhuma regra aplicável — arquivo ignorado.",
        )
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
        # Resiliência (E2): a falha de um arquivo não pode derrubar o PR inteiro.
        # Não silenciamos (QUA-001): registramos o erro com stacktrace no log e
        # devolvemos um bloco honesto no lugar do veredito.
        _log.exception("Falha ao avaliar %s com o modelo.", arquivo.caminho)
        _anunciar(
            observador,
            "erro",
            f"`{arquivo.caminho}`: o modelo não pôde ser consultado.",
        )
        return _MODELO_INDISPONIVEL

    comentario = montar_comentario_de_avaliacao(resposta)
    _anunciar(
        observador, "avaliado", f"`{arquivo.caminho}`: avaliação concluída."
    )
    return comentario


def _anunciar(observador: ObservadorPort, etapa: str, descricao: str) -> None:
    """Avisa o observador, sem deixar que isso afete a revisão.

    Observabilidade é acessória: se o observador falhar (um navegador que se
    desconectou no meio, por exemplo), a revisão do Pull Request precisa seguir
    normalmente. Registramos a falha para não silenciá-la (QUA-001).
    """
    try:
        observador.registrar(EventoDeProgresso(etapa=etapa, descricao=descricao))
    except Exception:
        _log.exception("Falha ao notificar o observador na etapa '%s'.", etapa)


def _erro_de_sintaxe(
    arquivo: ArquivoAlterado, linguagem: str | None
) -> SyntaxError | None:
    """Devolve o erro de sintaxe do arquivo, ou None se ele é válido.

    Só faz sentido para linguagens que sabemos analisar e quando temos o
    conteúdo completo: sem o arquivo inteiro, um trecho isolado do diff pareceria
    inválido mesmo estando correto.
    """
    if linguagem != "python" or not arquivo.conteudo:
        return None

    try:
        extrair_esqueleto(arquivo.conteudo)
    except SyntaxError as erro:
        return erro
    return None


def _extrair_elementos_alterados(arquivo: ArquivoAlterado, linguagem: str | None):
    """Extrai o esqueleto dos elementos que mudaram, quando isso é possível.

    Só há AST para linguagens suportadas (hoje, Python) e quando temos o conteúdo
    completo do arquivo. Arquivos inválidos já foram tratados antes desta função
    (ver `_erro_de_sintaxe`), então aqui a análise não deve falhar.
    """
    if linguagem != "python" or not arquivo.conteudo:
        return []

    linhas = linhas_alteradas(arquivo.diff)
    return elementos_alterados(arquivo.conteudo, linhas)


def _descrever_mudanca(arquivo: ArquivoAlterado, elementos) -> str:
    """Monta a consulta em linguagem descritiva para a busca de regras (RAG).

    Sutileza registrada no projeto: a busca casa o que mudou contra regras
    escritas em português, então a consulta deve ser DESCRITIVA, não código cru.
    Quando há esqueleto AST, usamos as assinaturas (naturais e enxutas); sem ele,
    caímos para as linhas adicionadas do diff, o melhor sinal disponível.
    """
    if elementos:
        assinaturas = "; ".join(elemento.assinatura for elemento in elementos)
        return f"Alterações no arquivo {arquivo.caminho}. Elementos modificados: {assinaturas}"

    adicionadas = _linhas_adicionadas(arquivo.diff)
    return f"Alterações no arquivo {arquivo.caminho}. Trecho modificado: {adicionadas}"


def _linhas_adicionadas(diff: str) -> str:
    """Extrai o texto das linhas adicionadas do diff (sem o '+' inicial)."""
    linhas = [
        linha[1:]
        for linha in diff.splitlines()
        # '+' marca adição; '+++' é o cabeçalho do arquivo, que ignoramos.
        if linha.startswith("+") and not linha.startswith("+++")
    ]
    return " ".join(linhas)
