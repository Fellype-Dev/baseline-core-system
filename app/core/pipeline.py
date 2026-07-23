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

from app.core.models import ArquivoAlterado, ConsultaDeRegras, PullRequest
from app.core.ports import ConhecimentoPort, LLMPort, RepositorioPort
from app.services.ast_service import elementos_alterados, identificar_linguagem
from app.services.diff_service import linhas_alteradas
from app.services.prompt_service import montar_prompt
from app.services.resultado_service import montar_comentario_de_avaliacao


def revisar_pull_request(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
) -> None:
    """Revisa o PR de ponta a ponta e publica o comentário com o resultado."""
    comentario = analisar_pull_request(pr, repositorio, conhecimento, llm)
    repositorio.publicar_comentario(pr, comentario)


def analisar_pull_request(
    pr: PullRequest,
    repositorio: RepositorioPort,
    conhecimento: ConhecimentoPort,
    llm: LLMPort,
) -> str:
    """Produz o texto do comentário da revisão, sem publicá-lo.

    Separar a análise (que gera texto) da publicação (efeito colateral) deixa o
    encadeamento testável: dá para verificar o comentário sem simular a postagem.
    """
    arquivos = repositorio.obter_arquivos_alterados(pr)

    blocos: list[str] = []
    for arquivo in arquivos:
        comentario = _revisar_arquivo(arquivo, conhecimento, llm)
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
    arquivo: ArquivoAlterado, conhecimento: ConhecimentoPort, llm: LLMPort
) -> str | None:
    """Revisa um único arquivo. Devolve o comentário, ou None se não há regra.

    Quando nenhuma regra é aplicável ao arquivo, não faz sentido acionar o
    modelo: o arquivo é simplesmente omitido da revisão.
    """
    linguagem = identificar_linguagem(arquivo.caminho)
    elementos = _extrair_elementos_alterados(arquivo, linguagem)

    consulta = ConsultaDeRegras(
        texto=_descrever_mudanca(arquivo, elementos),
        caminho=arquivo.caminho,
        linguagem=linguagem or "",
    )
    regras = conhecimento.buscar_regras_relevantes(consulta)
    if not regras:
        return None

    prompt = montar_prompt(arquivo, elementos, regras)
    resposta = llm.avaliar(prompt)
    return montar_comentario_de_avaliacao(resposta)


def _extrair_elementos_alterados(arquivo: ArquivoAlterado, linguagem: str | None):
    """Extrai o esqueleto dos elementos que mudaram, quando isso é possível.

    Só há AST para linguagens suportadas (hoje, Python) e quando temos o conteúdo
    completo do arquivo. Um arquivo que não parseia (Python inválido no meio de
    um PR em andamento) não deve derrubar a revisão: caímos para a lista vazia e
    o prompt se apoia apenas no diff.
    """
    if linguagem != "python" or not arquivo.conteudo:
        return []

    linhas = linhas_alteradas(arquivo.diff)
    try:
        return elementos_alterados(arquivo.conteudo, linhas)
    except SyntaxError:
        return []


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
