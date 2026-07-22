"""
Adaptador do Gemini: implementa a LLMPort usando a API do Google Gemini.

Adaptador de SAÍDA e propositalmente BURRO: recebe um texto (o prompt já montado
pelo núcleo) e devolve um texto (a resposta do modelo). Ele não sabe o que há no
prompt nem o que fazer com a resposta — essa inteligência é do núcleo. É o que a
`LLMPort` promete: "mandar texto, receber texto".

Essa modéstia é a razão de a troca de modelo ser barata: substituir o Gemini por
um modelo open source local (plano do TCC para o fim do projeto) será escrever um
novo adaptador com estas mesmas duas linhas úteis, sem tocar no núcleo.

Nota (jul/2026): o pacote `google-generativeai` foi descontinuado pelo Google em
favor de `google-genai`. Como o Gemini é apenas o andaime durante a construção e
está isolado atrás da porta, seguimos com ele por ora — a descontinuação é, na
prática, mais um motivo para a migração já planejada.
"""

import google.generativeai as genai

from app.core.ports import LLMPort


class GeminiAdapter(LLMPort):
    """Fala com a API do Gemini para cumprir o contrato LLMPort."""

    def __init__(self, api_key: str, modelo: str) -> None:
        # Nenhuma chamada de rede acontece aqui: `configure` só guarda a chave e
        # `GenerativeModel` apenas prepara o cliente. A rede só é tocada em
        # `avaliar`. Isso permite testar a construção com uma chave falsa.
        genai.configure(api_key=api_key)
        self._modelo = genai.GenerativeModel(modelo)

    def avaliar(self, prompt: str) -> str:
        """Envia o prompt ao Gemini e devolve a resposta em texto puro.

        Tratamento de falhas (timeout, bloqueio por filtro de segurança, resposta
        vazia) fica para o Conjunto E (resiliência), onde o pipeline inteiro é
        endurecido. Aqui o adaptador permanece fino de propósito.
        """
        resposta = self._modelo.generate_content(prompt)
        return resposta.text
