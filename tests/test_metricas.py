"""Testes das métricas de avaliação (lógica pura, sem modelo nem rede)."""

from avaliacao.metricas import ResultadoDeCaso, calcular


def caso(nome, esperadas, detectadas):
    return ResultadoDeCaso(
        nome=nome, esperadas=frozenset(esperadas), detectadas=frozenset(detectadas)
    )


# --- Classificação por caso -------------------------------------------------

def test_classifica_acertos_e_erros_de_um_caso():
    resultado = caso("x", ["SEG-001", "QUA-001"], ["SEG-001", "ARQ-001"])
    assert resultado.verdadeiros_positivos == frozenset({"SEG-001"})
    assert resultado.falsos_positivos == frozenset({"ARQ-001"})
    assert resultado.falsos_negativos == frozenset({"QUA-001"})
    assert not resultado.acertou


def test_caso_exato_quando_conjuntos_coincidem():
    assert caso("x", ["SEG-001"], ["SEG-001"]).acertou


def test_caso_em_conformidade_e_o_que_nao_espera_violacao():
    assert caso("limpo", [], []).em_conformidade
    assert not caso("sujo", ["SEG-001"], []).em_conformidade


# --- Agregação --------------------------------------------------------------

def test_deteccao_perfeita():
    metricas = calcular(
        [caso("a", ["SEG-001"], ["SEG-001"]), caso("b", [], [])]
    )
    assert metricas.precisao == 1.0
    assert metricas.revocacao == 1.0
    assert metricas.f1 == 1.0
    assert metricas.taxa_de_alarme_falso == 0.0


def test_falso_positivo_em_codigo_correto_reduz_precisao():
    # Um arquivo correto que recebeu apontamento: o erro mais grave para adoção.
    metricas = calcular(
        [caso("a", ["SEG-001"], ["SEG-001"]), caso("limpo", [], ["ARQ-001"])]
    )
    assert metricas.falsos_positivos == 1
    assert metricas.precisao == 0.5
    assert metricas.revocacao == 1.0
    assert metricas.taxa_de_alarme_falso == 1.0


def test_violacao_nao_detectada_reduz_revocacao():
    metricas = calcular(
        [caso("a", ["SEG-001", "QUA-001"], ["SEG-001"])]
    )
    assert metricas.falsos_negativos == 1
    assert metricas.revocacao == 0.5
    assert metricas.precisao == 1.0


def test_ferramenta_muda_nao_e_premiada():
    """Não apontar nada dá precisão 1.0 por convenção, mas revocação zero."""
    metricas = calcular([caso("a", ["SEG-001"], [])])
    assert metricas.precisao == 1.0
    assert metricas.revocacao == 0.0
    assert metricas.f1 == 0.0


def test_taxa_de_alarme_falso_considera_so_os_casos_limpos():
    metricas = calcular(
        [
            caso("limpo1", [], []),
            caso("limpo2", [], ["SEG-001"]),
            caso("sujo", ["SEG-001"], ["SEG-001", "ARQ-001"]),
        ]
    )
    # Dois casos limpos, um deles com alarme: 50%. O falso positivo do caso
    # "sujo" não entra nesta taxa (ela mede código correto que foi incomodado).
    assert metricas.casos_em_conformidade == 2
    assert metricas.taxa_de_alarme_falso == 0.5


def test_acuracia_por_caso():
    metricas = calcular(
        [caso("a", ["SEG-001"], ["SEG-001"]), caso("b", ["QUA-001"], [])]
    )
    assert metricas.casos_exatos == 1
    assert metricas.acuracia_por_caso == 0.5


def test_caso_nao_avaliado_fica_fora_das_metricas():
    """Cota esgotada não pode virar falso negativo — isso falsearia o resultado."""
    nao_avaliado = ResultadoDeCaso(
        nome="sem_cota",
        esperadas=frozenset({"SEG-001"}),
        detectadas=frozenset(),
        erro="ResourceExhausted: cota diaria",
    )
    metricas = calcular([caso("a", ["SEG-001"], ["SEG-001"]), nao_avaliado])

    assert metricas.casos == 1
    assert metricas.casos_nao_avaliados == 1
    assert metricas.falsos_negativos == 0
    assert metricas.revocacao == 1.0


def test_corpus_vazio_nao_quebra():
    metricas = calcular([])
    assert metricas.casos == 0
    assert metricas.acuracia_por_caso == 0.0
    assert metricas.taxa_de_alarme_falso == 0.0
