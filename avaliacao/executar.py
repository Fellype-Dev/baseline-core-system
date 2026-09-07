

import argparse
import difflib
import sys
import time
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.core.models import ArquivoAlterado, ConsultaDeRegras  # noqa: E402
from app.services.ast_service import (  # noqa: E402
    elementos_alterados,
    identificar_linguagem,
)
from app.services.diff_service import linhas_alteradas  # noqa: E402
from app.services.prompt_service import montar_prompt  # noqa: E402
from app.services.resultado_service import (  # noqa: E402
    RespostaInvalidaError,
    anexar_evidencia,
    descartar_regras_desconhecidas,
    interpretar_violacoes,
)
from avaliacao.metricas import (  # noqa: E402
    ResultadoDeCaso,
    calcular,
    formatar_relatorio,
)

CAMINHO_DOS_CASOS = RAIZ / "avaliacao" / "casos.yml"


CORPUS = {
    "casos": RAIZ / "avaliacao" / "casos.yml",
    "validacao": RAIZ / "avaliacao" / "validacao.yml",
    # Terceiro conjunto, reservado. Os dois primeiros já foram medidos e não
    # servem mais para sustentar número novo. Além disso, só este traz diffs
    # parciais — os anteriores entregam o arquivo inteiro ao modelo e por isso
    # não conseguem revelar falha de contexto.
    "contexto": RAIZ / "avaliacao" / "contexto.yml",
}

PAUSA_PADRAO_EM_SEGUNDOS = 7.0
TENTATIVAS_POR_CASO = 4

# Quantas linhas de contexto o GitHub coloca em volta de cada alteração. É esse
# número, e não o tamanho do arquivo, que decide o que o modelo consegue ver.
CONTEXTO_DO_GITHUB = 3


def carregar_casos(caminho: Path = CAMINHO_DOS_CASOS) -> list[dict]:
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return dados["casos"]


def montar_diff(codigo: str) -> str:
    """Diff de arquivo recém-criado: cada linha é uma adição.

    Serve para os casos que declaram só `codigo` — arquivo novo, em que o diff
    de fato contém tudo. Note que esse formato entrega o arquivo inteiro ao
    modelo, e portanto NÃO exercita corte de contexto. Casos que precisam disso
    declaram `codigo_base` e caem em `montar_diff_parcial`.
    """
    linhas = codigo.splitlines()
    cabecalho = f"@@ -0,0 +1,{len(linhas)} @@"
    return "\n".join([cabecalho] + [f"+{linha}" for linha in linhas])


def montar_diff_parcial(base: str, modificado: str) -> str:
    """Diff de alteração, no mesmo formato que o GitHub entrega.

    Este é o caminho que importa medir: em um Pull Request real a ferramenta
    quase nunca recebe o arquivo inteiro, e sim hunks com três linhas de
    contexto. O recorte é cego ao significado do código e pode terminar no
    meio de um bloco — foi assim que nasceu um falso positivo em produção.

    A API do GitHub devolve o `patch` sem os cabeçalhos `---`/`+++`, que são
    descartados aqui pelo mesmo motivo: medir o formato que chega de verdade.
    """
    linhas = difflib.unified_diff(
        base.splitlines(keepends=True),
        modificado.splitlines(keepends=True),
        n=CONTEXTO_DO_GITHUB,
    )
    corpo = [linha for linha in linhas if not linha.startswith(("---", "+++"))]
    return "".join(corpo).rstrip("\n")


def diff_do_caso(caso: dict) -> str:

    base = caso.get("codigo_base")
    if base is None:
        return montar_diff(caso["codigo"])
    return montar_diff_parcial(base, caso["codigo"])


