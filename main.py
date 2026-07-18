"""
Servidor principal da ferramenta de revisão arquitetural de Pull Requests.

Fluxo atual (protótipo inicial):
  1. Recebe o webhook do GitHub quando um PR é aberto.
  2. Busca os arquivos alterados no PR.
  3. Envia o diff para o Gemini avaliar segundo uma regra da empresa.
  4. Publica o feedback como comentário no próprio PR.

Nas próximas etapas serão adicionados: sanitização com AST e recuperação
de regras via RAG/Qdrant a partir do documento SDD.
"""

from fastapi import FastAPI, Request
import uvicorn
from github import Github
import google.generativeai as genai

import config

# Falha cedo, com mensagem clara, se as chaves não estiverem no .env.
config.validar_configuracao()

app = FastAPI()

genai.configure(api_key=config.GEMINI_API_KEY)
modelo_ia = genai.GenerativeModel(config.GEMINI_MODEL)


@app.post("/webhook")
async def receber_evento_github(request: Request):
    payload = await request.json()

    # Só reage quando um Pull Request é aberto.
    if payload.get("action") == "opened" and "pull_request" in payload:
        nome_repo = payload["repository"]["full_name"]
        numero_pr = payload["pull_request"]["number"]

        print("\n" + "=" * 50)
        print(f"EVENTO RECEBIDO: PR #{numero_pr} em {nome_repo}")
        print("Buscando código e enviando para o Gemini analisar...\n")

        try:
            g = Github(config.GITHUB_TOKEN)
            repo = g.get_repo(nome_repo)
            pr = repo.get_pull(numero_pr)
            arquivos_alterados = pr.get_files()

            regra_da_empresa = (
                "Nunca coloque anos fixos (ex: 2024, 2025) em títulos ou "
                "documentações. Use sempre termos atemporais."
            )

            for arquivo in arquivos_alterados:
                diff_do_codigo = arquivo.patch

                prompt = f"""
                Você é um Arquiteto de Software Sênior revisando um Pull Request.
                Avalie o código abaixo seguindo ESTRITAMENTE esta regra da nossa empresa:
                Regra: {regra_da_empresa}

                Aqui está o código alterado (Diff):
                {diff_do_codigo}

                Houve alguma violação da regra? Responda de forma curta, amigável mas firme, como se estivesse comentando na PR do GitHub.
                E EVITE O USO DE EMOJIS!
                """

                resposta_ia = modelo_ia.generate_content(prompt)

                print(f"Arquivo: {arquivo.filename}")
                print("-" * 40)
                print(resposta_ia.text)
                print("-" * 40 + "\n")

                print("Enviando comentário para o GitHub...")
                pr.create_issue_comment(resposta_ia.text)
                print("Comentário publicado com sucesso no PR!")

        except Exception as e:
            print(f"Erro na integração: {e}")

    return {"status": "sucesso"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
