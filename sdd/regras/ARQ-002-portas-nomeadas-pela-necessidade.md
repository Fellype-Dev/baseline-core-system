---
id: ARQ-002
titulo: Portas devem ser nomeadas pela necessidade, não pela tecnologia
categoria: arquitetura
severidade: obrigatoria
status: ativa
linguagens: [python]
aplica_se_a:
  - "app/core/**"
excecoes: []
---

## Regra

O nome de uma porta e a assinatura de seus métodos devem descrever a necessidade
do domínio que ela atende, e nunca a tecnologia que a implementa.

## Motivação

Quando o nome da porta carrega a tecnologia, o detalhe de implementação vaza
para o núcleo e a substituição futura fica comprometida: trocar o banco vetorial
exigiria renomear a porta e ajustar quem a usa. Nomes orientados à necessidade
mantêm o núcleo estável mesmo quando a infraestrutura muda.

## Como identificar

Nomes de classes de porta ou de seus métodos que citem produtos, protocolos ou
bibliotecas específicas em vez do conceito de domínio.

## Exemplo incorreto

```python
class QdrantPort(ABC):
    @abstractmethod
    def buscar_por_vetor(self, embedding: list[float]) -> list[dict]: ...
```

## Exemplo correto

```python
class ConhecimentoPort(ABC):
    @abstractmethod
    def buscar_regras_relevantes(self, codigo: str) -> list[RegraArquitetural]: ...
```
