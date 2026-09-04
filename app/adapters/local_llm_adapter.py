

import requests

from app.core.ports import LLMPort

URL_PADRAO = "http://localhost:11434/v1/chat/completions"
MODELO_PADRAO = "qwen2.5-coder:14b"
TEMPO_LIMITE_EM_SEGUNDOS = 600


class ErroDoModeloLocal(Exception):
    """Falha ao consultar o modelo local (executor fora do ar, modelo ausente)."""
class LocalLLMAdapter(LLMPort):

    def __init__(
        self,
        modelo: str = MODELO_PADRAO,
        url: str = URL_PADRAO,
        tempo_limite: int = TEMPO_LIMITE_EM_SEGUNDOS,
    ) -> None:

        self._modelo = modelo
        self._url = url
        self._tempo_limite = tempo_limite

    def avaliar(self, prompt: str) -> str:
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
