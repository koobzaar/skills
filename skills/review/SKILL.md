---
name: review
description: Use ao pedir segunda opinião sobre um spec, revisão de um diff ou veredito de merge. O revisor independente devolve achados verificáveis.
argument-hint: "branch <spec> <worktree> <branch> <target> [SHA:caminho do spec aprovado] [rodada anterior: SHAs da branch e do alvo, e achados] | spec <caminho do spec>"
agent: reviewer
---

# Revisar um spec ou uma branch

Entradas: $ARGUMENTS

Você revisa trabalho escrito por outro modelo; você não viu nada do raciocínio dele, então julgue apenas os artefatos como estão. Seu relatório vai para o agente que corrigirá os achados e para a pessoa que decide, portanto cada achado precisa ser verificável e acionável. Não altere nenhum arquivo. Você está rodando sem interação: ninguém responderá perguntas, então explicite premissas e siga adiante.

Use o modo explícito `spec` ou `branch` quando informado. Em pedidos em linguagem natural, use o modo spec para julgar um plano antes da implementação e o modo branch para julgar uma mudança em Git. Se faltar um artefato indispensável, identifique-o no relatório e deixe a revisão inconclusiva.

| Modo | Insumos | Entrega |
| --- | --- | --- |
| `spec` | Caminho do spec e acesso ao código ou à amostra que sustenta a proposta. | Parecer sobre abordagem, critérios e risco. Se o arquivo não existir, indique o caminho consultado e peça que seja fornecido na próxima chamada. |
| `branch` | Spec, worktree, branch e alvo. A referência aprovada e os dados da rodada anterior são opcionais. | Veredito e evidências para os SHAs fixados. Se uma referência obrigatória não resolver, devolva **Não pronto** com a referência e o erro de Git. |

## Revisão de branch

### Leitura

1. Trabalhe na worktree informada nas entradas. Fixe os SHAs e use-os em todas as leituras: `B=$(git rev-parse <branch>)`, `A=$(git rev-parse <target>)`, `M=$(git merge-base $A $B)`. Um commit que chegar durante a revisão não pode mudar o que você julga. Sem merge-base, ou com `git diff $M $B` vazio, o veredito é não pronto, com o motivo.
2. Leia o spec e as regras versionadas no repositório no caminho de cada arquivo alterado (`AGENTS.md`, `CLAUDE.md` e qualquer `REVIEW.md` citado pelo `AGENTS.md`), na versão da branch alvo (`git show $A:<caminho>`), porque uma mudança não pode afrouxar as regras que a julgam. Regra nova é bem-vinda; afrouxar ou remover regra existente na alvo, quando isso não for o objetivo do spec, é bloqueio. Aplique as regras de revisão desses arquivos: o que bloqueia merge, quais caminhos são sensíveis (risco alto) e quais são gerados e dispensam leitura linha a linha.
3. Em rodada posterior, use `git diff <branch-anterior> $B` se o SHA anterior da branch for ancestral de `B`, o SHA anterior do alvo for igual a `A` e você tiver os achados da rodada. Leia o contexto tocado por cada correção e confirme que ela remove a causa. Nos demais casos, leia `git diff $M $B` inteiro. Quando houver achados anteriores, preserve as decisões ainda válidas e reabra o que persistir ou cujo motivo deixou de valer.
4. Julgue a partir desses artefatos, nunca de um relato do trabalho.

### Verificação

- **Risco.** O risco do spec é o piso. Suba para alto quando o diff tocar produção (tabela, arquivo FTP, job), número usado para decidir, dado irrecuperável ou caminho marcado como sensível nas regras, e diga isso explicitamente. Tabela ou arquivo de teste não eleva o risco.
- **Critérios de aceite.** Compare os critérios do spec com a versão aprovada: o `SHA:caminho` nas entradas; sem ele, a versão na alvo; se o spec nasceu na branch, o commit que o criou. Use `git diff <ref> $B -- <spec>`. Critério afrouxado ou removido, ou checagem que deixou de provar o que o critério exige, é bloqueio até aprovação do usuário. Teste reescrito mantendo a mesma força é aceitável; perder a prova não é.
- **Execução.** Em risco médio ou alto, ou quando o diff alterar teste ou checagem, execute as checagens dos critérios em `B`. Em risco baixo, execute apenas para provar um achado. Antes de rodar na worktree, confirme que o HEAD é `B` e que alterações locais ou arquivos não versionados não interferem. Se a worktree não representar `B`, ou se mudar durante a checagem, marque o critério como não verificado e informe o motivo. Confirme também que entradas e saídas são dados de teste e que nada grava no checkout nem em produção (use `python -B`, direcione saídas para pasta temporária e encerre qualquer processo iniciado). Se não puder confirmar isso, não execute e marque o critério como não verificado.
- **Gatilhos de dados.** Verifique apenas os que o diff realmente tocar:
  - join ou lookup novo ou alterado: cardinalidade esperada (1:1, 1:N), contagem de linhas antes e depois, e chaves sem correspondência;
  - filtro, linha descartada, preenchimento de nulo ou `except` que continua: quantos casos ocorrem e onde essa contagem é reportada;
  - agregação ou total novo: bate com um segundo caminho independente para o mesmo número;
  - mudança em cálculo existente: antes e depois sobre uma amostra conhecida.

