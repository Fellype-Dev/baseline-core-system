"""
Executor da avaliação: roda o corpus contra a ferramenta e mede o resultado.

Cada caso do `casos.yml` é submetido ao mesmo encadeamento que o produto usa em
um Pull Request real (AST → recuperação de regras → modelo de linguagem), e o
conjunto de regras apontadas é comparado com o gabarito.

Uso:
    venv/Scripts/python.exe avaliacao/executar.py
    venv/Scripts/python.exe avaliacao/executar.py --com-exemplos
    venv/Scripts/python.exe avaliacao/executar.py --caso segredo_no_codigo

Cada caso avaliado consome uma chamada ao modelo de linguagem. `--caso` permite
depurar um único caso sem gastar o corpus inteiro.

Por que este módulo repete a sequência do `app/core/pipeline.py` em vez de
chamá-lo: o pipeline devolve o comentário já formatado em markdown, e medir
exigiria reinterpretar esse texto. Aqui a sequência é a mesma, mas o resultado
é coletado ainda estruturado (objetos `Violacao`), que é a forma correta de
medir. O preço é manter as duas sequências alinhadas caso o pipeline mude.
"""

import argparse
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
    interpretar_violacoes,
)
from avaliacao.metricas import (  # noqa: E402
    ResultadoDeCaso,
    calcular,
    formatar_relatorio,
)

CAMINHO_DOS_CASOS = RAIZ / "avaliacao" / "casos.yml"

# O plano gratuito do Gemini limita as chamadas por minuto. Uma rodada completa
# do corpus estoura esse limite se disparar tudo em sequência, então o executor
# espaça as chamadas e insiste quando é recusado. Sem isso, a avaliação
# simplesmente não termina.
PAUSA_PADRAO_EM_SEGUNDOS = 7.0
TENTATIVAS_POR_CASO = 4


def carregar_casos(caminho: Path = CAMINHO_DOS_CASOS) -> list[dict]:
    """Lê o corpus de avaliação com o gabarito."""
    dados = yaml.safe_load(caminho.read_text(encoding="utf-8"))
    return dados["casos"]


def montar_diff(codigo: str) -> str:
    """Gera o patch de um arquivo recém-adicionado ao Pull Request.

    Todas as linhas entram como incluídas, que é exatamente o diff que o GitHub
    envia para um arquivo novo. Gerar em vez de escrever à mão evita que um erro
    de digitação no patch seja confundido com erro da ferramenta.
    """
    linhas = codigo.splitlines()
    cabecalho = f"@@ -0,0 +1,{len(linhas)} @@"
    return "\n".join([cabecalho] + [f"+{linha}" for linha in linhas])


def avaliar_caso(caso: dict, conhecimento, llm, *, incluir_exemplos: bool) -> frozenset:
    """Submete um caso à ferramenta e devolve as regras que ela apontou."""
    arquivo = ArquivoAlterado(
        caminho=caso["caminho"],
        diff=montar_diff(caso["codigo"]),
        conteudo=caso["codigo"],
    )

    linguagem = identificar_linguagem(arquivo.caminho)
    elementos = []
    if linguagem == "python":
        try:
            elementos = elementos_alterados(
                arquivo.conteudo, linhas_alteradas(arquivo.diff)
            )
        except SyntaxError:
            elementos = []

    consulta = ConsultaDeRegras(
        texto=_descrever(arquivo, elementos),
        caminho=arquivo.caminho,
        linguagem=linguagem or "",
    )
    regras = conhecimento.buscar_regras_relevantes(consulta)
    if not regras:
        # Nenhuma regra aplicável: a ferramenta não aponta nada, por construção.
        return frozenset()

    prompt = montar_prompt(
        arquivo, elementos, regras, incluir_exemplos=incluir_exemplos
    )
    resposta = _avaliar_com_retentativa(llm, prompt)

    try:
        violacoes = interpretar_violacoes(resposta)
    except RespostaInvalidaError:
        # Resposta ilegível conta como "nada apontado": vira falso negativo nos
        # casos com violação, o que é o tratamento honesto — a ferramenta de
        # fato não entregou o apontamento.
        print(f"    AVISO: resposta ilegível do modelo em '{caso['nome']}'")
        return frozenset()

    return frozenset(v.regra.strip() for v in violacoes if v.regra.strip())


def _avaliar_com_retentativa(llm, prompt: str) -> str:
    """Chama o modelo insistindo quando a cota por minuto é recusada.

    A espera dobra a cada tentativa. Uma recusa por limite de taxa não é erro da
    ferramenta e não pode contaminar a métrica: por isso insistimos, em vez de
    registrar o caso como "nada detectado".
    """
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
    """Reproduz a consulta descritiva que o pipeline monta para o RAG."""
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


def _montar_dependencias(motor: str):
    """Monta o banco de conhecimento e o motor de linguagem escolhido.

    A avaliação monta seus próprios adaptadores (em vez de importá-los do
    `main`) justamente para poder submeter o MESMO corpus a motores diferentes —
    é isso que torna possível comparar o modelo local com o Gemini.
    """
    import config
    from app.adapters.qdrant_adapter import QdrantAdapter

    conhecimento = QdrantAdapter()

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
    argumentos = parser.parse_args()

    # O modelo local não tem cota: esperar entre casos só desperdiça tempo.
    if argumentos.pausa is None:
        argumentos.pausa = 0.0 if argumentos.llm == "local" else PAUSA_PADRAO_EM_SEGUNDOS

    casos = carregar_casos()
    if argumentos.caso:
        casos = [c for c in casos if c["nome"] == argumentos.caso]
        if not casos:
            print(f"Caso '{argumentos.caso}' não encontrado.")
            sys.exit(1)

    modo = "COM exemplos (few-shot)" if argumentos.com_exemplos else "SEM exemplos"
    print(
        f"Avaliando {len(casos)} caso(s) — motor '{argumentos.llm}', prompt {modo}.\n"
    )

    conhecimento, llm = _montar_dependencias(argumentos.llm)

    resultados: list[ResultadoDeCaso] = []
    try:
        for indice, caso in enumerate(casos, start=1):
            print(f"  [{indice}/{len(casos)}] {caso['nome']}", flush=True)
            erro = None
            detectadas = frozenset()
            try:
                detectadas = avaliar_caso(
                    caso, conhecimento, llm, incluir_exemplos=argumentos.com_exemplos
                )
            except Exception as falha:
                # O modelo ficou indisponível (cota diária, indisponibilidade).
                # Registrar e seguir: assim os casos já medidos não se perdem, e
                # o relatório sai com o que foi possível apurar.
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
