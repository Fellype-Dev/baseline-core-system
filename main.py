from fastapi import FastAPI, Request
import uvicorn
from github import Github
import google.generativeai as genai

app = FastAPI()

GITHUB_TOKEN = "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"
GEMINI_API_KEY = "AIzaSyCe-CoW8BUM_b-EclTGYBBGM1a68l7VtK4"

genai.configure(api_key=GEMINI_API_KEY)
modelo_ia = genai.GenerativeModel('gemini-2.5-flash') 

@app.post("/webhook")
async def receber_evento_github(request: Request):
    
    payload = await request.json()
    
    if "action" in payload and payload["action"] == "opened" and "pull_request" in payload:
        
        nome_repo = payload["repository"]["full_name"]
        numero_pr = payload["pull_request"]["number"]
        
        print("\n" + "="*50)
        print(f"EVENTO RECEBIDO: PR #{numero_pr} em {nome_repo}")
        print("Buscando código e enviando para o Gemini analisar...\n")
        
        try:
            g = Github(GITHUB_TOKEN)
            repo = g.get_repo(nome_repo)
            pr = repo.get_pull(numero_pr)
            arquivos_alterados = pr.get_files()
            
            regra_da_empresa = "Nunca coloque anos fixos (ex: 2024, 2025) em títulos ou documentações. Use sempre termos atemporais."
            
            for arquivo in arquivos_alterados:
                diff_do_codigo = arquivo.patch
                
                prompt = f"""
                Você é um Arquiteto de Software Sênior revisando um Pull Request.
                Avalie o código abaixo seguindo ESTRITAMENTE esta regra da nossa empresa:
                Regra: {regra_da_empresa}

                Aqui está o código alterado (Diff):
                {diff_do_codigo}

                Houve alguma violação da regra? Responda de forma curta, amigável mas firme, como se estivesse comentando na PR do GitHub.
                E EVITE O USO DE EMOGIS!
                """
                
                resposta_ia = modelo_ia.generate_content(prompt)
                
                print(f"📄 Arquivo: {arquivo.filename}")
                print("-" * 40)
                print(resposta_ia.text)
                print("-" * 40 + "\n")

                print("-" * 40)
                print(resposta_ia.text)
                print("-" * 40 + "\n")
                
                print("Enviando comentário para o GitHub...")
                comentario_formatado = f"{resposta_ia.text}"
                pr.create_issue_comment(comentario_formatado)
                print("✅ Comentário publicado com sucesso no PR!")
                
        except Exception as e:
            print(f"Erro na integração: {e}")
                
        except Exception as e:
            print(f"Erro na integração: {e}")

    return {"status": "sucesso"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)