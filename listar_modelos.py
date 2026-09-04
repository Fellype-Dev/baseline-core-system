

import google.generativeai as genai

import config

genai.configure(api_key=config.GEMINI_API_KEY)

print("Modelos disponíveis na sua conta para gerar texto:")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
