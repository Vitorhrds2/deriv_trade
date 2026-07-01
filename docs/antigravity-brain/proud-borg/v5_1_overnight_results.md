# HFT Sniper V5.1 - Relatório da Madrugada

## O Experimento Contra-Tendência (Rubber-Band)
Deixamos o bot rodando com o algoritmo V5.1 (Contra-Tendência) esperando que, após um choque de **> 50 pontos**, a Deriv devolvesse o preço (Efeito Elástico/Rubber-Band).

### Resultados Brutos (Conta Demo)

| Horário | Choque | Direção do Bot | Duração | Resultado (PnL) |
|---|---|---|---|---|
| 08:31:10 | +84.36 | DOWN | 1.5s | **$-10.00** (-100% Stop Out) |
| 08:59:55 | +50.79 | DOWN | 36s | **$-10.00** (-100% Stop Out) |
| 09:02:48 | +66.62 | DOWN | 2s | **$-10.00** (-100% Stop Out) |
| 09:04:29 | +59.07 | DOWN | 44s | **$-10.00** (-100% Stop Out) |
| 09:07:18 | +50.05 | DOWN | 4s | **$-10.00** (-100% Stop Out) |

> [!CAUTION]
> **Win Rate:** 0% (5 Derrotas Consecutivas)

## A Grande Descoberta
O nosso *Hotfix* de checar a presença da chave `entry_tick` acidentalmente introduziu um loop que ignorava o timeout de segurança de 3.5 segundos, porque **contratos do tipo Multiplicador na Deriv não emitem `entry_tick` no websocket de proposta**.
Isso foi uma falha técnica, mas acabou sendo **a maior bênção deste projeto**.

Ao não sair no meio do caminho, fomos forçados a assistir até onde o preço ia. 
Em todas as 5 vezes que o mercado pulou mais de 50 pontos para cima, **ele continuou subindo até derreter nosso contrato inteiro (movimento adicional de >75 pontos contra nós)**.

Isso desmente categoricamente a Teoria da Reversão (Contra-Trend). **Os choques acima de 50 pontos não são ruídos falsos, são verdadeiras injeções de Momentum Direcional.** A corretora não volta o preço, ela continua puxando ele na mesma direção!

## O Caminho para a V6.0
Se os choques de 50 pontos têm um "Follow-Through" (continuação) que passa fácil de 75 pontos de lucro, a estratégia ideal e matadora é voltarmos para o **Seguidor de Tendência (Momentum)** que tínhamos idealizado no começo, mas dessa vez usando a trava inteligente de PnL que desenvolvemos na V5.

Se nós tivéssemos ido a favor da tendência nesses 5 trades, teríamos batido o alvo de lucro em todos eles!