def avaliar_caso(
    caso: dict,
    conhecimento,
    llm,
    *,
    incluir_exemplos: bool,
    incluir_corpo: bool = True,
    conferir_evidencia: bool = True,
) -> frozenset:
    """Submete um caso à ferramenta e devolve as regras que ela apontou."""
    arquivo = ArquivoAlterado(
        caminho=caso["caminho"],
        diff=diff_do_caso(caso),
        conteudo=caso["codigo"],
    )

    linguagem = identificar_linguagem(arquivo.caminho)
    elementos = []
    if linguagem == "python":
        try:
            elementos = elementos_alterados(
                arquivo.conteudo, linhas_alteradas(arquivo.diff)
            )
        except SyntaxError as erro:
            # Silenciar aqui degradaria a medição sem deixar rastro: o caso
            # seria avaliado só pelo diff, e o resultado pior apareceria como
            # limitação do modelo em vez de erro no corpus.
            print(
                f"    AVISO: '{caso['nome']}' tem código inválido "
                f"({erro.msg}); avaliado apenas pelo diff"
            )
            elementos = []

    consulta = ConsultaDeRegras(
        texto=_descrever(arquivo, elementos),
        caminho=arquivo.caminho,
        linguagem=linguagem or "",
    )
    regras = conhecimento.buscar_regras_relevantes(consulta)
    if not regras:
        return frozenset()

    prompt = montar_prompt(
        arquivo,
        elementos,
        regras,
        incluir_exemplos=incluir_exemplos,
        incluir_corpo=incluir_corpo,
    )
    resposta = _avaliar_com_retentativa(llm, prompt)

    try:
        violacoes = interpretar_violacoes(resposta)
    except RespostaInvalidaError:

        print(f"    AVISO: resposta ilegível do modelo em '{caso['nome']}'")
        return frozenset()

    # O mesmo filtro que a produção aplica antes de publicar o comentário. Sem
    # ele a medição descreveria um sistema que o usuário nunca vê: regras
    # inventadas pelo modelo entrariam na conta como se fossem apontamentos.
    violacoes = descartar_regras_desconhecidas(
        violacoes, frozenset(regra.identificador for regra in regras)
    )

    if conferir_evidencia and elementos:
        violacoes = anexar_evidencia(violacoes, arquivo.conteudo)

    return frozenset(v.regra.strip() for v in violacoes if v.regra.strip())


def _avaliar_com_retentativa(llm, prompt: str) -> str:

    espera = PAUSA_PADRAO_EM_SEGUNDOS
    for tentativa in range(1, TENTATIVAS_POR_CASO + 1):
        try:
            return llm.avaliar(prompt)
        except Exception as erro:
            if tentativa == TENTATIVAS_POR_CASO:
                raise
            print(
                f"    modelo recusou (tentativa {tentativa}/{TENTATIVAS_POR_CASO}: "
                f"{type(erro).__name__}); nova tentativa em {espera:.0f}s"
            )
            time.sleep(espera)
            espera *= 2
    raise RuntimeError("inalcançável")


def _descrever(arquivo: ArquivoAlterado, elementos) -> str:
    if elementos:
        assinaturas = "; ".join(e.assinatura for e in elementos)
        return (
            f"Alterações no arquivo {arquivo.caminho}. "
            f"Elementos modificados: {assinaturas}"
        )
    adicionadas = " ".join(
        linha[1:]
        for linha in arquivo.diff.splitlines()
        if linha.startswith("+") and not linha.startswith("+++")
    )
    return f"Alterações no arquivo {arquivo.caminho}. Trecho modificado: {adicionadas}"


def _montar_dependencias(motor: str, caminho_dados: str):

    import config
    from app.adapters.qdrant_adapter import QdrantAdapter
    from app.services.sdd_service import carregar_sdd

    conhecimento = QdrantAdapter(caminho_dados=caminho_dados)

    # As regras vêm do `sdd/` versionado, e não do que estiver no índice. Sem
    # isso a medição dependeria do estado em que o banco por acaso estivesse, e
    # duas execuções da mesma configuração poderiam divergir sem explicação.
    # O repositório vazio corresponde à coleção que o harness consulta.
    regras = carregar_sdd(RAIZ / "sdd")
    conhecimento.sincronizar_regras("", regras)
    print(f"Índice preparado: {len(regras)} regra(s) ativa(s) de sdd/.\n")

    if motor == "gemini":
        from app.adapters.gemini_adapter import GeminiAdapter

        llm = GeminiAdapter(
            api_key=config.GEMINI_API_KEY, modelo=config.GEMINI_MODEL
        )
    else:
        from app.adapters.local_llm_adapter import LocalLLMAdapter

        llm = LocalLLMAdapter(
            modelo=config.LLM_LOCAL_MODELO, url=config.LLM_LOCAL_URL
        )

    return conhecimento, llm


