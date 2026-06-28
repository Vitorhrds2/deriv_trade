# 📂 Plano de Implementação: Anexação do Frontend ao Repositório Principal

O seu repositório remoto (GitHub) exibe o `hypothesis-lab-os` como uma "pasta cinza" que não pode ser clicada porque o Git o enxerga como um "repositório aninhado" (ele possui uma pasta oculta `.git` dentro dele). 

Para que os arquivos fiquem fisicamente dentro do repositório principal e acessíveis pelo GitHub nativamente, precisamos convertê-lo.

## ⚠️ User Review Required
A conversão exige que deletemos o histórico interno independente do `hypothesis-lab-os` (a pasta oculta `.git` dele). O código fonte e os arquivos (`package.json`, `src/`, etc.) permanecerão 100% intactos, mas ele deixará de ser um repositório isolado e passará a pertencer ao histórico principal do `hypothesis`.

## ❓ Open Questions
Você precisa do histórico isolado de commits do Frontend? Se não, podemos proceder e torná-lo uma pasta comum.

## 🛠️ Proposed Changes

Executarei a seguinte rotina de desanexação e reanexação:

1. **Remover a Referência Fantasma:**
   Desvincular o ponteiro de repositório aninhado usando o Git.
   `git rm --cached hypothesis-lab-os`

2. **Deletar a Independência do Submódulo:**
   Remover a pasta oculta `.git` de dentro do projeto frontend para que ele vire arquivos normais do sistema.
   `rm -rf hypothesis-lab-os/.git`

3. **Reanexar e Versionar no Repositório Principal:**
   Adicionar a pasta, agora como um diretório normal, realizar o commit como `Carlos Paiva` (conforme nossa última regra), e enviar o Push para a branch atual (`feat/sniper-lenta`).

## 🧪 Verification Plan
Acessaremos a interface web do GitHub ou faremos um `git status` para confirmar que todos os arquivos contidos em `hypothesis-lab-os/` (como o `package.json` e a pasta `src/`) passaram a ser rastreados nativamente pelo repositório principal.
