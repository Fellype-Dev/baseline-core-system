"""
Adaptador de modelo de linguagem sobre HTTP, no protocolo da OpenAI.

Serve tanto um executor na própria máquina (Ollama, LM Studio) quanto um
provedor que hospeda modelos abertos. Protocolo é o mesmo; o que muda é o
endereço e, quando há cobrança, uma credencial.

Essa indiferença é deliberada. ONDE o modelo roda é decisão de implantação, não
de projeto: em um laboratório sem placa de vídeo, aluga-se a inferência; onde o
código revisado não pode sair da infraestrutura, roda-se na própria máquina. O
núcleo recebe uma `LLMPort` e não percebe a diferença.
"""

import requests

from app.core.ports import LLMPort

URL_PADRAO = "http://localhost:11434/v1/chat/completions"
MODELO_PADRAO = "marvin"
TEMPO_LIMITE_EM_SEGUNDOS = 600


class ErroDoModelo(Exception):
    """Falha ao consultar o modelo (fora do ar, ausente, credencial recusada)."""


class LLMHttpAdapter(LLMPort):

    def __init__(
        self,
        modelo: str = MODELO_PADRAO,
        url: str = URL_PADRAO,
        tempo_limite: int = TEMPO_LIMITE_EM_SEGUNDOS,
        chave: str | None = None,
    ) -> None:

        self._modelo = modelo
        self._url = url
        self._tempo_limite = tempo_limite
        self._chave = chave

    @property
    def _cabecalhos(self) -> dict[str, str]:
        """Credencial só existe quando o modelo é hospedado por terceiro.

        Um executor local não pede autenticação, e mandar um cabeçalho vazio
        faria alguns deles recusarem a requisição.
        """
        if not self._chave:
            return {}
        return {"Authorization": f"Bearer {self._chave}"}

    def avaliar(self, prompt: str) -> str:
        try:
            resposta = requests.post(
                self._url,
                headers=self._cabecalhos,
                json={
                    "model": self._modelo,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "stream": False,
                },
                timeout=self._tempo_limite,
            )
            resposta.raise_for_status()
            dados = resposta.json()
        except requests.RequestException as erro:
            raise ErroDoModelo(
                f"não foi possível consultar o modelo em {self._url}: {erro}"
            ) from erro

        try:
            escolha = dados["choices"][0]
            conteudo = escolha["message"].get("content") or ""
        except (KeyError, IndexError) as erro:
            raise ErroDoModelo(
                f"resposta em formato inesperado do modelo: {dados}"
            ) from erro

        # As duas checagens abaixo existem porque a falha que elas pegam já
        # aconteceu, e passou despercebida: o executor trunca o prompt quando
        # ele excede a janela de contexto configurada, sem avisar. A resposta
        # volta vazia — ou, pior, coerente mas apoiada em metade do código.
        if escolha.get("finish_reason") == "length":
            raise ErroDoModelo(
                f"a resposta do modelo '{self._modelo}' foi cortada por limite "
                "de contexto. Num executor local, amplie a janela (veja o "
                "Modelfile do projeto); num provedor, confira o limite do plano."
            )

        if not conteudo.strip():
            raise ErroDoModelo(
                f"o modelo '{self._modelo}' devolveu resposta vazia. Costuma "
                "indicar prompt truncado pela janela de contexto."
            )

        return conteudo
