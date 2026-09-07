

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
            escolha = dados["choices"][0]
            conteudo = escolha["message"].get("content") or ""
        except (KeyError, IndexError) as erro:
            raise ErroDoModeloLocal(
                f"resposta em formato inesperado do modelo local: {dados}"
            ) from erro

        # As duas checagens abaixo existem porque a falha que elas pegam já
        # aconteceu, e passou despercebida: o executor trunca o prompt quando
        # ele excede a janela de contexto configurada, sem avisar. A resposta
        # volta vazia — ou, pior, coerente mas apoiada em metade do código.
        # Sem isto, o vazio virava "não foi possível interpretar a resposta", e
        # a causa real ficava invisível.
        if escolha.get("finish_reason") == "length":
            raise ErroDoModeloLocal(
                f"a resposta do modelo '{self._modelo}' foi cortada por limite "
                "de contexto. Aumente a janela do modelo (veja o Modelfile do "
                "projeto: `ollama create marvin -f Modelfile`)."
            )

        if not conteudo.strip():
            raise ErroDoModeloLocal(
                f"o modelo '{self._modelo}' devolveu resposta vazia. Costuma "
                "indicar prompt truncado pela janela de contexto do executor."
            )

        return conteudo
