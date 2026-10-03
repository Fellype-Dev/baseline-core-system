"""Mede quanto custa uma revisão nesta máquina.

Existe porque a latência da implantação não pode ser estimada: ela depende do
processador, da quantização e do tamanho do arquivo revisado. O número que este
script produz é o que se declara no documento — e o que decide se a configuração
serve.

Uso:
    venv/bin/python scripts/medir_latencia.py
    venv/bin/python scripts/medir_latencia.py --repeticoes 5
"""

import argparse
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

import requests  # noqa: E402

import config  # noqa: E402
from app.adapters.qdrant_adapter import QdrantAdapter  # noqa: E402
from app.core.models import ArquivoAlterado, ConsultaDeRegras  # noqa: E402
from app.services.ast_service import (  # noqa: E402
    elementos_alterados,
    identificar_linguagem,
)
from app.services.diff_service import linhas_alteradas  # noqa: E402
from app.services.prompt_service import montar_prompt  # noqa: E402
from app.services.sdd_service import carregar_sdd  # noqa: E402

# Dois tamanhos, porque a latência não escala igual nas duas fases: o prompt
# cresce com o arquivo, a resposta não.
PEQUENO = '''import requests


def avisar_equipe(mensagem: str) -> None:
    # Literal com cara de credencial, de propósito: é o que a SEG-001 procura.
    # Sem prefixo de provedor real — detectores de segredo não distinguem
    # exemplo de vazamento, e com razão.
    token = "exemplo-nao-funcional-0a1b2c3d4e5f"
    try:
        requests.post(
            "https://hooks.slack.com/services/T000/B000",
            headers={"Authorization": f"Bearer {token}"},
            json={"text": mensagem},
            timeout=10,
        )
    except Exception:
        pass
'''

GRANDE = PEQUENO + "\n\n" + "\n\n".join(
    f'''def processar_lote_{i}(itens: list, deposito) -> dict:
    """Processa um lote de itens e devolve o resumo da operação."""
    resultados = []
    for item in itens:
        registro = deposito.carregar(item["id"])
        registro.atualizar(item["dados"])
        deposito.salvar(registro)
        resultados.append(registro.identificador)
    return {{"processados": len(resultados), "ids": resultados}}'''
    for i in range(12)
)


def montar_diff(codigo: str) -> str:
    linhas = codigo.splitlines()
    return "\n".join(
        [f"@@ -0,0 +1,{len(linhas)} @@"] + [f"+{linha}" for linha in linhas]
    )


def preparar(conhecimento, codigo: str):
    """Devolve uma função que monta um prompt NOVO a cada chamada.

    Reusar o mesmo prompt mediria errado: o executor guarda o prefill em cache
    e a segunda medição sairia quase instantânea. Em serviço isso nunca
    acontece — a defesa contra injeção sorteia uma marca a cada chamada, então
    o prompt nunca se repete e o prefill é sempre pago por inteiro.
    """
    arquivo = ArquivoAlterado(
        "scripts/exemplo.py", montar_diff(codigo), codigo
    )
    elementos = elementos_alterados(
        arquivo.conteudo, linhas_alteradas(arquivo.diff)
    )
    regras = conhecimento.buscar_regras_relevantes(
        ConsultaDeRegras(
            texto=f"Alterações no arquivo {arquivo.caminho}. Elementos "
            "modificados: " + "; ".join(e.assinatura for e in elementos),
            caminho=arquivo.caminho,
            linguagem=identificar_linguagem(arquivo.caminho) or "",
        )
    )
    return lambda: montar_prompt(arquivo, elementos, regras)


def medir(montar, repeticoes: int) -> None:
    endereco = config.LLM_URL.replace("/v1/chat/completions", "/api/chat")
    amostras = []

    for i in range(1, repeticoes + 1):
        prompt = montar()
        inicio = time.time()
        dados = requests.post(
            endereco,
            json={
                "model": config.LLM_MODELO,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0},
            },
            timeout=3600,
        ).json()
        total = time.time() - inicio

        entrada = dados.get("prompt_eval_count", 0)
        saida = dados.get("eval_count", 0)
        t_entrada = dados.get("prompt_eval_duration", 0) / 1e9
        t_saida = dados.get("eval_duration", 0) / 1e9
        amostras.append(total)

        print(
            f"    {i}/{repeticoes}: {total:6.1f} s "
            f"| prompt {entrada:5} tok em {t_entrada:6.1f} s "
            f"({entrada / t_entrada if t_entrada else 0:6.1f} tok/s) "
            f"| gerou {saida:4} tok em {t_saida:6.1f} s "
            f"({saida / t_saida if t_saida else 0:5.1f} tok/s)",
            flush=True,
        )

    # A primeira execução carrega o modelo e não representa o regime normal.
    uteis = amostras[1:] if len(amostras) > 1 else amostras
    media = sum(uteis) / len(uteis)
    print(f"    media (sem a primeira): {media:.1f} s\n")


def principal() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeticoes", type=int, default=3)
    argumentos = parser.parse_args()

    conhecimento = QdrantAdapter()
    try:
        regras = [
            r for r in carregar_sdd(os.path.join(RAIZ, "sdd"))
            if r.escopo == "arquivo"
        ]
        conhecimento.sincronizar_regras("", regras)
        print(f"Modelo: {config.LLM_MODELO}  em  {config.LLM_URL}")
        print(f"Regras ativas: {len(regras)}\n")

        for rotulo, codigo in (("ARQUIVO PEQUENO", PEQUENO),
                               ("ARQUIVO GRANDE", GRANDE)):
            montar = preparar(conhecimento, codigo)
            print(f"  {rotulo} — prompt de {len(montar())} caracteres")
            medir(montar, argumentos.repeticoes)
    finally:
        conhecimento.fechar()

    print(
        "A primeira execução inclui o carregamento do modelo. Em serviço, isso "
        "acontece uma vez;\ndepois o modelo permanece em memória enquanto houver "
        "uso."
    )


if __name__ == "__main__":
    principal()
