---
name: implement
description: Use quando o usuário pedir para implementar um spec aprovado em specs/. Execute em worktree, valide cada passo e entregue a revisão antes do merge.
argument-hint: "[caminho do spec]"
triggers:
  - user
---

# Implement

O spec em `specs/<slug>.md` é a especificação. Planeje, edite e valide na sessão principal, que mantém o contexto de cada decisão. Não delegue a escrita do código a outro agente. Use o subagente `explorer` para leituras longas com pergunta delimitada e confira você mesmo as evidências de cada decisão.

## Preparação

- Leia o spec e todo `AGENTS.md` ou `CLAUDE.md` que governa os arquivos tocados. Se o spec não tiver nível de risco ou tiver critério de aceite sem checagem, pare e pergunte ao usuário.
- Crie uma worktree com a branch `<slug>` a partir da branch atual do usuário. Se o spec ainda não estiver commitado, faça dele o primeiro commit da branch. Anote a referência da versão aprovada, `<sha>:specs/<slug>.md`, porque o revisor confere os critérios contra ela.
- Não faça push: o remoto é um repositório bare compartilhado pelo time, e o push é decisão do usuário.

## Passos

Construa a menor mudança que atende aos critérios, no peso que o risco exige, porque cada guarda extra é mais código para revisar e manter. Siga as decisões do spec e escolha o resto do método.

Execute cada passo na worktree, rode a checagem que o valida e faça commit com mensagem terminando numa linha `Validado: <comando> -> <resultado>`, ou `Validado: nenhum` com o motivo, porque `close-spec` leva essas linhas para o commit de merge. Não commite `.explore/` nem saídas temporárias. Leituras independentes podem rodar em paralelo; edições e decisões ficam na sessão principal.

Um teste que falha e depois passa sem mudança é intermitente (flaky): diga isso no relatório e no commit, mesmo que passe durante a investigação, em vez de reexecutar até passar.

Quando um passo falha, confira primeiro se a checagem executa e mostra o erro. Use a falha para corrigir a implementação, sem afrouxar a checagem. Se a mesma abordagem falhar duas vezes, mude o método com base nas evidências; se não houver alternativa fundamentada, pare e entregue ao usuário o erro, o que foi tentado e a decisão necessária.

Quando uma descoberta mudar o plano, reescreva o spec para seu estado final e avise o usuário. Se mudar o objetivo ou um critério de aceite, espere o ok do usuário, commite o spec com "aprovado pelo usuário" na mensagem e use esse commit como nova referência aprovada.

## Revisão

Rode todos os critérios de aceite antes da revisão: nenhum revisor substitui uma checagem executável.

Depois rode a skill `review` em modo branch (`/review branch <spec> <worktree> <branch> <target> <approved ref>`), que executa no subagente `reviewer` com um modelo de outro fornecedor; na primeira rodada, não envie seu raciocínio, para que o revisor julgue a mudança como ela está. Rodadas: risco baixo até 2, médio até 2, alto até 3; se o revisor subir o risco, use o limite do novo risco.

Antes de corrigir, reproduza cada bloqueio a partir da falha apontada pelo revisor (rode o comando, leia a linha); um bloqueio que você não conseguir reproduzir vai para o usuário marcado como não confirmado. Corrija todo bloqueio confirmado e cada achado no escopo cujo custo compense. Achados fora do escopo vão para o relatório. Você pode descartar um achado do qual discorde dando o motivo em uma linha, mas um bloqueio contestado vai para o usuário. Commite as correções e, se restar rodada, rode `review` de novo passando os SHAs da branch e do alvo julgados na rodada anterior e cada achado com o que foi feito (corrigido em `<sha>`, ou descartado: motivo), para o revisor conferir as correções e decidir se pode revisar só o delta. Em risco baixo, a segunda rodada existe apenas para conferir correções.

Quando achados voltam para a mesma área depois de uma correção, pare de empilhar guardas: questione o método e mude-o, ou pergunte ao usuário, porque cada guarda nova traz um achado novo. Se o limite de rodadas terminar com bloqueio aberto, pare e pergunte: o problema está no método ou no spec. Na última rodada, com veredito pronto, não commite melhorias no escopo: deixe no relatório, porque um commit novo ficaria sem revisão.

## Portão

Não faça merge nem push; isso pertence a `close-spec`. O veredito só é pronto com todos os critérios passando no HEAD atual, nenhum teste flaky sem causa encontrada, nenhum bloqueio aberto e os SHAs da branch e do alvo coincidindo com os da última revisão. Relate, nesta ordem, porque `close-spec` pode rodar em outra sessão e depende disso:

1. O veredito e o risco final (o do spec, ou o que o revisor elevou).
2. Spec, referência aprovada, worktree, branch e alvo.
3. Os SHAs (branch, alvo, base) que a última revisão julgou, comparados com o HEAD atual, e o modelo do revisor.
4. Cada critério de aceite com seu comando e resultado.
5. Achados descartados com o motivo, achados no escopo não corrigidos e achados fora do escopo.

## Exemplos de implementação

| Pedido | Ação e resultado esperado |
| --- | --- |
| `/implement specs/receita-liquida.md` | Crie a worktree de `receita-liquida`. Numa amostra com R$ 100 de venda e R$ 20 de estorno, confira os R$ 80 previstos no spec. Registre a validação no commit e entregue o veredito com os SHAs julgados. |
| “Pode executar o plano que aprovei em `specs/arredondamento.md`?” | Registre a referência aprovada. Se o arredondamento alimentar o comitê, rode a checagem diferencial e a checagem ponta a ponta do spec antes da revisão de risco alto. |
| “Pode codar o spec aprovado que acabamos de discutir?” | Recupere o caminho da versão aprovada na conversa e use esse arquivo como referência na worktree. Se houver mais de um spec possível, confirme qual deve ser implementado. |
| “Implemente `specs/filtro-ativos.md`.” O critério de contagem de descartes está sem checagem. | Aponte o critério sem prova e peça a checagem de aceite antes de editar. |
| “Implemente o spec de conciliação e deixe a branch pronta para revisão e merge.” A checagem passa numa repetição sem mudança. | Registre a intermitência e investigue a causa. Enquanto o teste continuar sem explicação, relate o estado como não pronto e preserve a branch para retomar. |

Pedidos próximos usam outras skills:

| Pedido | Ação |
| --- | --- |
| “Escreva um plano para filtrar pedidos ativos.” | Use `spec` para produzir o plano. |
| “Confira se esta branch implementa o spec.” | Use `review` para julgar a branch existente. |
| “Faça o squash e arquive o spec já revisado.” | Use `close-spec` para verificar os SHAs e fechar o trabalho. |