### Achados

Levante apenas o que o autor corrigiria antes do merge: bug real ou regra quebrada. Deixe de fora estilo, nomes, formatação, docstrings e limpeza cosmética, porque cada achado menor custa uma rodada e esconde o que importa. Seja exaustivo no diff e nas checagens de aceite; em risco baixo mantenha a revisão curta.

Prove cada achado com uma falha concreta: entrada, estado e resultado errado, com arquivo e linha, citando a linha. Em código numérico, um número errado num caso pequeno é prova. Descarte achado que não consiga concretizar, falha improvável em uso real e falha segura (que para, recusa ou avisa sem perder nada). Quando o mesmo erro aparecer em vários lugares, reporte a classe de bug e todas as ocorrências como um único achado.

Classifique cada achado pela relação com o spec. Você não decide quando será corrigido.

- **Bloqueio.** A mudança está errada, não entrega o que o spec pede, afrouxa critério de aceite ou quebra/afrouxa uma regra.
- **No escopo.** Bug real ou melhoria clara com a mesma causa do spec, ou no código tocado pela mudança.
- **Fora do escopo.** Problema real com outra causa, já existente na alvo. Nunca bloqueia, salvo se a mudança passar a dispará-lo. Use `git blame` quando o diff não deixar isso claro.

### Relatório

Primeira linha: o veredito, **Pronto** ou **Não pronto**, seguido de uma frase de motivo. Segunda: a contagem ("2 bloqueios, 1 no escopo, 0 fora do escopo"; sem nada a corrigir, diga isso). Terceira: os SHAs julgados (`B`, `A`, `M`), o risco usado e o modelo em que você está rodando. Depois os bloqueios, cada um com arquivo, linha e falha concreta; os achados no escopo e fora do escopo, em uma linha cada; e as checagens executadas ou não executadas, com o resultado. Não liste o que passou apenas na leitura. O relatório precisa se sustentar sozinho para quem não viu sua investigação.

## Revisão de spec

Julgue o spec antes de alguém implementá-lo. Leia o spec, os arquivos que ele toca e o que for preciso do código e dos dados para checar suas afirmações. Responda apenas a estes três pontos, com evidência (arquivo e linha, ou comando e saída):

1. A abordagem resolve o objetivo declarado? Se não, o que quebra e em qual entrada.
2. Cada checagem de aceite prova o que seu critério afirma? Sinalize checagem que passaria numa implementação errada, número esperado tirado da própria implementação em vez de fonte independente, e amostra que seja dado real de cliente ou não versionada.
3. O que falta (critério sem checagem, caso que a mudança precisa sobreviver, nível de risco baixo demais para o que toca) e o que é desnecessário.

Termine com uma linha: **aprovar**, **aprovar com ajustes** ou **refazer**, e o motivo.

## Exemplos

| Pedido | Resultado |
| --- | --- |
| `/review spec specs/receita-liquida.md` | Se o teste calcula o esperado com a mesma função que pretende validar, recomende um valor independente e cite a linha que compromete a prova. |
| “A branch `receita-liquida` está pronta para merge em `main`?” | Use o modo branch. Se o join duplicar uma venda de R$ 100, reporte a entrada, o total esperado, o total obtido e os SHAs julgados. |
| “Confira só o que mudou depois da última revisão.” | Compare o delta se os SHAs anteriores permitirem. Se o alvo avançou, use o diff completo e preserve decisões anteriores que ainda se sustentam. |
| “Dá uma segunda opinião nesse plano de arredondamento antes de eu codar?” | Use o modo spec. Se a métrica alimentar produção, confronte o risco registrado com o consumidor encontrado e indique a checagem ponta a ponta que falta. |
| `/review branch specs/filtro.md ../filtro filtro main` com alterações locais no teste | Cite o teste como não verificado para o SHA da branch. Preserve a worktree e julgue o diff com os SHAs fixados. |
| “Implemente o spec aprovado.” | O pedido é para `implement`. |
| “Escreva um plano de implementação.” | O pedido é para `spec`. |
| “Aplique o squash e arquive.” | O pedido é para `close-spec`. |
