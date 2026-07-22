"""
Adaptador do Qdrant: implementa a ConhecimentoPort com busca semântica (RAG).

Este adaptador esconde do núcleo TODA a mecânica de recuperação: geração de
embeddings, banco vetorial, métrica de similaridade. O núcleo só pede "as regras
relevantes para este código" e recebe modelos de domínio de volta.

Modo EMBARCADO: o Qdrant roda dentro do próprio processo Python, gravando em um
diretório local. Não exige servidor, container nem conta em serviço externo.
Migrar para um servidor depois significa trocar apenas a criação do QdrantClient.

Os embeddings são gerados localmente pelo fastembed (o SDD é documento interno;
não faz sentido enviá-lo a uma API externa).
"""

from dataclasses import asdict

from fastembed import TextEmbedding
from qdrant_client import QdrantClient, models

from app.core.models import RegraArquitetural
from app.core.ports import ConhecimentoPort

# Modelo multilíngue: o SDD é escrito em português, então um modelo só-inglês
# degradaria a busca semântica.
MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class QdrantAdapter(ConhecimentoPort):
    """Recupera regras do SDD por similaridade semântica usando Qdrant + embeddings."""

    def __init__(
        self,
        caminho_dados: str = "./dados_qdrant",
        nome_colecao: str = "regras_arquiteturais",
        modelo_embedding: str = MODELO_PADRAO,
        quantidade_de_regras: int = 3,
    ) -> None:
        # path=... ativa o modo embarcado (sem servidor).
        self._cliente = QdrantClient(path=caminho_dados)
        self._modelo = TextEmbedding(model_name=modelo_embedding)
        self._colecao = nome_colecao
        # Quantas regras retornar por consulta. Fica aqui (detalhe do adaptador)
        # e não na porta, que deve permanecer simples.
        self._quantidade = quantidade_de_regras

    # ------------------------------------------------------------------
    # Operação de ciclo de vida do adaptador (fora do contrato da porta):
    # indexar o SDD. Chamada por um script de setup, nunca pelo núcleo.
    # ------------------------------------------------------------------
    def indexar_regras(self, regras: list[RegraArquitetural]) -> None:
        """Gera os embeddings das regras e as armazena no Qdrant (C3 + C4)."""
        if not regras:
            return

        textos = [self._texto_para_busca(regra) for regra in regras]
        vetores = [vetor.tolist() for vetor in self._modelo.embed(textos)]

        # A dimensão vem do próprio modelo, em vez de ser fixada no código —
        # assim trocar de modelo de embedding não quebra nada aqui.
        dimensao = len(vetores[0])

        # Reindexação começa do zero: o SDD é a fonte da verdade.
        if self._cliente.collection_exists(self._colecao):
            self._cliente.delete_collection(self._colecao)
        self._cliente.create_collection(
            collection_name=self._colecao,
            vectors_config=models.VectorParams(
                size=dimensao,
                distance=models.Distance.COSINE,
            ),
        )

        self._cliente.upsert(
            collection_name=self._colecao,
            points=[
                models.PointStruct(
                    id=indice,
                    vector=vetor,
                    # O payload guarda a regra inteira, para reconstruí-la na busca.
                    payload=asdict(regra),
                )
                for indice, (regra, vetor) in enumerate(zip(regras, vetores))
            ],
        )

    # ------------------------------------------------------------------
    # Implementação do contrato ConhecimentoPort.
    # ------------------------------------------------------------------
    def buscar_regras_relevantes(self, codigo: str) -> list[RegraArquitetural]:
        """Retorna as regras do SDD semanticamente mais próximas do texto dado (C5)."""
        if not self._cliente.collection_exists(self._colecao):
            return []

        vetor_consulta = next(iter(self._modelo.embed([codigo]))).tolist()

        resposta = self._cliente.query_points(
            collection_name=self._colecao,
            query=vetor_consulta,
            limit=self._quantidade,
        )

        return [self._regra_do_payload(ponto.payload) for ponto in resposta.points]

    @staticmethod
    def _regra_do_payload(payload: dict) -> RegraArquitetural:
        """Reconstrói a regra a partir do payload armazenado.

        O Qdrant devolve as coleções como listas (formato JSON); o modelo de
        domínio usa tuplas para permanecer imutável, então convertemos de volta.
        """
        dados = dict(payload)
        for campo in ("linguagens", "aplica_se_a", "excecoes"):
            dados[campo] = tuple(dados.get(campo) or ())
        return RegraArquitetural(**dados)

    def fechar(self) -> None:
        """Libera o banco embarcado de forma explícita.

        No modo embarcado o Qdrant mantém um lock de arquivo sobre o diretório
        de dados. Fechar explicitamente evita que a liberação aconteça durante
        o desligamento do interpretador (o que produz erros ruidosos no Windows)
        e libera o diretório para outro processo.
        """
        self._cliente.close()

    @staticmethod
    def _texto_para_busca(regra: RegraArquitetural) -> str:
        """Texto que representa a regra no espaço vetorial.

        Usa apenas as partes em linguagem natural (título, enunciado, motivação
        e sinais de identificação). Os exemplos de código ficam de fora por
        enquanto: se incluí-los melhora ou piora a recuperação é uma questão
        empírica, prevista como experimento para o capítulo de Resultados.
        """
        partes = [regra.titulo, regra.regra, regra.motivacao, regra.como_identificar]
        return "\n".join(parte for parte in partes if parte)