def principal() -> None:
    parser = argparse.ArgumentParser(description="Avaliação empírica da ferramenta.")
    parser.add_argument(
        "--com-exemplos",
        action="store_true",
        help="inclui os exemplos do SDD no prompt (experimento de few-shot)",
    )
    parser.add_argument(
        "--caso", help="executa apenas o caso de nome informado", default=None
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=None,
        help="segundos de espera entre casos, para respeitar a cota do modelo",
    )
    parser.add_argument(
        "--llm",
        choices=["local", "gemini"],
        default="local",
        help="qual motor avaliar (o sistema usa 'local'; 'gemini' é comparação)",
    )
    parser.add_argument(
        "--corpus",
        choices=sorted(CORPUS),
        default="casos",
        help="qual conjunto avaliar ('casos' = desenvolvimento; 'validacao' = reservado)",
    )
    parser.add_argument(
        "--dados",
        default="./dados_qdrant",
        help=(
            "diretório do índice vetorial; aponte para um caminho próprio "
            "quando o servidor estiver no ar (o Qdrant embarcado é de um "
            "processo só)"
        ),
    )
    parser.add_argument(
        "--sem-evidencia",
        action="store_true",
        help=(
            "não confere a citação do modelo contra o código (desliga o filtro "
            "de evidência, para comparação)"
        ),
    )
    parser.add_argument(
        "--sem-corpo",
        action="store_true",
        help=(
            "envia apenas o diff, sem a forma completa dos elementos alterados "
            "(configuração anterior, para comparação)"
        ),
    )
    argumentos = parser.parse_args()

    if argumentos.pausa is None:
        argumentos.pausa = 0.0 if argumentos.llm == "local" else PAUSA_PADRAO_EM_SEGUNDOS

    casos = carregar_casos(CORPUS[argumentos.corpus])
    if argumentos.caso:
        casos = [c for c in casos if c["nome"] == argumentos.caso]
        if not casos:
            print(f"Caso '{argumentos.caso}' não encontrado.")
            sys.exit(1)

    modo = "COM exemplos (few-shot)" if argumentos.com_exemplos else "SEM exemplos"
    contexto = "só o diff" if argumentos.sem_corpo else "diff + corpo dos elementos"
    evidencia = "sem conferência" if argumentos.sem_evidencia else "conferida"
    parciais = sum(1 for c in casos if c.get("codigo_base") is not None)
    print(
        f"Avaliando {len(casos)} caso(s) do conjunto '{argumentos.corpus}' — "
        f"motor '{argumentos.llm}', prompt {modo}, contexto: {contexto}, "
        f"evidência: {evidencia}.\n"
        f"Diffs parciais (como o GitHub entrega): {parciais}/{len(casos)}.\n"
    )

    conhecimento, llm = _montar_dependencias(argumentos.llm, argumentos.dados)

    resultados: list[ResultadoDeCaso] = []
    try:
        for indice, caso in enumerate(casos, start=1):
            print(f"  [{indice}/{len(casos)}] {caso['nome']}", flush=True)
            erro = None
            detectadas = frozenset()
            try:
                detectadas = avaliar_caso(
                    caso,
                    conhecimento,
                    llm,
                    incluir_exemplos=argumentos.com_exemplos,
                    incluir_corpo=not argumentos.sem_corpo,
                    conferir_evidencia=not argumentos.sem_evidencia,
                )
            except Exception as falha:

                erro = f"{type(falha).__name__}: {str(falha).splitlines()[0][:120]}"
                print(f"    PULANDO — {erro}", flush=True)

            resultados.append(
                ResultadoDeCaso(
                    nome=caso["nome"],
                    esperadas=frozenset(caso["esperado"]),
                    detectadas=detectadas,
                    erro=erro,
                )
            )
            if indice < len(casos):
                time.sleep(argumentos.pausa)
    finally:
        conhecimento.fechar()

    print()
    print(formatar_relatorio(resultados, calcular(resultados)))


if __name__ == "__main__":
    principal()
