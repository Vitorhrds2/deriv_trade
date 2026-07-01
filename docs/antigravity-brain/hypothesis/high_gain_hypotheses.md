# Hipóteses Agressivas (Low Balance, High Gains) 🚀

Enquanto o nosso robô roda no seu banho, já preparei o terreno para o nosso "Plano B". Se o modelo conservador atual demorar muito para agir e não gerar a variação esperada, nós podemos mudar a marcha para estratégias de **hiper-crescimento**.

Considerando que o seu capital de risco inicial será pequeno (R$ 50,00 ou ~$10 USD), estratégias conservadoras de 2% ao mês renderão centavos. Para transformar $10 em centenas ou milhares, precisamos de **alavancagem assimétrica**, **juros compostos agressivos** ou **alta frequência de giros**.

Aqui estão 3 hipóteses baseadas no *Algotrade Knowledge Hub* e dinâmicas de mercado da Deriv que podemos codificar em seguida:

---

## Hipótese 1: Snowballing com Kelly Criterion Modificado (Juros Compostos Agressivos)
> **Resumo:** Reinvestimento maciço do lucro em operações altamente prováveis usando Contratos Multipliers.

A fórmula de Kelly nos diz matematicamente qual é a % exata do capital que devemos apostar para maximizar o crescimento no longo prazo. Em bancas pequenas, usamos um "Kelly Fracionado Agressivo" (ex: 30% a 50% da banca por trade) mas focado **exclusivamente** em setups de altíssima precisão.
* **O setup:** Em vez de esperar cruzar a Média Móvel, nós entramos no trade logo que a vela rompe uma Banda de Bollinger de **3.0 SD** (evento muito raro).
* **O pulo do gato:** Usamos Multipliers de **x500** ou **x1000** com Stop Loss ultra curto e Take Profit longo. Como a anomalia estatística força uma forte correção do preço, o lucro é massivo. Se errarmos, perdemos pouco (devido ao Stop Loss curto). Se acertarmos, dobramos a aposta usando o lucro do último trade.

## Hipótese 2: Scalping de Alta Frequência em Ticks (Micro-momentum)
> **Resumo:** Entrar e sair do mercado em questão de 5 a 10 segundos, fazendo dezenas de operações na hora.

A Deriv oferece índices como o `1HZ10V` (Volatility 10 (1s) Index) onde um novo preço surge a cada 1 segundo. Nós abandonamos o gráfico de 1 minuto e descemos para o **Gráfico de Ticks**.
* **O setup:** O robô assina o WebSocket de `ticks` simples. Ele calcula o RSI (Relative Strength Index) num período micro de 14 ticks. Quando o RSI bater `< 10` ou `> 90`, ele dispara um contrato digital de **Rise/Fall (CALL/PUT) com duração exata de 5 Ticks**.
* **O pulo do gato:** Retorno fixo de ~95% por contrato em poucos segundos. Ao fazer 100 apostas por dia num modelo estatisticamente superior a 55% de Win Rate, o baixo balanço escala absurdamente rápido.

## Hipótese 3: Martingale Assimétrico Estratégico (O "Caminho do Risco")
> **Resumo:** Aumentar o tamanho do trade após uma perda para recuperar com lucro, mas com travas de segurança.

O Martingale clássico (dobrar a aposta ao perder) quebra qualquer conta pequena. Porém, o *Martingale Assimétrico* só aumenta a mão se a configuração do mercado **melhorar a seu favor**.
* **O setup:** Entramos apostando R$ 5,00 numa reversão após 2 velas de queda fora da banda. Se perdermos, significa que a tendência de queda continuou.
* **O pulo do gato:** Em vez de apostar R$ 10,00 na *próxima* vela cegamente, o robô **espera** a formação de um novo padrão (ex: um Candle Engolfo de Alta) para aí sim dar o tiro de $10. Isso absorve a força do choque e capitaliza na reversão real da tendência que inevitavelmente acontece em mercados de volatilidade.

---

## User Review Required

> [!IMPORTANT]
> Quando voltar do banho, analise o terminal. Se o nosso robô principal estiver estático ou você preferir ação imediata de alto retorno, me diga **qual das 3 hipóteses acima mais lhe agrada** para começarmos a arquitetura do novo bot!
