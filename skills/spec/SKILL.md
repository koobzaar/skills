---
name: spec
description: Escreva um spec ou plano técnico antes de implementar. Use para transformar notas ou decisões em specs/ com risco e critérios de aceite verificáveis.
argument-hint: "[pedido, caminho da nota ou contexto da conversa]"
---

# Escrever um spec

O spec é o contrato do resto do fluxo: `implement` o executa e `review` julga o diff contra ele. Um requisito que existe só em texto vira chute do modelo, então todo requisito obrigatório vira uma checagem executável.

## 1. Confirmar as entradas

- Use a nota, o arquivo ou a conversa apontada pelo usuário. Sem argumento, use o pedido atual e o contexto relevante da conversa. Se faltar o objetivo da mudança ou o consumidor afetado, faça uma pergunta específica antes de fechar o spec.
- Leia o `AGENTS.md` aplicável e avise se o repositório não tiver esse arquivo. Localize a transformação atual, as checagens existentes e quem consome a saída. Para uma leitura extensa, dê ao `explorer` uma pergunta verificável, como “onde a receita é arredondada e quem consome essa saída?”. Confira os arquivos citados antes de usar o resultado. Se a exploração delegada estiver indisponível, leia diretamente os caminhos necessários.

## 2. Escrever o contrato

Escreva `specs/<slug>.md` na raiz do repositório, contendo:

- **Risco**: baixo, médio ou alto, com uma linha sobre o que quebra se der errado. Tocar produção, um número usado para decidir ou dado irrecuperável: alto.
- **Objetivo** e **Fora do escopo**.
- **Decisões**, cada uma com seu motivo.
- **Critérios de aceite**: cada um com a checagem que o prova (um comando, um teste, um script ou um número esperado sobre uma amostra conhecida). Critério sem checagem volta para o usuário. Escolha a checagem pelo tipo de mudança, porque cada uma pega um erro diferente:
  - Muda um cálculo existente: teste diferencial, saída antiga contra nova na mesma amostra, com a lista de diferenças esperadas e das que devem ser ignoradas (ordem de linhas, arredondamento).
  - Cria uma transformação: invariantes que valem para qualquer entrada (total preservado, sem chave duplicada, idempotência), com Hypothesis quando o repositório já o utiliza.
  - Risco alto: também uma execução ponta a ponta numa amostra, checando a tabela ou métrica usada pelo consumidor.

  A amostra é sintética ou anonimizada e versionada no repositório (`tests/fixtures/`), porque dados de clientes nunca vão para o Git e ninguém consegue repetir uma checagem que só roda na sua máquina. Escreva no critério o número esperado nessa amostra e de onde ele veio (conta feita à mão numa amostra pequena, consulta de referência), nunca da própria implementação, pois assim um número errado vira o esperado. Inclua um caso que falharia com o erro que a mudança quer evitar.
- **Passos**, cada um pequeno o bastante para ser validado sozinho.
- **Pontos abertos**.

Use Markdown comum, sem sintaxe de Obsidian (sem `[[links]]`, callouts ou frontmatter de vault), porque agentes e pessoas leem o arquivo fora do vault. O spec declara apenas o que vale hoje: histórico de decisões vai na conversa ou no commit, não no arquivo.

## 3. Revisar e pedir aprovação

Antes de mostrar o spec, rode `/review spec specs/<slug>.md` quando o risco for médio ou alto. Em risco baixo, rode a revisão se houver dúvida sobre a abordagem. Se o revisor apontar um consumidor de produção que faltou na análise, atualize o risco e inclua a checagem ponta a ponta. Se a revisão exigida estiver indisponível, entregue o spec como rascunho e indique que a revisão está pendente.

Mostre o caminho do spec, o parecer do revisor e os pontos que dependem de decisão do usuário. Se faltar uma checagem, diga qual critério ficou sem prova e peça o insumo necessário, como a amostra ou a origem do valor esperado. Depois do ok, aplique os ajustes acordados e apresente novamente o spec para aprovação se eles mudarem o objetivo ou o aceite. O spec aprovado é o contrato que `implement` registra em um commit.

## Exemplos de uso

```text
/spec Escreva um plano para descontar estornos da receita mensal.
```

Entregue `specs/receita-liquida.md`. Um trecho de aceite para esse pedido:

```markdown
## Aceite

- Receita líquida de R$ 80 na amostra `tests/fixtures/receita_estorno.csv`,
  com uma venda de R$ 100 e um estorno de R$ 20. Esperado calculado pela subtração.
- Checagem a implementar em `tests/test_receita.py`: compare a saída com R$ 80.
  A versão que ignora o estorno retorna R$ 100 e deve falhar.
```

Se a amostra ou o teste forem novos, identifique-os como artefatos a produzir em `implement`. Cite o consumidor no risco e mostre o parecer do revisor junto com o caminho do spec.

| Pedido | Resultado esperado |
| --- | --- |
| “Transforme estas notas em um plano para trocar o arredondamento da receita do comitê.” | Classifique como risco alto, especifique o teste diferencial com valores no limite do arredondamento e peça revisão antes de apresentar o spec. |
| “Use `notas/deduplicacao.md` para escrever o spec do novo join.” | Documente a cardinalidade esperada e confira a preservação de linhas numa amostra com uma chave duplicada. |
| “Coloca no papel o que decidimos sobre o filtro de pedidos ativos.” | Use as decisões da conversa e exija uma checagem que verifique tanto o total líquido quanto a contagem de descartes. |
| “Escreva um spec para corrigir este número.” | Se o consumidor ou a fonte do esperado forem desconhecidos, pergunte pelo insumo específico e identifique o critério pendente. |
| “Execute o plano em `specs/filtro-ativos.md`.” | Use `implement`. |
| “Confira se o plano de deduplicação é válido.” | Use `review spec`. |
| “Fecha a mudança já aprovada e arquiva o spec.” | Use `close-spec`. |
