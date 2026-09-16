

import hashlib
import re
from dataclasses import asdict

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

from app.core.applicability import regra_se_aplica
from app.core.models import ConsultaDeRegras, RegraArquitetural
from app.core.ports import ConhecimentoPort

MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class QdrantAdapter(ConhecimentoPort):
    _FATOR_DE_SOBREBUSCA = 4

    def __init__(
        self,
        caminho_dados: str = "./dados_qdrant",
        nome_colecao: str = "regras_arquiteturais",
        modelo_embedding: str = MODELO_PADRAO,
        quantidade_de_regras: int = 3,
        indexar_exemplos: bool = False,
    ) -> None:
        self._cliente = QdrantClient(path=caminho_dados)
        self._modelo = TextEmbedding(model_name=modelo_embedding)
        self._colecao = nome_colecao

        self._quantidade = quantidade_de_regras

        self._indexar_exemplos = indexar_exemplos

        self._assinaturas: dict[str, str] = {}


    def sincronizar_regras(
        self, repositorio: str, regras: list[RegraArquitetural]
    ) -> None:

        colecao = self._colecao_de(repositorio)
        assinatura = self._assinatura(regras)

        if self._assinaturas.get(colecao) == assinatura:
            return

        self.indexar_regras(regras, colecao)
        self._assinaturas[colecao] = assinatura

    @staticmethod
    def _colecao_de(repositorio: str) -> str:
        if not repositorio:
            return "regras_arquiteturais"
        seguro = re.sub(r"[^a-zA-Z0-9]+", "_", repositorio).strip("_").lower()
        return f"regras_{seguro}"

    def _assinatura(self, regras: list[RegraArquitetural]) -> str:
        conteudo = " ".join(
            self._texto_para_busca(regra) + repr(asdict(regra))
            for regra in sorted(regras, key=lambda r: r.identificador)
        )
        return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()

    def indexar_regras(
        self, regras: list[RegraArquitetural], colecao: str | None = None
    ) -> None:
        colecao = colecao or self._colecao
        if not regras:
            return

        textos = [self._texto_para_busca(regra) for regra in regras]
        vetores = [vetor.tolist() for vetor in self._modelo.embed(textos)]

        dimensao = len(vetores[0])

        if self._cliente.collection_exists(colecao):
            self._cliente.delete_collection(colecao)
        self._cliente.create_collection(
            collection_name=colecao,
            vectors_config=models.VectorParams(
                size=dimensao,
                distance=models.Distance.COSINE,
            ),
        )

        self._cliente.upsert(
            collection_name=colecao,
            points=[
                models.PointStruct(
                    id=indice,
                    vector=vetor,
                    payload=asdict(regra),
                )
                for indice, (regra, vetor) in enumerate(zip(regras, vetores))
            ],
        )


    def buscar_regras_relevantes(
        self, consulta: ConsultaDeRegras
    ) -> list[RegraArquitetural]:

        colecao = self._colecao_de(consulta.repositorio)
        if not self._cliente.collection_exists(colecao):
            return []

        vetor_consulta = next(iter(self._modelo.embed([consulta.texto]))).tolist()


        resposta = self._cliente.query_points(
            collection_name=colecao,
            query=vetor_consulta,
            limit=self._quantidade * self._FATOR_DE_SOBREBUSCA,
        )

        aplicaveis = [
            regra
            for regra in (
                self._regra_do_payload(ponto.payload) for ponto in resposta.points
            )
            if regra_se_aplica(regra, consulta)
        ]
        return aplicaveis[: self._quantidade]

    @staticmethod
    def _regra_do_payload(payload: dict) -> RegraArquitetural:

        dados = dict(payload)
        for campo in ("linguagens", "aplica_se_a", "excecoes"):
            dados[campo] = tuple(dados.get(campo) or ())
        return RegraArquitetural(**dados)

    def descrever_colecao(self) -> dict:
        if not self._cliente.collection_exists(self._colecao):
            return {"indexada": False}

        info = self._cliente.get_collection(self._colecao)
        vetores = info.config.params.vectors
        return {
            "indexada": True,
            "colecao": self._colecao,
            "regras": info.points_count,
            "dimensoes": vetores.size,
            "metrica": vetores.distance.value,
            "regras_por_consulta": self._quantidade,
        }

    def listar_regras(self) -> list[RegraArquitetural]:
        if not self._cliente.collection_exists(self._colecao):
            return []

        pontos, _ = self._cliente.scroll(
            collection_name=self._colecao, limit=1000, with_payload=True
        )
        regras = [self._regra_do_payload(ponto.payload) for ponto in pontos]
        return sorted(regras, key=lambda regra: regra.identificador)

    def buscar_com_pontuacao(
        self, texto: str, consulta: ConsultaDeRegras | None = None
    ) -> list[tuple[RegraArquitetural, float, bool]]:

        if not self._cliente.collection_exists(self._colecao):
            return []

        vetor = next(iter(self._modelo.embed([texto]))).tolist()
        resposta = self._cliente.query_points(
            collection_name=self._colecao, query=vetor, limit=50
        )

        resultado = []
        for ponto in resposta.points:
            regra = self._regra_do_payload(ponto.payload)
            aplicavel = regra_se_aplica(regra, consulta) if consulta else True
            resultado.append((regra, ponto.score, aplicavel))
        return resultado

    def fechar(self) -> None:

        self._cliente.close()

    def _texto_para_busca(self, regra: RegraArquitetural) -> str:

        partes = [regra.titulo, regra.regra, regra.motivacao, regra.como_identificar]
        if self._indexar_exemplos:

            partes = [regra.exemplo_incorreto] + partes
        return "\n".join(parte for parte in partes if parte)
