---
name: research
description: Confere uma ideia contra a literatura acadêmica antes do spec. Use ao perguntar se já foi feita, se as premissas se sustentam ou o que a contradiz.
argument-hint: "[ideia, caminho da nota ou contexto da conversa]"
---

# Pesquisar uma ideia na literatura

Entradas: $ARGUMENTS

O relatório serve para decidir se a ideia vale um spec. Cada afirmação apoiada em literatura aponta para um paper real e para o trecho que a sustenta, porque uma citação inventada leva a uma decisão errada sem que ninguém perceba. Descobrir que a ideia já foi feita ou que uma premissa não se sustenta é um resultado útil.

## Ferramenta

Use apenas papers obtidos pelo `lit.py`, que fica ao lado deste arquivo: `.devin/skills/research/lit.py` no projeto, ou `~/.config/devin/skills/research/lit.py` (`%APPDATA%\devin\skills\research\lit.py` no Windows) na instalação global. Leia `python lit.py --help`. Todo paper obtido por `search`, `get` ou `snippets` entra no registro `research/papers.jsonl`, e o `verify` só aceita citações desse registro. Nunca cite de memória.

## 1. Afirmações e queries

Quebre a ideia em afirmações verificáveis: o que ela supõe ser novo, cada premissa da qual depende e o resultado que espera. Para cada afirmação, escreva queries que busquem o que a confirma, o que a contradiz (crítica, limitação, replicação que falhou) e trabalho anterior com a mesma técnica ou o mesmo dado.

A busca envia as queries a serviços externos. Antes da primeira chamada, mostre as queries ao usuário. Se a ideia for de trabalho, ou se não estiver claro, espere o ok. Use termos genéricos do domínio, sem nome de cliente, dado interno ou detalhe que identifique o projeto.

Se a nota do usuário citar papers, resolva cada um com `get`. O que não for encontrado fica como não localizado e nunca vira evidência.

Queries vagas trazem papers que só mencionam os termos: escreva cada query com o conceito central e o objeto da ideia.

## 2. Buscar até saturar

Delegue a busca ao subagente `researcher`, que lê os resumos fora do seu contexto. Envie as afirmações, as queries aprovadas, o caminho do `lit.py` e o do registro. Se o subagente estiver indisponível, faça a busca você mesmo com as mesmas regras:

- Julgue a relevância pelo resumo ou pelo trecho, nunca só pelo título. Use `get` para o resumo completo, `snippets` para o corpo do texto e `--sort cited` para achar os trabalhos de referência do tema.
- Pese a qualidade de cada fonte. Prefira artigo revisado por pares e revisão sistemática. Preprint, paper sem citações e periódico desconhecido podem entrar, mas a evidência diz isso e o veredito não se apoia só neles. Paper retratado nunca vale como evidência.
- Nas rodadas seguintes, acrescente às queries apenas termos e autores dos papers obtidos. Pare quando uma rodada não trouxer paper relevante novo ou depois de quatro rodadas, e registre qual dos dois aconteceu.
- Se uma fonte falhar ou atingir o limite, registre isso: busca incompleta não demonstra ausência.

Confira o retorno antes de usá-lo: o veredito proposto precisa decorrer dos trechos citados.

## 3. Veredito por afirmação

| Veredito | Quando |
| --- | --- |
| `já feito` | Um trabalho publicado já faz o que a afirmação supõe ser novo. |
| `sustentada` | A literatura apoia a premissa e nenhum trabalho encontrado a contradiz de forma relevante. |
| `contestada` | Há trabalho que contradiz a premissa ou mostra que ela não vale no caso da ideia. |
| `sem evidência` | A busca não encontrou trabalho que decida a afirmação. Diga o que foi buscado. |

Cada veredito, exceto `sem evidência`, traz ao menos uma evidência no formato `[ID] "trecho"`, com o trecho copiado da saída do `lit.py`. Mostre também a evidência contrária a um veredito `sustentada`, quando houver.

## 4. Relatório e conferência

Escreva `research/<slug>.md` com: a ideia; um veredito geral em uma linha (seguir, ajustar, já existe ou premissa não se sustenta); a tabela de afirmações com veredito; as evidências, uma por linha; as citações da nota do usuário com o ID entre crases e o status; as queries, as rodadas e o motivo da parada; e os pontos abertos.

Rode você mesmo `python lit.py verify research/<slug>.md`, mesmo que o `researcher` já tenha conferido, e corrija cada falha copiando o trecho do texto obtido ou removendo a evidência. Repita até zero falhas.

Depois peça ao subagente `reviewer` que leia o relatório e o registro e diga, para cada evidência, se o trecho sustenta a afirmação e o veredito: apoia, apoia em parte ou não apoia, com o motivo. Revise os vereditos que ele contestar. Se o subagente estiver indisponível, marque a revisão como pendente no relatório.

Entregue o caminho do relatório, o veredito geral, as afirmações `já feito` ou `contestada`, o resultado do `verify` e o da revisão. O relatório pode servir de nota para `/spec`.

## Exemplos

| Pedido | Resultado |
| --- | --- |
| `/research usar a Lei de Benford nos óbitos diários de COVID-19 para detectar subnotificação` | Afirmação de novidade `já feito`, com o estudo que aplicou Benford aos óbitos por estado e o trecho do resumo que relata a subnotificação. |
| “Antes do spec, vê se a premissa de que o atraso de notificação é constante entre estados se sustenta.” | Mostre as queries, espere o ok por ser trabalho e devolva o veredito da premissa com a evidência contrária encontrada. |
| “Minha nota cita Silva 2021 com um DOI; confere se ele diz isso.” | Resolva o DOI com `get`. Se não existir, marque como não localizado e não use como evidência. |
| “Explique o que é a Lei de Benford.” | Responda direto, sem esta skill. |
| “Resuma este paper.” | Leia o paper indicado, sem esta skill. |
| “Escreva o spec do detector de subnotificação.” | Use `spec`. |
| “Revise a branch do detector.” | Use `review`. |
