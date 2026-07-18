"""
Script utilitário: lista os modelos do Gemini disponíveis na sua conta
que suportam geração de texto. Útil para conferir o nome exato do modelo.

Uso:  venv/Scripts/python.exe listar_modelos.py
"""

import google.generativeai as genai

import config

genai.configure(api_key=config.GEMINI_API_KEY)

print("Modelos disponíveis na sua conta para gerar texto:")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
