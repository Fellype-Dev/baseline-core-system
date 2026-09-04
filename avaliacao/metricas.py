

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoDeCaso:

    nome: str
    esperadas: frozenset[str]
    detectadas: frozenset[str]
    erro: str | None = None

    @property
    def avaliado(self) -> bool:
        return self.erro is None

    @property
    def verdadeiros_positivos(self) -> frozenset[str]:
        return self.esperadas & self.detectadas

    @property
    def falsos_positivos(self) -> frozenset[str]:
        return self.detectadas - self.esperadas

    @property
    def falsos_negativos(self) -> frozenset[str]:
        return self.esperadas - self.detectadas

    @property
    def em_conformidade(self) -> bool:
        return not self.esperadas

    @property
    def acertou(self) -> bool:
        return self.esperadas == self.detectadas


@dataclass(frozen=True)
class Metricas:

    casos: int
    casos_exatos: int
    verdadeiros_positivos: int
    falsos_positivos: int
    falsos_negativos: int
    casos_em_conformidade: int
    casos_em_conformidade_com_alarme: int
    casos_nao_avaliados: int = 0

    @property
    def precisao(self) -> float:

        apontamentos = self.verdadeiros_positivos + self.falsos_positivos
        if apontamentos == 0:
            return 1.0
        return self.verdadeiros_positivos / apontamentos

    @property
    def revocacao(self) -> float:

        reais = self.verdadeiros_positivos + self.falsos_negativos
        if reais == 0:
            return 1.0
        return self.verdadeiros_positivos / reais

    @property
    def f1(self) -> float:
        if self.precisao + self.revocacao == 0:
            return 0.0
        return 2 * self.precisao * self.revocacao / (self.precisao + self.revocacao)

    @property
    def taxa_de_alarme_falso(self) -> float:

        if self.casos_em_conformidade == 0:
            return 0.0
        return self.casos_em_conformidade_com_alarme / self.casos_em_conformidade

    @property
    def acuracia_por_caso(self) -> float:
        if self.casos == 0:
            return 0.0
        return self.casos_exatos / self.casos


def calcular(resultados: list[ResultadoDeCaso]) -> Metricas:

    avaliados = [r for r in resultados if r.avaliado]
    em_conformidade = [r for r in avaliados if r.em_conformidade]

    return Metricas(
        casos=len(avaliados),
        casos_exatos=sum(1 for r in avaliados if r.acertou),
        verdadeiros_positivos=sum(len(r.verdadeiros_positivos) for r in avaliados),
        falsos_positivos=sum(len(r.falsos_positivos) for r in avaliados),
        falsos_negativos=sum(len(r.falsos_negativos) for r in avaliados),
        casos_em_conformidade=len(em_conformidade),
        casos_em_conformidade_com_alarme=sum(
            1 for r in em_conformidade if r.detectadas
        ),
        casos_nao_avaliados=sum(1 for r in resultados if not r.avaliado),
    )


def formatar_relatorio(resultados: list[ResultadoDeCaso], metricas: Metricas) -> str:
    linhas = ["=" * 72, "RESULTADO POR CASO", "=" * 72]

    for resultado in resultados:
        if not resultado.avaliado:
            linhas.append(f"[PULOU] {resultado.nome}")
            linhas.append(f"         nao avaliado: {resultado.erro}")
            continue

        marca = "OK  " if resultado.acertou else "FALHA"
        linhas.append(f"[{marca}] {resultado.nome}")
        linhas.append(f"         esperado : {_conjunto(resultado.esperadas)}")
        linhas.append(f"         detectado: {_conjunto(resultado.detectadas)}")
        if resultado.falsos_positivos:
            linhas.append(
                f"         (+) falso positivo: {_conjunto(resultado.falsos_positivos)}"
            )
        if resultado.falsos_negativos:
            linhas.append(
                f"         (-) nao detectado : {_conjunto(resultado.falsos_negativos)}"
            )

    linhas += ["", "=" * 72, "MÉTRICAS AGREGADAS", "=" * 72]
    linhas.append(f"Casos avaliados............: {metricas.casos}")
    if metricas.casos_nao_avaliados:
        linhas.append(
            f"Casos NAO avaliados........: {metricas.casos_nao_avaliados} "
            "(excluidos das metricas)"
        )
    linhas.append(
        f"Casos exatos...............: {metricas.casos_exatos} "
        f"({metricas.acuracia_por_caso:.1%})"
    )
    linhas.append(f"Verdadeiros positivos......: {metricas.verdadeiros_positivos}")
    linhas.append(f"Falsos positivos...........: {metricas.falsos_positivos}")
    linhas.append(f"Falsos negativos...........: {metricas.falsos_negativos}")
    linhas.append(f"Precisão...................: {metricas.precisao:.1%}")
    linhas.append(f"Revocação..................: {metricas.revocacao:.1%}")
    linhas.append(f"F1.........................: {metricas.f1:.1%}")
    linhas.append(
        f"Alarme falso em código correto: "
        f"{metricas.casos_em_conformidade_com_alarme}/"
        f"{metricas.casos_em_conformidade} ({metricas.taxa_de_alarme_falso:.1%})"
    )
    return "\n".join(linhas)


def _conjunto(identificadores: frozenset[str]) -> str:
    return ", ".join(sorted(identificadores)) if identificadores else "(nenhuma)"
