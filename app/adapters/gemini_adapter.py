
import google.generativeai as genai

from app.core.ports import LLMPort


class GeminiAdapter(LLMPort):

    def __init__(self, api_key: str, modelo: str) -> None:

        genai.configure(api_key=api_key)
        self._modelo = genai.GenerativeModel(modelo)

    def avaliar(self, prompt: str) -> str:

        resposta = self._modelo.generate_content(prompt)
        return resposta.text
