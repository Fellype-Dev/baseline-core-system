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

from app.core.aplicabilidade import regra_se_aplica
from app.core.models import ConsultaDeRegras, RegraArquitetural
from app.core.ports import ConhecimentoPort

# Modelo multilíngue: o SDD é escrito em português, então um modelo só-inglês
# degradaria a busca semântica.
MODELO_PADRAO = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class QdrantAdapter(ConhecimentoPort):
    """Recupera regras do SDD por similaridade semântica usando Qdrant + embeddings."""

    # Quantas candidatas buscar por vaga desejada. Como o filtro de
    # aplicabilidade descarta parte dos resultados, buscar apenas a quantidade
    # final devolveria menos regras do que o pedido.
    _FATOR_DE_SOBREBUSCA = 4

    def __init__(
        self,
        caminho_dados: str = "./dados_qdrant",
        nome_colecao: str = "regras_arquiteturais",
        modelo_embedding: str = MODELO_PADRAO,
        quantidade_de_regras: int = 3,
        indexar_exemplos: bool = False,
    ) -> None:
        # path=... ativa o modo embarcado (sem servidor).
        self._cliente = QdrantClient(path=caminho_dados)
        self._modelo = TextEmbedding(model_name=modelo_embedding)
        self._colecao = nome_colecao
        # Quantas regras retornar por consulta. Fica aqui (detalhe do adaptador)
        # e não na porta, que deve permanecer simples.
        self._quantidade = quantidade_de_regras
        # Se os exemplos de código da regra entram no texto vetorizado. Ver a
        # justificativa em `_texto_para_busca`. Precisa ser o MESMO valor usado
        # na indexação: mudar isto exige reindexar o SDD.
        self._indexar_exemplos = indexar_exemplos

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
    def buscar_regras_relevantes(
        self, consulta: ConsultaDeRegras
    ) -> list[RegraArquitetural]:
        """Retorna as regras aplicáveis ao arquivo e relevantes para o código (C5).

        São duas etapas: a busca semântica traz as candidatas mais próximas, e o
        filtro de aplicabilidade descarta as que não valem para aquele arquivo
        (outra linguagem ou fora do escopo de caminho declarado no SDD).
        """
        if not self._cliente.collection_exists(self._colecao):
            return []

        vetor_consulta = next(iter(self._modelo.embed([consulta.texto]))).tolist()

        # Busca mais candidatas do que o necessário, porque parte delas será
        # descartada pelo filtro de aplicabilidade logo abaixo.
        resposta = self._cliente.query_points(
            collection_name=self._colecao,
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
        """Reconstrói a regra a partir do payload armazenado.

        O Qdrant devolve as coleções como listas (formato JSON); o modelo de
        domínio usa tuplas para permanecer imutável, então convertemos de volta.
        """
        dados = dict(payload)
        for campo in ("linguagens", "aplica_se_a", "excecoes"):
            dados[campo] = tuple(dados.get(campo) or ())
        return RegraArquitetural(**dados)

    # ------------------------------------------------------------------
    # Inspeção do índice (fora do contrato da porta).
    #
    # O núcleo nunca precisa saber o que está armazenado nem com que pontuação
    # — ele só pede as regras relevantes. Estas operações existem para tornar o
    # índice observável de fora: sem elas, a etapa de recuperação seria uma
    # caixa-preta, impossível de demonstrar ou de auditar.
    # ------------------------------------------------------------------

    def descrever_colecao(self) -> dict:
        """Resume o estado do índice: quantas regras, dimensão e métrica."""
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
        """Devolve todas as regras armazenadas, ordenadas por identificador."""
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
        """Busca semântica exposta com as pontuações, para inspeção.

        Devolve todas as candidatas com a similaridade obtida e se cada uma seria
        aceita pelo filtro de aplicabilidade. Diferente de
        `buscar_regras_relevantes`, nada é descartado: o objetivo aqui é mostrar
        POR QUE uma regra entrou ou ficou de fora, e não entregar um resultado
        pronto ao núcleo.
        """
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
        """Libera o banco embarcado de forma explícita.

        No modo embarcado o Qdrant mantém um lock de arquivo sobre o diretório
        de dados. Fechar explicitamente evita que a liberação aconteça durante
        o desligamento do interpretador (o que produz erros ruidosos no Windows)
        e libera o diretório para outro processo.
        """
        self._cliente.close()

    def _texto_para_busca(self, regra: RegraArquitetural) -> str:
        """Texto que representa a regra no espaço vetorial.

        A base é a linguagem natural da regra (título, enunciado, motivação e
        sinais de identificação). Quando `indexar_exemplos` está ligado, os
        exemplos de código entram ANTES da prosa — e a ordem é o ponto central.

        Duas razões, ambas medidas:

        1. A consulta que chega aqui é derivada do código (assinaturas extraídas
           da AST), enquanto a regra é prosa em português. São modalidades
           diferentes de texto, e a distância entre elas domina a similaridade.
           Os exemplos de código da regra são o único trecho escrito na mesma
           modalidade da consulta, e é isso que os torna úteis para a busca.

        2. O modelo de embedding TRUNCA a entrada em torno de 128 tokens
           (~600 caracteres em português), apesar de a descrição da biblioteca
           anunciar 512. Como a prosa de uma regra já ocupa essa janela
           inteira, exemplos acrescentados ao FIM são descartados em silêncio:
           o vetor resultante fica idêntico ao de antes. Colocá-los no início é
           o que garante que sobrevivam ao corte.
        """
        partes = [regra.titulo, regra.regra, regra.motivacao, regra.como_identificar]
        if self._indexar_exemplos:
            # Apenas o exemplo INCORRETO. Indexar também o exemplo correto
            # aproxima a regra do código que já está em conformidade: ela passa
            # a ser recuperada exatamente onde não deveria ser cobrada, e o
            # apontamento indevido vira falso positivo. Medido: incluir os dois
            # exemplos levou a revocação a 100%, mas derrubou a precisão.
            partes = [regra.exemplo_incorreto] + partes
        return "\n".join(parte for parte in partes if parte)
