import google.generativeai as genai

# Cole sua chave aqui
GEMINI_API_KEY = "AIzaSyCe-CoW8BUM_b-EclTGYBBGM1a68l7VtK4"
genai.configure(api_key=GEMINI_API_KEY)

print("Modelos disponíveis na sua conta para gerar texto:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)