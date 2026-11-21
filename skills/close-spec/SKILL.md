---
name: close-spec
description: Use quando o usuário pedir o merge ou squash de um spec já revisado, seu arquivamento ou a limpeza após o fechamento. Confira os SHAs e faça o fechamento local.
argument-hint: "[spec ou branch]"
triggers:
  - user
---

# Fechar um spec revisado

## Entradas e resultado

Leia branch, alvo, worktree e veredito a partir do argumento do usuário ou do último relatório de `implement`. Sem relatório recuperável, confirme o alvo com o usuário e rode as checagens do spec e a skill `review` antes de seguir.

| Entrada | Como resolver |
| --- | --- |
| Caminho do spec | Localize o arquivo e a branch correspondente no relatório de implementação. |
| Nome de branch | Use o relatório de implementação para recuperar o caminho do spec, o alvo e os SHAs. |
| Pedido de retomada sem argumento | Localize o último relatório de fechamento e confira o commit no alvo e o spec arquivado antes de decidir se falta apenas a limpeza. |

Reporte o caminho do spec, a branch, o alvo, a worktree e os SHAs aprovados. O resultado esperado é um commit local no alvo e o spec em `specs/done/`. Se já existir um commit de fechamento verificado para aquele spec, retome apenas a limpeza pendente após conferir o estado atual. Espere um ok antes de qualquer passo que possa perder trabalho, incluindo um commit ausente do squash, mudanças não commitadas ou um rebase.

## Conferir o que foi aprovado

O veredito vale apenas para os SHAs que o revisor julgou (branch e alvo). Imediatamente antes do squash, compare `git rev-parse <branch>` e `git rev-parse <target>` com eles. Se qualquer um mudou (commit novo, rebase, alvo que avançou), ou se o veredito não for pronto, não faça merge: rode as checagens do spec no HEAD atual, peça nova revisão do que mudou e avise o usuário. Isso vale mesmo com permissão prévia para fechar, porque essa permissão foi dada para o que foi revisado.

| Estado observado | Próxima ação |
| --- | --- |
| Squash ainda pendente e revisão válida | Faça o fechamento local. |
| Alvo avançou, branch mudou ou revisão pendente | Atualize os resultados de aceite e peça revisão do par atual. |
| Já existe commit de fechamento verificado | Retome na verificação e limpeza. |

## Squash e arquivamento

1. Se a branch estiver atrás da alvo e o usuário quiser o rebase, faça na worktree da branch. O rebase altera os SHAs, então volte para "Conferir o que foi aprovado".
2. No checkout principal (o git recusa mexer em branch ocupada por outra worktree), com árvore limpa, troque para a branch alvo. Faça a conferência dos SHAs com o alvo já em checkout e rode `git merge --squash <SHA revisado da branch>`. Em caso de conflito, liste os arquivos não mesclados com `git diff --name-only --diff-filter=U`, informe o estado do checkout e pare antes do commit e da limpeza.
3. Antes de commitar, mova o spec para `specs/done/`, para nenhum agente trabalhar nele de novo, e registre em `specs/pending.md` apenas achados fora do escopo que sejam bug reproduzido, regra do `AGENTS.md` quebrada ou melhoria de alto valor, um por linha, com o spec de origem. Se já existir uma linha com a mesma causa, adicione o caso a ela sem duplicar.
4. Crie um único commit com o título do spec. O corpo preserva as mensagens dos passos com suas linhas `Validado:` e termina com estas seções curtas, que são o que alguém precisa ao achar esse commit num incidente:
   - **Como testado**: as checagens de aceite e seus resultados.
   - **Risco**: o do spec, ou o que o revisor elevou, com uma linha sobre o que quebra.
   - **Como reverter**: `git revert` basta para código; para tabela, dado ou arquivo em produção, informe o passo (backup, reprocessamento).
   - **Achados descartados**: um por linha, com o motivo.

## Verificação e limpeza

1. Confira com `git show --stat <commit>` e `git diff <alvo-revisado> <commit>` se o squash contém a mudança revisada, o arquivamento e as pendências registradas.
2. Antes de remover a worktree, confira o HEAD dela, o tip da branch e `git status --porcelain` na worktree. Se houver trabalho novo, preserve a branch e a worktree e informe o motivo. Caso contrário, remova a worktree sem `--force`, rode `git worktree prune` e apague a branch local com `git branch -D` somente se ela ainda estiver no SHA revisado. O squash deixa os commits antigos fora da ancestralidade do alvo.
3. Se a limpeza falhar, preserve o commit e informe a ação pendente. Em nova chamada, confirme com `git worktree list` se a worktree ainda existe e com `git rev-parse --verify <branch>` se a branch ainda existe. Ignore o que já foi removido e verifique o SHA antes de excluir uma branch remanescente.
4. Deixe o push para uma solicitação separada. Informe quantos commits o alvo está à frente se houver uma referência remota conhecida.

Reporte o commit de merge, os achados registrados e o que não pôde ser limpo, com o motivo. Nunca use `--no-verify` nem force-push.

```text
Exemplo de entrega
Squash local: <SHA> em main
Spec arquivado: specs/done/receita-total.md
Pendência registrada: divergência no relatório mensal de dezembro
Worktree e branch: removidas após conferência
Push: não realizado
```

## Exemplos

`/close-spec specs/receita-total.md` com revisão pronta de `receita-total` para `main` entrega um commit local em `main`, move o spec para `specs/done/receita-total.md` e informa se a worktree foi removida. Se o alvo tiver mudado desde o relatório, o resultado é uma divergência identificada e o squash fica pendente de nova revisão.

| Pedido | Resultado |
| --- | --- |
| `/close-spec receita-liquida` com relatório pronto e SHAs válidos | Faça o squash, arquive `specs/receita-liquida.md`, registre como o merge foi testado e preserve a instrução de reversão no commit. |
| “Faça o merge do spec de arredondamento.” A `main` avançou desde o parecer pronto. | Registre a divergência, rode as checagens e solicite nova revisão antes do squash. |
| “Pode arquivar o spec e limpar a worktree.” A worktree tem alterações locais. | Informe quais alterações seriam afetadas e espere o usuário decidir o que preservar antes da limpeza. |
| “Termina a limpeza do spec que acabou de fechar.” | Verifique o commit no alvo e o spec arquivado. Se a branch não avançou e a worktree estiver limpa, termine a remoção pendente. |
| `/close-spec receita-total` com conflito de squash | Informe os arquivos em conflito e o estado do checkout. Preserve a branch e aguarde a resolução antes de concluir. |
| “Esta branch já está pronta para merge?” | O pedido é para `review`, que devolve o parecer sem fechar o spec. |
| “Implemente a conciliação descrita neste spec aprovado.” | Use `implement` para executar o plano. |
| “Escreva um plano para migrar essa tabela.” | O pedido é para `spec`. |
