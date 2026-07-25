"""
Adaptador de LLM local: implementa a LLMPort com um modelo aberto na máquina.

É o adaptador que cumpre a proposta do trabalho — o motor de verificação sendo um
modelo de linguagem Open Source, sem depender de serviço de terceiros. Substitui
o GeminiAdapter, que serviu de andaime durante a construção.

Conversa pelo protocolo de "chat completions" compatível com a API da OpenAI, que
é o denominador comum dos executores locais (Ollama, LM Studio, vLLM). Por isso o
adaptador é agnóstico ao executor: trocar Ollama por LM Studio é mudar a URL, não
o código.

Duas escolhas deliberadas:

* `temperature=0` — a avaliação empírica do trabalho mede precisão e falsos
  positivos. Com temperatura alta, duas rodadas do mesmo corpus dariam números
  diferentes e a medição não seria reproduzível.
* tempo limite generoso — na primeira chamada o executor ainda está carregando
  os pesos do modelo na memória da placa de vídeo, o que leva dezenas de
  segundos. Um tempo limite curto transformaria isso em falha.

Assim como os demais adaptadores, este é BURRO: recebe o prompt pronto do núcleo
e devolve texto. Quem decide o que perguntar continua sendo o núcleo.
"""

import requests

from app.core.ports import LLMPort

URL_PADRAO = "http://localhost:11434/v1/chat/completions"
MODELO_PADRAO = "qwen2.5-coder:14b"
TEMPO_LIMITE_EM_SEGUNDOS = 600


class ErroDoModeloLocal(Exception):
    """Falha ao consultar o modelo local (executor fora do ar, modelo ausente)."""


class LocalLLMAdapter(LLMPort):
    """Fala com um modelo aberto servido localmente para cumprir a LLMPort."""

    def __init__(
        self,
        modelo: str = MODELO_PADRAO,
        url: str = URL_PADRAO,
        tempo_limite: int = TEMPO_LIMITE_EM_SEGUNDOS,
    ) -> None:
        # Nenhuma chamada de rede acontece aqui: só a configuração do cliente,
        # espelhando o comportamento dos outros adaptadores.
        self._modelo = modelo
        self._url = url
        self._tempo_limite = tempo_limite

    def avaliar(self, prompt: str) -> str:
        """Envia o prompt ao modelo local e devolve a resposta em texto puro."""
        try:
            resposta = requests.post(
                self._url,
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
            raise ErroDoModeloLocal(
                f"não foi possível consultar o modelo local em {self._url}: {erro}"
            ) from erro

        try:
            return dados["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as erro:
            raise ErroDoModeloLocal(
                f"resposta em formato inesperado do modelo local: {dados}"
            ) from erro
