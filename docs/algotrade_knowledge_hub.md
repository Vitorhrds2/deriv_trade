# Algotrade Knowledge Hub – Referência Completa

*Compilado em 18/06/2026 a partir de hub.algotrade.vn*

---

# Sumário


## I. OVERVIEW

- [01. Introduction to Algorithmic Trading](#01-introduction-to-algorithmic-trading)
- [02. Advantages of Algorithmic Trading](#02-advantages-of-algorithmic-trading)
- [03. Algorithmic Trading Risks](#03-algorithmic-trading-risks)
- [04. Core Components to Build an Algorithmic Trading System](#04-core-components-to-build-an-algorithmic-trading-system)
- [05. Semi-Automated Trading](#05-semi-automated-trading)
- [06. 09 Steps to Develop Algorithms](#06-09-steps-to-develop-algorithms)

## II. PROPOSE AN ALGORITHM HYPOTHESIS

- [07. Distinction between Two Types of Algorithms](#07-distinction-between-two-types-of-algorithms)
- [08. Execution Algorithms to Optimize Trading Fees](#08-execution-algorithms-to-optimize-trading-fees)
- [09. 06 Components to Build a Complete Trading Algorithm](#09-06-components-to-build-a-complete-trading-algorithm)
- [10. Differences Between Equity and Derivative Trading](#10-differences-between-equity-and-derivative-trading)
- [11. How to Construct an Algorithm Hypothesis](#11-how-to-construct-an-algorithm-hypothesis)
- [12. Trading Strategy Overview](#12-trading-strategy-overview)
- [13. Market-Neutral Strategy](#13-market-neutral-strategy)
- [14. Price Momentum Strategy](#14-price-momentum-strategy)
- [15. Mean-Reversion Strategy](#15-mean-reversion-strategy)
- [16. Event-Driven Strategy](#16-event-driven-strategy)
- [17. Market-Making Strategy](#17-market-making-strategy)
- [18. Scalping Strategy](#18-scalping-strategy)
- [19. ETF Front-Runner Strategy](#19-etf-front-runner-strategy)
- [20. Arbitrage Strategy](#20-arbitrage-strategy)
- [21. Grid Strategy](#21-grid-strategy)
- [22. Smart-Beta Strategy](#22-smart-beta-strategy)
- [23. Sniffing Strategy](#23-sniffing-strategy)
- [24. High-Tech Algorithmic Trading](#24-high-tech-algorithmic-trading)
- [25. Behavioral Finance in Algorithmic Hypothesis Formation](#25-behavioral-finance-in-algorithmic-hypothesis-formation)

## III. DATA

- [26. Standard Data in Algorithmic Trading](#26-standard-data-in-algorithmic-trading)
- [27. Data Cleaning Tutorial](#27-data-cleaning-tutorial)
- [28. Data Management in Algorithmic Trading](#28-data-management-in-algorithmic-trading)
- [29. Stock Trading API in Vietnam Market](#29-stock-trading-api-in-vietnam-market)
- [30. Search Process for Fastest Data Source](#30-search-process-for-fastest-data-source)

## IV. BACKTESTING

- [31. Philosophical Foundations of Backtesting](#31-philosophical-foundations-of-backtesting)
- [32. Critical Mistakes in Backtesting](#32-critical-mistakes-in-backtesting)
- [33. Backtesting Module](#33-backtesting-module)

## V. OPTIMIZATION

- [34. Optimizing Trading Algorithms](#34-optimizing-trading-algorithms)
- [35. Techniques to Avoid Overfitting](#35-techniques-to-avoid-overfitting)
- [36. Post-optimization Assessment](#36-post-optimization-assessment)

## VI. FORWARD TESTING

- [37. Meaning of Forward Testing](#37-meaning-of-forward-testing)
- [38. Paper Trading](#38-paper-trading)
- [39. Small Account Test](#39-small-account-test)

## VII. REAL TRADING

- [40. Algorithm in Real Environment](#40-algorithm-in-real-environment)
- [41. Evaluation of Execution Algorithms With TWAP and VWAP](#41-evaluation-of-execution-algorithms-with-twap-and-vwap)
- [42. Measuring Implementation Shortfall](#42-measuring-implementation-shortfall)

## VIII. EVALUATION CRITERIA FOR ALGORITHMS

- [43. Return Rate](#43-return-rate)
- [44. Maximum Drawdown in Algorithmic Trading](#44-maximum-drawdown-in-algorithmic-trading)
- [45. Kelly Criterion – Definition and Application](#45-kelly-criterion-definition-and-application)

## IX. OPTIMIZATION IN MULTI-ALGORITHM TRADING

- [46. Capital Optimization on Multi-Algorithms System](#46-capital-optimization-on-multi-algorithms-system)
- [47. Beta Optimization](#47-beta-optimization)
- [48. Leverage Transaction Data](#48-leverage-transaction-data)

## X. ALGORITHMIC TRADING PRACTICE

- [49. Models or Randomness](#49-models-or-randomness)
- [50. Is Algorithmic Trading a Zero-Sum Game](#50-is-algorithmic-trading-a-zero-sum-game)
- [51. What to Do When in Doubt of Your Trading Algorithm](#51-what-to-do-when-in-doubt-of-your-trading-algorithm)
- [52. Scams in Algorithmic Trading: 07 Major Characteristics](#52-scams-in-algorithmic-trading-07-major-characteristics)
- [53. Third-Party Software in Algorithmic Trading](#53-third-party-software-in-algorithmic-trading)
- [54. Is Algorithmic Trading Preferable for All Traders](#54-is-algorithmic-trading-preferable-for-all-traders)
- [55. How to Become an Algorithmic Trader](#55-how-to-become-an-algorithmic-trader)
- [56. How to Learn Programming Skills for Algorithmic Trading](#56-how-to-learn-programming-skills-for-algorithmic-trading)

## XI. INTEL CENTER – SUPPORT CHANNEL

- [57. Intel Center Overview](#57-intel-center-overview)
- [58. Foreign Trading Data](#58-foreign-trading-data)
- [59. Daily Accumulative Foreign Trading Value in VN30](#59-daily-accumulative-foreign-trading-value-in-vn30)

## XII. ALGOTRADE LAB – FIRST STEP TO ALGORITHMIC TRADING

- [60. Algotrade Lab Overview](#60-algotrade-lab-overview)
- [61. Introduction to SMA Algorithm](#61-introduction-to-sma-algorithm)
- [62. How to Register for API at SSI Securities JSC](#62-how-to-register-for-api-at-ssi-securities-jsc)
- [63. Experience Algotrade Lab](#63-experience-algotrade-lab)
- [64. SMA Algorithm Configuration and Monitoring Experience](#64-sma-algorithm-configuration-and-monitoring-experience)

## OTHER ARTICLES

- [Sortino Ratio](#sortino-ratio)
- [Information Ratio](#information-ratio)
- [Fundamental Analysis and Technical Analysis](#fundamental-analysis-and-technical-analysis)
- [Smart Beta Backtesting Procedure](#smart-beta-backtesting-procedure)
- [Biases in Algorithmic Trading](#biases-in-algorithmic-trading)
- [Popular Technical Analysis Indicators](#popular-technical-analysis-indicators)
- [Stock Price Prediction – A Discipline Branch Within Social Science](#stock-price-prediction-a-discipline-branch-within-social-science)
- [Challenges in Economic Forecasting](#challenges-in-economic-forecasting)
- [Five Personal Factors Influencing Investment Strategy](#five-personal-factors-influencing-investment-strategy)
- [Feature Improvement Procedure for Live Algorithms](#feature-improvement-procedure-for-live-algorithms)
- [Overfitting and How to Mitigate It](#overfitting-and-how-to-mitigate-it)
- [Moving Average](#moving-average)
- [How to Integrate Expert Input](#how-to-integrate-expert-input)
- [Intraday Algorithmic Trading](#intraday-algorithmic-trading)
- [Head and Shoulders Pattern](#head-and-shoulders-pattern)
- [Algorithmic Trading, Quant Trading and High Frequency Trading](#algorithmic-trading-quant-trading-and-high-frequency-trading)
- [Equity Segmentation](#equity-segmentation)
- [Weighting Methods Used in Smart-Beta Strategy](#weighting-methods-used-in-smart-beta-strategy)
- [Key Insights From Career Development of Quant King Jim Simons](#key-insights-from-career-development-of-quant-king-jim-simons)
- [Passive, Active, and Quantitative Investment](#passive-active-and-quantitative-investment)
- [Action Bias in Algorithmic Trading](#action-bias-in-algorithmic-trading)
- [Quantitative Hedge Funds and Algorithms](#quantitative-hedge-funds-and-algorithms)
- [04 Strategies for Closing Positions in Algorithmic Trading](#04-strategies-for-closing-positions-in-algorithmic-trading)
- [Hedging in Algorithmic Trading](#hedging-in-algorithmic-trading)
- [Variations of Statistical Arbitrage](#variations-of-statistical-arbitrage)
- [Optimal Position Sizing Strategy in Algorithmic Trading](#optimal-position-sizing-strategy-in-algorithmic-trading)
- [What Algorithmic Trading Can and Cannot Offer for a Typical Hedge Fund](#what-algorithmic-trading-can-and-cannot-offer-for-a-typical-hedge-fund)
- [Implementation Challenges of Market Neutral Strategies](#implementation-challenges-of-market-neutral-strategies)
- [After The 9 Steps](#after-the-9-steps)
- [Risk Management in Algorithmic Trading](#risk-management-in-algorithmic-trading)
- [Basic Assumptions and Market Evolution](#basic-assumptions-and-market-evolution)

## GLOSSARY

- [Glossary of Terms](#glossary-of-terms)

---


# I. OVERVIEW


## 01. Introduction to Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/algorithmic-trading-overview/*

How long do you think one takes to evaluate this expression?

**260 x 252 - 721 = ?**

No matter how fast one can calculate the expression, one cannot solve it faster, more reliably, and more accurately than a computer. This is the fundamental concept of algorithmic trading: making use of computing power to perform tasks in which computers outperform humans’ capabilities

**Algorithmic trading** is using a computer system to carry out fully automated trades according to pre-programmed algorithms.

**A[trading algorithm](glossary)** is a concrete investment strategy in a set of execution statements to make trading decisions. It also determines what to buy or sell, at what price, and in how much volume and in which order type.

**An[algorithmic trading system](glossary)** automates all data collection processes, and data queries and uses computer algorithms to make trading decisions and reports, to manage real-time financial portfolios without any human intervention.

  * **Query data.** An algorithmic trading system can automatically update the latest information on the price and volume of all stocks in companies listed on all 03 stock exchanges in Vietnam, namely HOSE/HNX/UPCOM every 02 seconds, and it can query data at all times. This is a huge competitive advantage for investors who want to exhaust existing opportunities in the market.
  * **Make trading decisions.** The system automatically makes trading decisions after each data update. A [high-frequency trading](glossary) algorithm can make thousands of trading decisions every day.
  * **Place investing orders.** After making a trading decision, the algorithm can place or cancel trading orders to the investor’s account. It is possible to successfully place trading orders as fast as 50 milliseconds in the Vietnamese stock market.
  * **Report trading results.** The system can report signals and results of placing/executing/canceling orders in real time. Simultaneously, it constantly updates the account status and summarizes trading results. In addition, it reports bugs in real-time to improve reaction time and resolve technical problems.
  * **Manage financial portfolios.** After updating the portfolio, the change in the trading position will affect subsequent trading decisions. Portfolio management gets more complex as the trading system operates on both the stock market and the derivatives market.


If there’s no delay in order matching, all the steps above can be completed in 2.5 seconds by a computer system, compared to manual operations which can take over 30 seconds.

Thanks to the algorithm process, the strategy can be consistently executed on a large number of transactions, eliminating human biases (emotional biases and cognitive errors), thus following the law of large numbers to assess the effectiveness of trading strategies.

It’s important to note that the investment performance mainly depends on the algorithm design. A poor investment strategy will only lead to automatic losses when put into an algorithmic trading system.

---


## 02. Advantages of Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/advantages-of-algorithmic-trading/*

Algorithmic trading brings unique strengths of computer systems to traders that traditional trading does not have. Taking advantage of the algorithmic potential can dramatically change investment performance.

# The Law of Large Number

In probability and statistics, the law of the large numbers states that if the same experiment is repeated independently a large number of times, the average result must be close to the expected value. Alternatively, even with random and unknown events, a sufficiently large number of attempts will lead to a stable average result.

The law of large numbers can be illustrated by rolling the dice. The probability of the occurrence of all sides 1, 2, 3, 4, 5, and 6 is the same. Therefore the expected value of a dice roll event is:

(1 + 2 + 3 + 4 + 5 + 6)÷6 = 3.5

If one only rolls the dice a few times, the average value of the results may be far off from this expected value. For example, roll the dice 3 times and the results are 6, 4, and 5 respectively. The average value is thus 5. However, according to the law of large numbers, if one rolls the dice many thousands of times, the average result will come closer to 3.5.

In trading, the winning or losing results of a handful of transactions can occur randomly and unpredictably. According to the law of large numbers, the results from a small number of trading orders are not sufficient to judge its effectiveness. However, if there’s a reasonable trading strategy with a winning expectation over 50% across a large number of trades, then on average it will generate profits in the long run even though there might be periods of consistent losses or consistent wins. Moreover, these results can be used as tests to evaluate a trading strategy’s performance.

In practice, there’s a big issue when applying the law of large numbers to real-life trading. It’s often difficult for investors to ensure all transactions are sufficiently consistent according to a predefined strategy, due to the following factors:

  * Effects of psychology and emotions;
  * Risks such as mistakes in placing orders, or slow reaction time that leads to missing buy or sell opportunities;
  * Unable to place orders according to the predefined strategy due to irregular price monitoring.


Because of these issues, the results obtained can be far from the initial expectation despite an effective trading strategy and a sufficiently large number of trades. More importantly, it’s impossible to assess whether this result is due to a low-performing strategy or poor execution. An [algorithmic trading system](glossary) can solve these problems. It ensures the application of the law of large numbers, minimizing the impact of undesirable factors. Investors only need to focus on building, evaluating, adjusting, and improving their strategies to create stable long-term profits.

# Ensure Investment Consistency and Eliminate Emotional Interference

In stock trading, besides a clear strategy, emotional management is a key factor of investment results. Investors are often swayed by emotions and make decisions contrary to their investment principles or strategies.

For example, before the 2008 global financial crisis, the market signaled that a crisis was imminent. Yet a lot of investors ignored these signs because they were caught up with the “frenzy” up-trend momentum in the market. Few thought a crisis was likely to happen.

Algorithmic trading solves this problem by ensuring all trades follow a predetermined set of rules and strategies. It eliminates the emotional influence of trading altogether. A simple example is the 7% stop-loss principle, common among Vietnamese investors to avoid big losses. However, very few investors actually carry out this trading principle. They often keep holding on to falling stocks even when the price has fallen too low.****A[trading algorithm](glossary) will help investors avoid this. A stop-loss strategy does not guarantee good results, but it does ensure consistent investment principles.

There are random unpredictable events every day. They are out of control yet have a direct impact on the market and stock prices. These events require investors to make a decision to buy, sell or keep holding. Making uninformed decisions gives most investors ambiguity, stress, anxiety, and insecurity.

The algorithmic trading system is not a magic wand that can tell the future and ensure all trading decisions are correct. However, it is an automated system that quickly reacts to random events that can happen without human intervention.

Investors only need to set up periodic reviews, monthly or quarterly, to evaluate an algorithm’s performance. They can make necessary adjustments and upgrades to optimize profits. This mechanism boosts investors’ confidence and reduces stress because there’s no need to be hands-on every day.

# Minimize Market Impact When Trading Large Volumes

A high-volume transaction from institutional investors, hedge funds, or major shareholders can dramatically change the market equilibrium. To avoid this, investors usually split into several small-volume trades.

For example, if you would like to buy 5 million shares of FPT, investors can divide it into 1000 orders, each at 5000 shares per order every 5 minutes. After one hour of this execution, the investors assess the impact of the orders on the stock price. If the share price doesn’t change much in the unfavorable direction, keep following the same strategy and check in on the price every hour until reaching the target of 5 million shares.

However, there’s a time disadvantage to this strategy. In this example, even under favorable market conditions, it still requires at least 83 hours or 21 trading sessions to complete.

An algorithmic trading system solves this problem by simultaneously calculating the volume and making the stock purchase. It also checks the market impact immediately to significantly reduce the number of buy orders and the time required.

# Save Time

A complete algorithmic trading will ensure full execution of the investment process without any investor intervention. It is the best benefit as investors can spend their time more efficiently instead of closely monitoring live boards all day long to place orders.

---


## 03. Algorithmic Trading Risks

*Fonte: https://hub.algotrade.vn/knowledge-hub/critical-risks-on-algorithmic-trading-system/*

It’s possible for [algorithmic trading system](glossary)s to make errors indeed. Although rare, mistakes can still occur at the most unexpected times. Some serious mishaps can wipe out the entire fund in a matter of seconds. It’s required to have quality risk management for a sustainable system. There are 3 main risks we found.

# Buy and Sell Loop

This is the top risk that can occur in algorithmic trading systems. When a loop of buying high and selling low occurs, 99% of an account in terms of asset value can be lost in just a minute.

Knight Capital, a market maker, lost $440 million in just 45 minutes on August 1, 2012.****A new[trading algorithm](glossary) at Knight mistakenly trades 150 stocks, buying higher and selling lower than the market price. Knight was on the brink of bankruptcy when the issue had been flagged. A loop error resulted in a disastrous loss to Knight just in 45 minutes.

# Data Error

When data errors occur, like delayed data, the trading system may start to make arbitrary decisions. It is a state in which the system makes trades not based on real-time data. It leads to serious losses and inconsistent performance system-wide. At ALGOTRADE, we use at least 3 different data sources to cross-check in real time and to minimize data errors.

# Unexpectedly Low Liquidity

Investors can suffer big losses if they only focus on the latest price and disregard liquidity with market orders. This may not impact small individual accounts; however, the effect is much larger for institutional accounts. In particular, this effect will have a huge impact on multi-algorithm trading with strategies using market orders to open and close positions in the same direction.

On May 6, 2010, the Flash Crash happened in the U.S. market. It was a stock sell-off that led to a sharp price fall in a matter of minutes. Without taking into account liquidity issues, trading orders were executed with a 60% price difference from before the Flash Crash event. It almost wiped out the entire account balances of the parties involved.

Serious risk management to avoid the instant collapse of an algorithmic trading system is extremely important and should be of the highest priority. Other risks related to computer programs such as API and connection errors may occur frequently. Yet these errors are much less likely to crash the entire system.

Iterative improvement is pivotal to enhance a system's stability. However, investors shouldn’t stress too much over small, unavoidable bugs. Even though it may open an arbitrary position, it may not always lead to loss. In fact, erroneous trading positions may still unexpectedly make profits.

---


## 04. Core Components to Build an Algorithmic Trading System

*Fonte: https://hub.algotrade.vn/knowledge-hub/what-you-need-to-build-an-algorithmic-trading-system/*

When building an [algorithmic trading system](glossary) in Vietnam, for technical analysis in the derivatives market, investors can use Entrade or third-party software such as AmiBroker and MetaTrader.

If investors need a complete system that can deploy a variety of algorithms including but not limited to fundamental analysis, multi-data (e.g. real-time oil price chart), ****or[high-frequency trading](glossary) systems, the following core components are critical.

  * **[Trading algorithm](glossary). **Algorithms are the most crucial factor. If there’s no stable profitable trading algorithm in the long term, a super-powerful system still cannot take advantage of computing power. In addition, shaping the trading strategy is a prerequisite to structuring the remaining system components. Specifically, a derivatives trading strategy works on vastly different data compared to a stock trading strategy.
  * **Database.** Database stores price, volume, account, and transaction information with financial statements. Databases are often underinvested because they have little impact on algorithmic trading systems in real scenarios while they require lots of time and energy to maintain. However, for sustainable growth, algorithmic traders have no choice but to build high-performing databases. In the long run, databases serve algorithm enhancement with research and serve as inputs to high-latency algorithms.
  * **Stock Market APIs.** APIs allow placing and canceling orders as well as retrieving account information in real-time. There are many public security companies offering API services. This promotes the development of algorithmic trading in Vietnam in recent years.
  * **Real-time Trading Data.** The trading system relies on real-time trading data to make trading decisions. In addition, these data are also stored in databases for long-term usage. In Vietnam, besides the APIs of security companies that come with data packages, investors can purchase data from providers such as FireAnt and Fialda. When building an automated trading system from scratch, investors normally use raw data from the security companies’ API because of its high coverage, low latency, and free of charge. Data provider services are most suitable for MetaTrader or AmiBroker.


All trading prototypes use programming and data terms. Programming skills are required to build algorithmic trading systems. Python is a powerful and popular programming language for algorithmic trading. C is also a top choice for investors who need high execution speed.

---


## 05. Semi-Automated Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/semi-automated-trading/*

[Semi-automated trading](glossary) is a system that uses computers combined with expert input to optimize the decision-making process. Traders are primarily responsible for the decision-making process. They process information and data that computers haven’t solved on their own, while computers bring speed, stability, and accuracy. There are many semi-automated trading systems to support investors. Let’s take a look at examples in Vietnam’s stock market from a simple to complex level.

**Stock filter** –  _Complexity: very simple._ It is a widely used application of semi-automated algorithmic trading. The trader defines a set of criteria and the system will find qualified stocks. This saves a lot of time by shortlisting the market-wide search to several potential stocks.

In Vietnam, there are misconceptions about equating stock filters and algorithmic trading. Stock filters only help to the degree of data query and give supporting information. In terms of complexity, a professional investor with strong Excel skills can build a good filter in 2 days. However, building a complete [algorithmic trading system](glossary) requires several years along with a solid understanding of database management, server administration, programming (Python, C), investment strategies, and risk and portfolio management.

**Open/close Position Schedule** – _Complexity: simple._ The investors clearly understand the market situation and what actions to take if certain market conditions are met. Constantly checking market data to wait for conditions can be time-consuming. This leads to the use of a semi-automated trading system. Some common actions in this setup are price momentum trading, stop-loss, or take-profit.

**Trading ecommendation** – _Complexity: average._ While not common in Vietnam, this approach allows systems to suggest trading ideas. It requires an investor’s approval to execute orders. It always leaves the final decision up to the traders.

**Parameter Configuration** – _Complexity: complex._ It is an algorithmic trading system where investors can interact with the system in real-time by changing algorithmic parameters. They can thus impact trading performance. The system may be fully automated using a default configuration. This setup is highly effective when expert experience is extremely valuable, or when the system is in risky situations that require human intervention.

**Multi-Asset Class rading** – _Complexity: very complex._ Even when investors have great trading ideas, like [pair trading](glossary) for example, they will have difficulties realizing the ideas without the support of an automated trading system. Thus, a predefined set of rules that allows parameter configuration will be extremely useful for investors who want to implement a pair trading strategy.

---


## 06. 09 Steps to Develop Algorithms

*Fonte: https://hub.algotrade.vn/knowledge-hub/steps-to-develop-a-trading-algorithm/*

Building a fully automated trading system that is profitable and stable is the first challenge in this field. There are 9 steps to develop a trading algorithm as follows.

## 1\. Forming Algorithmic Hypotheses

Traders begin to develop an algorithm according to familiar investment strategies or market assumptions that will likely bring profits. This step is to break down a trading strategy into a set of statements that execute trading logic to make buy or sell orders. These orders have key information like the order type, price, and volume.

After suggesting the trading algorithm, it’s possible to move on to real trading. However, it would be extremely risky and can be a game of chance. To limit the risks, testing phases are required especially with large accounts.

## 2\. Data Collection

In most cases, basic data would satisfy the needs of algorithm development. However, for complex algorithms that may require tick data, financial statements, macroeconomic indices, commodities, or ETF indicators, traders need to collect data before implementing the algorithm.

Around the world, data collection has gone so far as using satellite images to estimate cars in a parking lot, or to estimate the number of sheep on a farm to predict business outcomes. This goes hand in hand with algorithm development to seek profits.

## 3\. Data Processing

This stage requires lots of effort to ensure that collected data is not duplicated. It also removes data outliers and structural errors to ensure sufficient quality data to develop algorithms.

Suppose investors in Vietnam would like to calculate the correlation between PVD shares and crude oil prices. After collecting oil price data, it is necessary to synchronize the time of world oil data with Vietnam time, adjusted for public holidays and any time zone difference. This is a simple example of the data processing operation.

## 4\. Backtesting With In-Sample Data 

Backtesting evaluates whether the trading algorithm is profitable. A correct method of testing on the historical in-sample data will give a reasonable expectation of its performance. It also helps understand the algorithm risk in the future.

To test past data, the first step is to divide this dataset into two parts, 70% and 30% of the dataset. The former is called in-sample data and the latter is out-of-sample historical data.

The in-sample data is used to evaluate the trading profile of the algorithm. The core metrics include profitability, maximum drawdown, and Sharpe ratio. Note that an algorithm requires at least 300 transactions to ensure these metrics are statistically significant. Testing on past data should also include taxes, fees, slippage, and any other trading costs incurred.

After estimating the parameter, if the performance is unsatisfactory, return to step 1 to propose a different hypothesis. Otherwise, the process can move to the next step

## 5\. Optimization

In this stage, investors make necessary adjustments to algorithm parameters to find the values that optimize the algorithm’s efficiency in the targeted market. It is necessary to test hundreds of different sets of parameters until a stable area is found. It is important to avoid [overfitting](glossary), that is the set of parameters only yields good returns in the past but will unlikely be the same in real trading.

In Vietnam, many focus on finding a set of parameters with optimal profit results in past data to attract and sell trading algorithms to customers. Investors who buy and trade according to these algorithms have no idea they are in a highly risky game.

## 6\. Backtesting on Out-Of-Sample Past Data

After the optimization phase, traders continue to test the remaining 30% out-of-sample data from step 4. This process tests whether the post-optimization algorithm can generate stable profits. If the performance is similar to that of step 5, it’s likely a good algorithm with strong potentials. Otherwise, investors should be cautious if they want to proceed.

## 7\. Paper Testing

This stage tests the algorithm on completely unknown market data. The data comes from real data at the present until a certain point in time in the future. It is to objectively evaluate the algorithm’s performance. If it is similar to that of step 6, investors can move to the next stage of testing on small accounts.

## 8\. Small Account Testing

After the 7 stages above, it’s now possible to deploy the algorithm on a small account to test the performance, as well as the algorithm hypothesis during real trading. This stage also finds possible technical bugs and compares the result with the paper trading stage to make any adjustments if necessary.

This period usually lasts 2 months to have a large enough number of transactions and a long enough time to assess the stability of the [algorithmic trading system](glossary). If the performance profile is still consistent with that of previous stages, investors now have confidence and scientific grounds to apply to real trades.

## 9\. Real Trading 

At this point, investors can confidently let the algorithm trade at maximum capacity. In the early times, it’s necessary to monitor the operation and fix any technical bugs that may arise. After 3 months, investors can officially launch a new trading algorithm if the operation proves stable.

Don’t forget to get a cool and catchy name for your brand-new trading algorithm!

---


# II. PROPOSE AN ALGORITHM HYPOTHESIS


## 07. Distinction between Two Types of Algorithms

*Fonte: https://hub.algotrade.vn/knowledge-hub/distinguish-two-algorithmic-trading-categories/*

An investment process always consists of two stages: making buy/sell decisions and executing these orders. Depending on applications, we can classify algorithms into two types: profit-seeking algorithms and execution algorithms.

## Execution Algorithms 

As the name suggests, these algorithms are used in execution orders to take advantage of computer systems. It is used to optimize the trading price. These algorithms are for high-volume trading and aim to avoid market fluctuations.

Here are the common groups of execution algorithms:

  * Scheduled algorithm: POV, TWAP, VWAP;

  * Liquidity seeking algorithm;

  * Arrival price algorithm;

  * Dark strategy/liquidity aggregators;

  * Smart order router algorithm.


## Profit-Seeking Algorithms

Over the development of financial markets, profit-seeking algorithms have become more and more diverse. These algorithms all have the same goals to determine which securities to buy or sell, when, and in what volume to maximize profits.

The rules of this group are unified throughout the process from decision-making to order execution. The computer system will automate this process without human intervention.

The ultimate goal of investing is to increase profits. Investors pay more attention to the profit-seeking algorithms than the execution algorithms. However, it’s not easy to find profitable algorithms among thousands of options and a complex changing market landscape. Therefore, in reality profit-seeking algorithms are still on a small scale though they get much attention. In contrast, the group of execution algorithms is less well-known but easier to implement and more stable. In fact, this group is often used on a large scale by investment funds and professional investors.

Note that in the following, referring to “trading algorithms” or “algorithms” without further explanation can be understood as referring to profit-seeking algorithms.

---


## 08. Execution Algorithms to Optimize Trading Fees

*Fonte: https://hub.algotrade.vn/knowledge-hub/transaction-cost-reduction-execution-strategy/*

The execution price of a stock is determined daily by the rules of supply and demand. At any given time, if an investor executes an order to buy or sell shares in too large of a volume compared to normal liquidity, it will immediately create an imbalance of supply and demand. The stock price in the short term will move in an unfavorable direction to the investor. Specifically, when placing a high-volume buy order, the market price will increase, resulting in a higher average execution price than expected; and vice versa when selling in a large volume.

The larger the volume compared to the stock liquidity, the larger the impact on the market price in the unfavorable direction. For example, an investor places buy orders for stock A and stock B, at 1 million shares. However, the daily liquidity of these two is different (table below):

While the volumes are the same, stock A has higher liquidity. So the buying order from stock A has less impact on the market price. The order to buy stock B is likely to have a big impact and increase its market price.

# Why Large Volume Impacts the Market

When a high-volume buy and sell order enters the market, market participants are likely to believe that the market has key information that they are not aware of. They will then revise the price they are willing to buy or sell to reflect this unknown information.

To limit the market impact in an unfavorable direction, when trading in large volumes, investment funds and investors execute orders by dividing large orders into several smaller ones. They also execute orders at various times to minimize market impact. Commonly used execution algorithms include:

  * [POV algorithm](glossary) (percentage by volume);

  * [VWAP algorithm ](glossary)(volume-weighted average price);

  * [TWAP algorithm](glossary) (time-weighted average price).


For retail investors, these strategies may be of limited value. However, for large investment funds and investors, the application of execution algorithms is of great significance. It’s no less than the efforts to find value stocks or to manage portfolio risks.

# POV Algorithm 

This algorithm executes orders at a predetermined percentage of market liquidity until reaching the target volume. As the trading volume in the market increases, the algorithm will trade more stocks and vice versa.

For example, investors like to buy 5 million FPT shares with the POV algorithm at a rate of 10%. For every 10,000 FPT shares traded on the market, the algorithm will buy 1,000 shares until reaching 5 million.

The advantage of this algorithm is that it keeps the volume of buy orders in the market depending on the current liquidity of the market (around 10% as in the example above). Thus it minimizes the impact on market prices.

The main disadvantage of this algorithm is that it’s possible investors will not complete the trade within a specified period of time, especially in unfavorable market liquidity. In the example above, the historical liquidity of FPT at the time of writing is 2.5 million shares a day. It would then take 20 days to buy all 5 million shares if the liquidity stays constant.

However, at unfavorable times, market liquidity can drop to half . It may take up to 40 days for the algorithm to complete. This leads to the risk that the fair market price has increased significantly from the expectation.

VWAP and TWAP algorithms can solve the problem above. They both calculate to divide the stock volume into small orders to trade and place these orders on a predetermined schedule. They ensure the algorithm is completed within a specified period of time, such as buying 5 million FPT shares completed in 20 days.

# VWAP Algorithm 

This algorithm breaks down and puts orders into the market in different time frames. The volume is calculated based on historical data. The challenge is that the historical liquidity data may not always repeat itself in the future. There are time frames with high trading volume in the past but this may not happen again in the future.

# TWAP Algorithm

This algorithm breaks down and puts orders into equal parts and places them into the market at regular time periods (normally spaced 5 minutes apart). It should be noted that investors should split orders small enough to ignore market liquidity impact. It’s because this algorithm does not include the liquidity factor in the calculation. Its goal is to complete the transaction within the specified time period.

In Vietnamese, investors can see this algorithm is widely used on blue chip stocks. They are traded with a volume of fewer than 1,000 shares every 2 seconds.

---


## 09. 06 Components to Build a Complete Trading Algorithm

*Fonte: https://hub.algotrade.vn/knowledge-hub/elements-of-a-complete-algorithmic-trading-strategy/*

In addition to two main components of position entry points and take-profit points, a trading algorithm also decides stop-loss points, target markets, position sizing, and trading tactics. 

## 1\. Position Entry Point

The entry point is the minimum requirement of any [trading algorithm](glossary). Note that having an entry point does not mean the order is successfully executed. In many trading strategies, the fill rate can be under 10% in real trading.

## 2\. Take-Profit Point

After the entry point, the timing or condition to take profits and rebalance portfolios is the next required condition for all algorithms. In certain special cases, the algorithm can take profits according to the time function, not the profit function. The profit would be more random in these cases.

## 3\. Stop-Loss Point

Most algorithmic trading strategies should have stop-loss points while a few do not require them. In reality, it’s likely hard to accept losses as a prevailing sentiment is “not cutting losses is not losing”. However, with this mindset, investors can fall into the trap of winning lots of small pots but ultimately losing money in the entire process. This phenomenon is common in the mean-reversion and scalping strategies.

## 4\. Target Market – Which Stocks to Buy/Sell 

Experienced traders mostly trade in their familiar sectors. Every security has its own characteristics, formed by the impact of stakeholders. Since it attracts different groups of investors, funds, and traders, we never assume different securities work in similar ways. Any algorithmic trading strategy can follow this philosophy instead of a one-size-fits-all approach.

## 5\. Position Sizing – How Much to Buy/Sell

In Vietnam, 95% of algorithm execution does not consider position sizing but buys or sells the entire account as soon as a position is opened. This may be due to small account size, or technical limitations of third-party software that do not allow position sizing to be adjusted. However, to allow multi-algorithm trading on the same account, it’s necessary to take position sizing into account. Otherwise, buying or selling the entire account likely leads to systematic collapse within 03 years.

## 6\. Trading Tactics – How to Buy/Sell

It’s an enhanced version of using market orders in all situations to limit slippage costs. They greatly affect system-wide performance, especially for large accounts. Instead of using market orders, algorithms such as VWAP, TWAP, or POV can be used. In our system, ALGOTRADE uses an enhanced [POV algorithm](glossary) that allows [high-frequency trading](glossary) when there is a price advantage.

---


## 10. Differences Between Equity and Derivative Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/key-differences-between-algorithmic-trading-in-equity-market-and-derivatives-market-in-vietnam/*

The number of investors using [algorithmic trading system](glossary)s in Vietnam is still limited. As an estimate, 98% of algorithmic trading systems in Vietnam operate on the derivatives market (VN30F futures contracts) but not on the equity market. This is due to fundamental differences between the two markets as follows.

# Time to Complete Transactions

Differences in completion time explain why more than 60% of algorithmic trading prefers derivatives markets to stock markets. This can be understood as the algorithmic trading system that can trade at high frequency in the derivatives market. It’s rather limited in the stock market since the wait time takes up to 1.5 days to sell.

# Database Complexity 

Most derivatives trading algorithms use technical analysis that includes only price and volume data. They are easy to collect and organize into a database.

In contrast, trading algorithms on the equity market use fundamental analysis, which requires full financial statements from all listed companies in Vietnam. They include income statements, balance sheets, and cash flow statements. These reports usually have different structures when it comes to company types, like insurance, security companies, conventional companies, or even banks. Databases in the equity market have specific requirements in the data structure, query speed, data cleaning, etc. The database complexity is much higher in the equity market compared to the derivatives market.

Note that when using multivariate algorithms, the database gets even more complex. These algorithms require more types of data besides financial statements.

# Fees and Taxes

Taxes and two-way transaction fees in the derivatives market are only about 30% of the stock market, excluding price slippage. From this perspective, the derivatives market looks more attractive to investors. However, in the long term, trading in the derivatives market may incur higher fees if investors opt for high-frequency trades. There’s no daily transaction limit in the derivatives market.

In summary, there are three main differences between algorithmic trading in the equity market and in the derivatives market as follows:

For most algorithmic traders, the derivatives market is more attractive due to the three main differences above. However, at Algotrade, we are working on algorithmic trading for both markets, as fundamental analysis proves to be highly valuable. There are also opportunities for market-neutral strategies that combine both markets at the same time for higher efficiency.

---


## 11. How to Construct an Algorithm Hypothesis

*Fonte: https://hub.algotrade.vn/knowledge-hub/guide-to-formulate-an-algorithm-hypothesis/*

Without a proper understanding of algorithmic hypotheses, it can be costly to waste time in subsequent stages without meaningful return. Finding a good algorithm may take a few years, even though forming one only takes minutes. A beginner in algorithmic trading will fail 99.5% of the time. Increasing the success rate from 0.5% to 10% is already a great success. This section demonstrates how to improve the success rate of an algorithm hypothesis.

# Master Foundation Knowledge

  * **Data.** Input data is a prerequisite to any algorithm. It plays an important role in forming an algorithm hypothesis. For instance, limiting input data to price and volume will force [algorithmic trader](glossary)s to have technical analysis as the only choice.
  * **Strategy.** The investment strategy must be concretized into a set of principles that must be followed when making trading decisions. It decides what securities to buy or sell, what type of order, when and what price, and in how much volume. For any investment strategy, the overall goal is to generate the highest possible return with the lowest risk. Understanding the risk-return trade-offs will enhance your chance of building a successful [trading algorithm](glossary). ****Don’t focus too much on a single strategy. In fact, the majority of algorithmic traders only focus on the price momentum strategy because it is easy to program and execute. Imagine what would happen if 99% of traders share the same strategy?

Multiple strategies will limit risks in the long term. Articles 12 to 23 detail common trading strategies. Algorithmic traders can refer to these strategies to develop their own trading algorithms. They can be tailored to individual tendencies to become more effective.

****
  * **Individual tendencies.** Every trader has their own personality tendencies. Some prefer safety to high risks with high returns. Some are willing to bet their entire portfolio on a few positions, instead of dividing them into smaller orders to lower risks. Some focus only on [high-frequency trading](glossary) strategies, expecting to find profits in the short term while ignoring long-term strategies. 

Algorithmic traders may suffer from emotional discomfort when downplaying their individual tastes when forming algorithm hypotheses. It’s because trading algorithms can operate wildly differently from their own personality. Understanding emotional tendencies will make the journey much simpler. For example, an algorithmic trader with low-risk tolerance who follows a price momentum strategy will find it difficult to stay calm with temporary losses. They often elect to intervene at unnecessary moments.

****


# Real Market Experience

Proposing a good algorithmic hypothesis often comes from an already effective approach in discretionary trading. Personal trading experience with both wins and losses is always valuable for algorithmic hypotheses. This source of information is irreplaceable since it comes from real experience. Knowledge from books and training courses is helpful but still cannot replace real trading. Thus algorithmic traders should take experience from decision-based trading, especially in the beginning. Ten years of market ups and downs will form a solid foundation for any investor.

# Learn Proven Successful Trading Strategies 

There are countless publicly available trading examples and strategies for free. Compared to a brand new, unproven high-tech strategy, investors can increase success rate based on proven trading strategies. Here are some examples:

  * Warren Buffett’s investment philosophy on value investing on undervalued stocks.

  * Passive investment in SPY.

  * International arbitrage business.

  * Market makers in commodities and forex markets.


Examining the potential of an algorithm hypothesis before the start of the testing phase will save a lot of time and effort. It also increases the success likelihood at the next stage of algorithm development.

---


## 12. Trading Strategy Overview

*Fonte: https://hub.algotrade.vn/knowledge-hub/algorithmic-trading-strategies/*

Trading strategies are one of the core components of an algorithmic trading system. Without stable, profitable strategies in the long term, an automated system cannot take advantage of the computing power. Even though different strategies may work in different markets, there are major groups of investment strategies below.

**Market Neutral**

Market neutral is a group of investment strategies undertaken by an investor who simultaneously opens long and short positions in order to minimize market risk on portfolio returns.

Pair trading is a simple and common form of market-neutral strategy.

Statistical arbitrage is also a group of market-neutral strategies that evolved from****[pair trading](glossary). It uses mathematical and statistical models along with computer assistance to make the most of trading opportunities. They may come from abnormal changes in the relative price of one stock compared to another. Statistical arbitrage is difficult for retail investors to access, and ALGOTRADE is making continuous efforts to close the technology gap for these investors.

**Price Momentum.**

Investors look to buy rising stocks or short-sell falling stocks. This strategy believes that stocks continue to follow the momentum in the short term.

During the Covid years, this was the most widely used strategy in Vietnam. There’s no guarantee, however, this approach will continue to be effective in the long term.

**Mean Reversion**

This strategy assumes that if a stock’s price is too low compared to its intrinsic value, investors should buy and vice versa. In some cases, the intrinsic value may be replaced by the technical mean.

[Event-Driven Trading ](glossary)

Event-driven trading strategies take advantage of market inefficiencies from corporate events like mergers and acquisitions, corporate restructures, share buybacks, extraordinary dividends, etc. to trade in the short term. Investors study the situations surrounding these events and assess how they will impact the stock price. They identify potential opportunities that may arise and take advantage of them.

[Market-Making ](glossary)

This strategy commonly places orders at the best bid price and the best ask price. It makes profits from the bid-ask spread.

[Scalping ](glossary)

It is a special strategy that focuses on an ultra-short time frame to open and close positions in order to make very small profits. Scalping traders make a lot of transactions daily and expect a very high success rate.

[Front-Running ETF S](glossary)

Investors anticipate the action of exchange-traded funds (ETFs) according to the public prospectus and simulate part of the action prior to the fund’s rebalancing.

**Arbitrage**

Arbitrage is a strategy that takes advantage of a temporary difference in the price of the same asset in two different markets. This strategy trades to make a profit without incurring too much risk.

**Grid**

This strategy sets up a price grid around a predefined value to make profits from market fluctuations. It works best in an oscillating market with large swings, though having a big risk in trending markets.

[Smart-Beta ](glossary)

Known as a factor-based strategy, this strategy builds portfolios according to rule-based processes. It uses business factors like liquidity, value, and quality as criteria for making trading decisions. It is not widely used yet because it’s necessary to establish an automatic connection to the financial data of all companies in the market.

**Sniffing**

This strategy relies on real-time transaction data to track the actions of individuals or organizations with large trading volumes. It assumes that these actions will last for days or weeks, and information advantage will ultimately generate significant profits.

---


## 13. Market-Neutral Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/market-neutral-strategy/*

# Definition

**Market neutra** l is a group of investment strategies undertaken by an investor who simultaneously opens long and short positions in order to minimize market risk on portfolio returns. It’s useful when investors want to remove market volatility from portfolio returns to focus on forecasting stock returns. This strategy has two main characteristics:

  * Can yield profits regardless of whether the market rises or falls;

  * Open opposite directions simultaneously with equal market risk.


In the stock market, investors often use beta from the Capital Asset Pricing Model (CAPM), as a measure of systemic risk. In this context, a [market-neutral](glossary) portfolio is defined as a portfolio with a beta of 0.

Pairs trading is a simple and common form of market neutral. The purpose of a [pair trading](glossary) strategy is to look for stock pairs that have a highly correlated price history. When the price correlation of two stocks deviates from the long-term average, investors buy stocks that are underperforming while selling stocks that are outperforming. They expect that this deviation is temporary. When the price correlation of two stocks converges to the expected average, investors close positions to realize profits.

**Statistical Arbitrage (StatArb)** also a group of market-neutral strategies that evolved from the pair trading strategy. It uses mathematical and statistical models along with computer assistance to make the most of the trading opportunities. These opportunities come from abnormal changes in the relative price of one stock to another.

In terms of classification, the****[statistical arbitrage strategy](glossary) group includes pair trading. Pair trading can be considered a statistical arbitrage strategy. However, statistical arbitrage is not exactly pair trading. With the help of computers, statistical arbitrage strategies can combine buying/selling two portfolios with hundreds of different stocks. At that time, investors will select potential stocks and rank them according to relative valuation criteria. Then they buy “relatively cheap” stocks while selling “relatively expensive” stocks.

# Examples of Market Neutral Strategies

Suppose the investor has just analyzed and selected a portfolio of 5 stocks in VN30 as follows: FPT, HPG, TCB, VIC, VPB (referred to as “VN05”). Investors predict in the future, the VN05 portfolio will be better than the general market. As a benchmark, the general market is the VN30 index. They decide to invest 600 million VND according to the market-neutral strategy as follows:

  * Buy 500 million VND in VN05;

  * Deposit 100 million VND to open 5 short positions simultaneously (assume VN30F1M index is 1,000; margin is 20%; and VN30F1M price changes entirely correlated with VN30 index score).


Assume the VN05 portfolio has better performance than the general market. If the market increases, VN05 increases more. And conversely, if the market falls, VN05 falls less. Excluding fees and taxes, assume 2 market scenarios with investment results as follows:

If the market rises, VN30 increases. The short position on VN30F1M incurs a loss. However, investors expect the VN05 portfolio to increase stronger than VN30 (12% vs 10%). The profit from the VN05 portfolio offset the entire loss from the short position. The final profit is 10 million VND.

Conversely, if the market falls, the VN05 portfolio incurs losses. However, the investors expect VN05 to fall less than the market (say -8% versus -10%). At the time, the profit from the short position offsets the entire loss from the VN05 portfolio. The final profit is also 10 million VND.

# Strengths of the Market-Neutral Strategy

As in the example above, with the market-neutral strategy, investment results depend primarily on selecting the right stock portfolio with better potential than the market average. It’s not dependent on accurately forecasting short-term price movements. Using this strategy, investors only need to focus on researching, understanding, and choosing a good portfolio of stocks with solid fundamentals. The portfolio should have high-profit potential in the long term, not worrying about short-term market fluctuations. Short-term events appear very random, and difficult to predict properly. They can only be perceived when they have occurred, and there’s no time to act at such moment. In addition, it saves a lot of time and effort from monitoring the market and daily fluctuations.

---


## 14. Price Momentum Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/momentum-strategy/*

# What Is Momentum?

In the stock market, stock prices always change due to the impact of supply and demand. When demand is greater than supply, the price starts to increase, and vice versa. There are several reasons why supply and demand are always changing. Common ones include positive macro impacts, good business news, and cash flows from new investors. These fundamentals give the stock incentive to rise in the beginning when demand outweighs supply.

Investment analysts observe that once a stock starts to rise, the bullish momentum will continue to stay the same for a certain period of time before stopping or turning bearish. This process is similar to throwing a coin vertically into the air. When the initial force is stronger than the earth’s gravity, the coin begins to accelerate and move upwards in the first few seconds. With momentum, the coin continues for another period with decreased speed before falling down. This analogy leads to a common term in physics “momentum” to be applied to finance.

Price momentum in finance is the rate of increase/decrease in a security’s price over a period of time. It’s also known as the rate of price change and is used to measure the strength of a trend.

In algorithmic trading, **the momentum strategy** buys rising stocks and short-sells falling stocks. It argues that stocks tend to keep following the trend in the short term. This argument comes from the belief that once the trend is established and there is sufficient momentum, it will continue to last a brief period of time for scalping to take profits.

In short, the main purpose is to buy stocks when the price has risen and sell when the price rises even more. Buy high and sell higher. The opposite of this strategy is the mean-reversion strategy. It buys stocks that are too low compared to their intrinsic value, or average value, and vice versa. Buy low and sell high. This strategy will be discussed in the next article.

# Causes of the Momentum Effect 

There are two plausible explanations for this effect. The first comes from studies of behavioral finance related to investor biases. Investors often overreact to information and events, leading to an increase in strength and prolonging trends.

The second is that investors receive and process information at different reaction times. When there’s a positive event, early investors realize the potential of the stock and start buying. It initiates the price trend to start moving upward. Some other investors slowly realize the opportunity but still have high expectations and decide to buy at a higher price. They maintain the uptrend. Both have positive expectations but different action timing, resulting in an uptrend that may last for a brief period of time before stopping and reversing.

# Investment Risks in the Price Momentum Strategy

This trading strategy works on a basic assumption: when a trend appears, it will last for a sufficient period of time to take profits from corresponding positions. However, in practice, there’s no guarantee this assumption always holds true.

Daily events and news directly affect investor psychology and expectations. They create changes in supply and demand, initiating trends. However, at the same time, investor sentiment also changes unpredictably during this brief period. A newly started uptrend can be short-lived when later macroeconomic news negatively impacts investors’ sentiment in the whole market.

---


## 15. Mean-Reversion Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/mean-reversion-strategy/*

# Foundation of the Mean-Reversion Strategy

Large corporations in fact cannot change radically in a short time frame such as daily, weekly, or even monthly. However, the market value from stock exchanges is never stable. For many reasons stock prices often fluctuate erratically just within a day. Sometimes they are close to the intrinsic values while other times they are far apart.

Investors pursuing this strategy assume that the stock price will approach the intrinsic value in the long run. Thus when the market price is too low relative to its intrinsic value, investors should open a long position and vice versa.

The figure above is an example of FPT corporation’s share price for two months, from March 2022 to May 2022. Assuming the business hasn’t undergone any major changes over the time period, investors who follow the mean-reversion strategy will look for opportunities through the difference between the stable intrinsic value and 30% moving market price.

# Intrinsic Value in the Mean-Reversion Strategy

The mean-reversion strategy is intuitive for many investors. It encourages buying a stock when it’s cheaper than its intrinsic value and takes profits on an already overvalued stock.

How does an investor come up with an intrinsic value? It’s beyond the scope of this article, though there are theoretical formulas to calculate intrinsic value. In practice, estimating this value requires significant domain knowledge. In this strategy, intrinsic value will shape the investor’s perspective on any investment opportunity. The following is a suggested action for the example above of FPT with different estimates on intrinsic value:

Completely different actions under the same market are the effects of estimating different intrinsic values.

In short, to master the mean-reversion strategy, investors need to have skills related to estimating the mean, or the intrinsic value.

# Investment Risks of the Mean-Reversion Strategy

Although companies often change slowly, it’s not the only factor impacting intrinsic value. Any change in macroeconomics, global markets, government policies, business lines, and competitors can have a major impact on a company’s intrinsic value. Misestimating the intrinsic value can lead to buying shares at a too high price while selling shares at a too low price.

The biggest risk in a mean-reversion strategy is that after years of research, the investor may never find the right approach to calculating intrinsic value.

---


## 16. Event-Driven Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/event-driven-strategy/*

# Definition

**Event-driven strategy** is a strategy to find profits from misestimating company prices at major events such as mergers and acquisitions, bankruptcy, share buyback, capital restructuring, extraordinary dividend payments. Investors will study their circumstances and assess how they will impact the company’s stock price. They identify potential opportunities that may arise and take advantage of them.

The strategy's effectiveness depends greatly on the investor’s ability to capture information, analyze, and evaluate.

More recently, the event-driven strategy has also included pricing after major global macro changes or natural disasters in different regions.

# Example of Event-Driven Strategies in Merger and Acquisitions

Arbitrage trading involving mergers and acquisitions (M&A) activities is one of the popular examples of an event-driven strategy.

Hypothetical scenario: merger and acquisitions with cash payments. Buyers propose buying shares of a target company at a fair price (bid price) and the price is higher than the market price.

Trading strategy: if you believe that the deal will go as announced, you will buy the shares of the target company and sell when the deal closes.

# Example of Event-Driven Strategies in a Global Macro Event

As the Russia and Ukraine war continues to drag on, investors who have information that Russia and Ukraine are major wheat exporters in the world will see a short-term decline in supply. It creates an upward demand for wheat and rice producers. Investors can take advantage of this opportunity to make a profit.

The positive stock movement of Vietnam Seed Group (HOSE: NSC) in the market downtrend may have partially reflected this event.

# Event-Driven Strategic Risk

Incorrect pricing of the event impact is the most common cause of losses for investors using this strategy. In addition, a less common but potentially huge cause of losses is third-party interference. In an event-driven strategy, third parties can be very powerful organizations such as the U.S. or Chinese governments. Actions that can change an investor’s entire calculation include policy changes, releases of strategic reserves, embargoes, etc.

In addition, there are unexpected internal events. For example, M&A events cannot take place due to a few reasons: shareholders of the target company do not approve, and the security and exchange commission does not approve and does not grant licenses. Another example is that the deal got approved, yet needed time for the completion of legal procedures. When the shares got converted and allowed to trade, the price fell again and investors no longer made profits.

---


## 17. Market-Making Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/market-making-strategy/*

# Definition

**The[market-making strategy](glossary)** simultaneously opens positions at the best buy and sell prices in order to seek profit through the spread. The profitability of market makers comes from the assumption that securities match in both buying and selling directions. Investors may suffer large losses if there’s only one-way order execution. It’s when they hold too many positions in the opposite direction when the stock price moves in an unfavorable direction.

In Vietnam, market makers are often misunderstood as market manipulators. Manipulators are a group of investors coordinating with each other to continuously buy and sell securities. They create artificial supply and demand, and at the same time spread false rumors. They provide false information to the public, enticing others to continuously place orders to manipulate stock prices.

Market makers essentially benefit from bid-ask spreads. It creates more liquidity in the market. In some markets, this additional liquidity is paid by the security companies or related parties. In most other cases, market makers have enough profits from the spreads.

# Market Maker in Vietnam

Market makers in Vietnam can consider two key directions:

  * _Participate at the best bid and ask price._ The condition of execution is (sell price - purchase price) > costs. The condition is rare in the Vietnamese market. However, it happens quite often on days with high volatility.

  * _Set an optimal bid and ask price based on algorithms._ In this approach, the maker will increase the profit margin but the number of matches will be greatly reduced. This is an approach with a higher success rate in Vietnamese.


To implement a market-making strategy in Vietnam, investors should note the following two points:

  * With the T+1.5 regulation in the underlying security, the market maker needs to have a position available to be able to place a sell order simultaneously with a buy order. With the T+0 trading feature, it’s simpler to implement a market-making strategy in the derivatives market.

  * Market makers need an automatic, stable, high-speed order system to executive orders, and cancel orders continuously according to each market movement.

---


## 18. Scalping Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/scalping-strategy/*

# Definition

**Scalping** is a strategy that specifically focuses on short time frames for closing and opening positions in order to make small profits. Scalpers often make a lot of trades on a daily basis and expect a very high win rate.

# Forms of [Scalping Strategy](glossary)

There are three popular forms of scalping strategy in the market:

  * _Scalping as market makers_. Investors order to buy and sell a security at the same time. This action is intended to profit from the difference between the buy and sell prices. This strategy has the best results for stable and high-volume stocks.

  * _Scalping as investors_. Scalpers buy in bulk stocks with a strong foundation and wait for the price to move. In Vietnam, with high fees and the T+1.5 rule, scalpers often take a profit when it reaches 2%.

  * _Scalping following technical analysis patterns_. In this approach, scalpers wait for a certain pattern to appear to open positions and expect quick profits. This approach often takes profit and stops loss at equal levels. Investors only focus on the /loss ratio.


# What Investors Need for a Scalping Strategy

In addition to the strategy, investors need a stable platform to place thousands of orders daily. In addition, good data sources are essential to make accurate decisions.

In Vietnam, a stable application programming interface (API) gives investors direct access to a stock brokerage company. It’s required for investors who want to execute scalping strategies in the derivatives market.

This strategy brings quick profits so it will attract a large number of investors. However, this strategy is not an easy way to make profits. Investors should note the following important factors:

  * Without proper risk management, a large loss may wipe out the profits from hundreds of successful trades.

  * Transaction costs are key. With scalping, the profit per trade is usually very thin. It may not be enough to compensate for fees and taxes. Minimizing transaction costs should be taken into account to increase the likelihood of success.

  * Liquidity and volatility will greatly affect investment performance. This strategy has high-profit potential when the market sharply fluctuates.

  * This strategy takes a lot of time and effort in the case of manual trading.

---


## 19. ETF Front-Runner Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/front-running-etf-strategy/*

# Definition

Every public fund must publish an investment prospectus. Index funds must publish details of rebalancing rules. By following these disclosure rules, investors may forecast the next actions of these funds and make a profit by acting ahead.

In the United States, investors following this strategy pocket about $4 billion yearly. The researchers also found most US index funds announce their rebalancing plans in advance. They execute trades at closing prices on index rebalancing days to minimize discrepancies.

The ETF front-runner is a very short-term strategy. To optimize the use of capital, it is necessary to combine it with other strategies. However, this strategy requires constant trading, so fees and taxes can increase multiple times.

In a bearish market, any strategy of taking long positions can incur serious losses. To hedge against market risk, one can consider using a market-neutral strategy. It typically combines buying underlying securities with short-selling derivatives with equal weighting.

# Ideas to Apply in Vietnam 

Among index funds in Vietnam, DCVFMVN DIAMOND ETF (FUEVFVND) is the best-known fund with the fastest capital growth in recent years. In the DIAMOND ETF prospectus, the fund’s investment objective is to track the DIAMOND index. Therefore, when it’s possible to forecast a new list of stocks added to the DIAMOND index, investors can make large profits without much risk. It’s because the DIAMOND ETF will likely buy many of these stocks.

Below are a few rules for stocks to be selected in DIAMOND INDEX (2022):

  * Have at least 3 months of listing and trading on HOSE as of the closing date of index periodic review;

  * Adjusted capitalization free-float value of at least 2,000 billion VND;

  * The minimum execution value at 8 billion VND and the trading volume at least 100,000 shares (for shares already in DIAMOND Index from the previous period) or 10 billion VND and 200,000 shares (for shares outside of DIAMOND index from the previous period) to be eligible;

  * The number of stocks in the index is at least 10. FOL of VNDiamond stocks in the previous period is at least 80%, where FOL is defined as: FOL = Foreign investor ownership/Foreign investor holding limit 


  * Stocks in the previous period with P/E at most 3 times the average P/E. For stocks outside of DIAMOND index, P/E is at most 2 times.

  * The proportion is at most 40% for a single industry.


By statistically using the complete set of rules in the prospectus, investors can accurately predict the list of stocks in the DIAMOND Index. Large securities companies like SSI JSC, or VNDirect JSC often make their own predictions. Following and forecasting their reports in advance will optimize profits for a trading system.

---


## 20. Arbitrage Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/arbitrage-strategy/*

**Arbitrage** is a strategy that takes advantage of temporary price differences of the same asset class in two different markets. It trades and takes profits without incurring much risk. Investors implement arbitrage strategies by buying assets in a lower-priced market and simultaneously selling them in a higher-priced market.

Arbitrage strategies are closely related to efficient market theory. This theory states that the market is perfectly efficient when all past and present information regarding the asset is quickly and reasonably reflected in the market price. In other words, efficient markets will allow no opportunity to take advantage of arbitrage trading.

However, for many reasons, subjective or objective, there are always periods of inefficiencies in the real market. That’s why the arbitrage strategy is widely used, and probably one of the oldest trading strategies in existence.

# Two Main Characteristics of Arbitrage Strategies 

_Only trade when there’s an imbalance in asset price_. This is the most important condition of arbitrage trading, which can take several forms:

  * The same asset but being traded at different prices on two different markets; or

  * Two assets have similar future cash flow expectations but are trading at different prices.


_Only trade simultaneously._ The buy and sell transactions must take place at the same time. The investor may be exposed to significant risk if there is too much difference in the timing.

# Arbitrage Trading in Practice

Arbitrage strategies almost don’t exist in the Vietnamese stock market. Arbitrage opportunities are more evident in the foreign exchange and cryptocurrency markets and in stocks traded over two markets, like the US and European markets.

In modern finance, arbitrage opportunities often do not exist for individual traders but only for international banks. They can continuously use and convert different foreign currencies.

An example in the modern economy of arbitrage is Bitcoin in South Korea versus the rest of the world. In 2017, the bitcoin price in South Korea was 50% higher compared to the rest of the world. Individuals/organizations who can buy and sell continuously legally may make extremely large profits without risks. However, most were unable to take advantage of this one-off opportunity although they were aware of it.

In Vietnam, the cooperation between the State Securities Commission of Vietnam (SSC) and the NYSE to develop a mechanism for investors to participate in the two stock markets was signed in May 2022. This can open up arbitrage opportunities in both markets. It is a potential project for small investors although major banks around the world dominate the field.

# Barriers to Entry in Arbitrage Strategy

The development of trading systems, along with algorithmic trading leads to the extremely short occurrence of arbitrage trading opportunities. Sometimes they can last for just a few seconds. In this context, the traditional method of placing orders will find it difficult to seize the opportunity and trade on time. However, in terms of the overall market, the more the transaction speed improves, the more efficient the market will be.

Despite arbitrage trading opportunities, the price gap is also a key factor. An investor only makes a profit if the price difference can cover the trading fees and costs.

---


## 21. Grid Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/grid-strategy/*

The grid strategy can make a profit in an oscillating market. However, it may have a big risk in trending markets.

# Definition

**Grid strategy** sets up a continuous price grid of buying and selling at predetermined prices to gain profit in any market. This strategy works best in an oscillating market with large swings.

The following is an example of a neutral grid setup on FPT corporation’s stock: the starting reference price of the grid is 87,200 VND. The grid step is 800 VND and the take-profit price step is also 800 VND.

# Grid Type 

  * _Neutral grid_. This grid works best in oscillating markets. The grid starts with zero positions and accumulates long positions if the market goes down, and short positions if the market goes up.
  * _Uptrend grid (bull market grid)._ This grid works best in bull markets. The grid starts with several long positions instead of no positions.
  * _Downtrend grid (bear market grid)._ This grid works best in bear markets. The grid starts with several short positions instead of no positions.


# Important Parameters

  * _Trading price range._ The highest price and lowest price of the grid.
  * _Grid._ The distance between each pending order and the profit/mesh. This distance can be between each pending order and can be a fixed number (arithmetic grid) or a fixed percentage (geometric grid).
  * _Stop-loss._ Does the system allow stop losses and when will it be activated?


# Risks 

Grid strategies work best in oscillating markets. Any trending market can cause this strategy to accumulate a large number of positions against the trend. It may cause heavy losses to the entire account.

In a bull market, a neutral grid will take short positions and accumulate more and more at a new high. If a stock constantly reaches new highs, the neutral grid can consume way more positions, leading to serious losses.

# Application 

The grid strategy can make significant profits in an oscillating market. It’s vastly different from the momentum approach. Any trading instrument can use the grid trading system. Also, because of its simplicity, the grid strategy can be easily automated. Today, the grid strategy is most popular in the currency and cryptocurrency markets because of its 24/7 trading nature. It’s very advantageous for the grid strategy. In Vietnam, a grid strategy can also be developed. However, risk control is key due to the extremely high volatility of small markets.

---


## 22. Smart-Beta Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/smart-beta-strategies/*

# Definition

[Smart-beta strategy](glossary), or factor investing, is a strategy for building a portfolio according to a system. It’s based on rules, and the use of fundamental business factors, e.g. liquidity, value, and quality, as criteria for making investment decisions.

Smart-beta is the scaling strategy of the passive investment strategy. With passive investing, investors only need to buy the entire component shares of an index as a proportion of market capitalization. They hold for the long term to achieve returns comparable to the reference index. With smart-beta, the portfolio weights are determined based on fundamental factors rather than market capitalization. The goal is to increase the proportion of stocks with high return potential, and in contrast, reduce the proportion of less potential stocks. It optimizes the portfolio with better returns compared to investment strategies.

Theoretically, smart-beta combines components of both passive and active investment.

# Example of Smart-Beta 

An investor believes that over the long term, stocks with low P/E tend to generate higher returns than the overall market average. Applying this investment perspective by taking VN-Index as a benchmark, this investor builds a portfolio according to the Beta strategy as follows: buy all VN-Index shares and hold for the long term. The weights are determined according to the rules: the lower the P/E, the higher the weight.

As an illustration, assume VN-Index has only 5 component stocks A, B, C, D, and E. Investors use P/E as a parameter to calculate the portfolio weight as shown in the table below:

This strategy is quite similar to passive investing, but the P/E ratio is used to determine portfolio weights, instead of market capitalization.

In the same instance, investors can determine portfolio weights using other methods, as long as the first principle is maintained: “Increase the weights of stocks with low P/E and reduce the weights of stocks with high P/E.” Below are some prime examples.

  * Only invest in x stocks in VN-Index with the lowest P/E, also known as shortlisting. For example, suppose VN-Index has 500 stocks, invest in only the bottom 50 stocks with the lowest P/E. The proportion is 2% for each shortlisted stock and none for others.

  * Determine an acceptable threshold of the P/E and only buy stocks satisfying this constraint.


# Some Commonly Used Factors in Smart-Beta Strategy

In investing, a “factor” is understood as a variable or characteristic highly correlated with stock returns. The factor can also be defined broadly as any variable that investors believe is valuable in ranking stocks and predicting future returns and risks. Below are 5 commonly used and widely accepted factors.

  * _Value._ In the long run, investing in stocks undervalued by the market has a higher rate of return than overvalued stocks. The value factor can be measured from key metrics in corporate financial statements, such as P/E ratio, dividends, income, cash flow, EBIT, and EBITDA.
  * _Market capitalization._ Small-cap stocks tend to rise more sharply than large-cap stocks.
  * _Volatility._ Increasing the weights of low-risk stocks can help improve the portfolio’s return on risk.
  * _Quality._ High-quality companies will increase the share price over time to reflect their intrinsic value. Some basic criteria of high quality are strong, stable profitability, and low leverage ratio.
  * _Momentum._ Recently rising stocks tend to continue gaining similar momentum in the short term.


In reality, there are hundreds of factors that have been identified and used in building portfolios under . Additionally, investors can combine them to create more variations of this strategy.

# Strengths and Weaknesses

Combining active and passive investing, the smart-beta strategy has several advantages of passive investing such as transparency, transaction costs, and low monitoring costs. At the same time, smart-beta also shares advantages of active investing like a higher potential return than average, and diversified investment depending on the preference and domain knowledge of each investor.

However, identifying key factors and rules in smart-beta strategy can be complex. It requires skills in testing historical data and experience plus in-depth knowledge of financial analysis. Besides, these factors often come from corporate financial statement data. In the Vietnamese market, it can be a huge hurdle to gather detailed, complete, and accurate financial statements of all listed companies. It remains the main challenge for investors following this strategy.

# Application in Algorithmic Trading in Vietnam

With an [algorithmic trading system](glossary), computing the financial factors of all stocks in the market has become simpler than ever. Besides common metrics like P/E, P/B, and ROE, investors can freely customize further metrics as desired. An example is the short-term unrealized revenue divided by the total revenue of the last 4 quarters. It reflects the percentage of potential revenue recorded in the next 4 quarters. Under the same conditions, the higher this factor is, the more stable and solid the company is.

An algorithm following a smart-beta strategy can include many of the customized metrics like those above. They can be adjusted to different weights as the portfolio desires.

Note that it’s key to restrict frequent portfolio restructuring and aggressive trading. It’s to ensure the passive investing components of the portfolio.

---


## 23. Sniffing Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/sniffing-strategy/*

# Definition

**“Sniffing”** is a special group of algorithms to detect other trading algorithms. The sniffing strategy usually aims at continuously high-volume trading algorithms like TWAP, VWAP, and POV. It can also detect market-making algorithms or price momentum algorithms albeit less commonly used.

The input data of sniffing algorithms includes real-time tick data with the order book of all traded securities.

The key principle is to rely on matching orders and order books to find patterns that are more repetitive than arbitrary. Once the predictive model has been identified, if the above pattern continues, the sniffing strategy is considered to have identified another algorithm. Depending on the obtained data, it can mirror to open similar positions to take advantage of the information.

Trading algorithms appear in different forms below:

  * _TWAP._ The main characteristic of the [TWAP algorithm](glossary) is that the orders are separated over a fixed period of time. Sorting trading orders and finding transactions with similar volumes separated by a constant time period is a strong [ indicator ](glossary)of TWAP.

  * _Order splitting._ The characteristic of order splitting is that many orders match in a brief time frame of under one second. A simple model reporting the number of executed orders over a 5-second period can give a strong signal of order splitting.

  * _Market maker._ The market-making strategy usually works very strongly at the bid price 1 and the ask price 1. All securities that continuously place orders at this bid and ask price usually involve a market-making algorithm.

  * _Price momentum._ Price momentum algorithms are often used in the derivatives markets. The common characteristic is to buy when the market is trending up and sell when the market is trending down. It usually creates a large price slippage. Monitoring repeated large slippage points over several days can give a reliable signal of high-volume price momentum algorithms in the market.


# Key Applications

When detecting possible transactions of large organizations, the basic principle is to take positions in the same direction at a reasonable volume. It’s key to note that price changes too quickly can change the strategies of investors who are accumulating positions. So opening positions need to be strategic and rational according to the general market. Investors need to consider taking profits when the price moves too fast, or there’s no longer a support signal from the detected algorithm.

When detecting stocks with the participation of market-making algorithms, applying the right price momentum strategy at the right time can bring great profits.

When detecting a price momentum algorithm, using a [scalping strategy](glossary) will be optimal at points where algorithms with large volumes are involved.

# Protect Your Systems From Sniffing Algorithms

Stealth algorithms are a group of algorithms to help execution algorithms avoid detection from sniffing algorithms. The basic principle of sniffing algorithms is to detect patterns. Adding more randomness in the execution will likely work well in defending sniffing algorithms.

---


## 24. High-Tech Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/advanced-algorithmic-trading-strategies/*

In global financial markets, any approach that brings high potential profits is of significant consideration. It includes the most modern technologies that may give investors a strong edge.

**Satellite Images**

Imagine you know exactly how the Russia-Ukraine war is unfolding in real time. You stay up-to-date on all Russian tankers and the current state of Ukrainian wheat production. With this information, how possible is it to make big profits with low risks? Does this sound like fraud to ordinary investors?

There are many satellite image providers in the market such as RS Metrics, Descartes Labs, Orbital Insight, and Planet. This proves to create a huge competitive advantage for clients of these companies during global and macro events. Having this information just one second before the news announcement can potentially bring large profits.

In practical applications, automobile counting is the most basic approach used to assess the potential of retailers. Other approaches include counting solar panels, timber inventories at sawmills, and counting metal mining vehicles worldwide.

Although promising, it’s currently not feasible in Vietnam because the market size is very small. Satellite imagery is unlikely to add much value. Besides, Vietnamese investors cannot, due to laws, invest in foreign markets where this approach can be of good use.

**Sentiment Analysis**

At 1:07 pm on Tuesday, April 23, 2013, the Associated Press Twitter feed stated Barack Obama had been injured in an explosion at the White House. The stock market fell 0.9% immediately in just a few seconds. After confirming the tweet is fake, the market has fully recovered. It’s still a vivid example, however, of how sentiment strategy works in real trading.

In principle, a sentiment strategy is an approach that uses words from global news, such as social accounts of supposed credible sources. They are to capture the latest news or the crowd mentality on a topic. From the data, the algorithm automatically opens the corresponding trading positions. Investors interested in this approach may consider Sentifi solutions.

At the time of publishing, there’s no evidence that sentiment-driven algorithmic trading has a competitive advantage in Vietnam. Still, this approach is a compelling and intriguing idea to follow.

**Machine Learning and Artificial Intelligence**

This approach is probably the most well-known for its applicability in various fields. However, in the financial sector, not many machine learning or artificial intelligence algorithms are known to be sustainably profitable. It is due to the random nature of the financial sector, which can be very different from other scientific and rule-based domains. In random datasets, many models that perform well with the past data will not guarantee future performance. This fact can make the trading performance of machine learning and artificial intelligence models ineffective. However, in the future, artificial intelligence will still dominate the trend in financial market research as we collect more and more data.

---


## 25. Behavioral Finance in Algorithmic Hypothesis Formation

*Fonte: https://hub.algotrade.vn/knowledge-hub/behavioral-finance-and-its-application-in-algorithmic-hypothesis-formation/*

# Definition

Behavioral finance studies how people make decisions and examines the psychological factors that influence and skew their decision-making process.

The traditional economic and financial theory generally assumes that market participants always act rationally by considering all available information in the decision-making process. In reality, financial decision-making is a complex situation. When faced with so much information to constantly process and update, people often don’t have the time or ability to come up with a completely optimal decision. Instead, they often take an easier and more subjective approach. They often use only parts of the available information and determine a course of action that best suits their judgment and priorities. They are content with making a “sufficiently good” choice rather than making an “optimal” choice. In this way, they may inadvertently bias the investment decision-making process. 

Behavioral finance does not assume people are always rational. It believes that people are limited in controlling themselves and are influenced by their own biases. These biases are in two main groups: cognitive errors and emotional biases.

# Cognitive Errors

These types of errors are basic statistical errors, information processing errors, or memory capacities. They cause decisions to deviate from rationality. In general, cognitive errors stem from faulty reasoning. It can often be, however, mitigated or eliminated through better information, education, and advice. Cognitive errors can be grouped into 2 types:

  * **Belief perseverance biases:** come from the result of mental discomfort. It occurs when new information conflicts with pre existing beliefs or perceptions. To resolve this dissonance, people are likely to ignore conflicting information. They only consider information that confirms their existing beliefs and thoughts.

  * **Information processing biases:** refer to information being processed and used in illogical and irrational manners.


Below are some common belief perseverance biases and their corresponding behaviors in financial investment.

Below are some common processing errors and their corresponding behaviors in financial investment.

# Emotional Bias

Emotional bias arises spontaneously from feelings and attitudes. It can cause decisions to deviate from rationality. It is typically harder to correct compared to cognitive errors because they originate from impulses and intuition rather than logical calculations. A person usually can only recognize and learn to adapt to it rather than correct itself.

Below are some common emotional biases and their corresponding behaviors in financial investment.

****

# Applications of Behavioral Finance in Algorithmic Hypothesis Formation

The focus of behavioral finance is the study of behavioral biases that influence individual investor decisions. Behavioral finance doesn’t show how to properly predict the future. Nor does it provide a financial investment model that can confidently beat a market. However, behavioral finance still helps investors have a deeper insight into how the market actually works. It helps build more reasonable algorithmic hypotheses.

Price momentum is a common phenomenon in the stock market. It’s an unusual movement of the stock price. It can be observed that when a stock rises or falls sharply in the short term, the trend tends to continue.

In terms of behavioral finance, price momentum can be explained by availability bias – the tendency to forecast an outcome or the importance of a phenomenon based on how easily the information is recollected.

When a stock price keeps rising, investors easily remember this event and unconsciously assume a future rise is more likely than a fall. Besides, hindsight bias causes illusions to investors who believe they could have forecasted a future rise and would regret it when missing the buying opportunity. Investors are thus urged to overcome this regret by placing buy orders even when the stock’s market price is already much higher than its intrinsic value.

Believing the biases above can have a strong market impact, algorithmic traders can take advantage of the price momentum strategy to seek short-term profits.

Behavior finance also explains the phenomenon of absurdly sharp rises in stock prices during a brief period of time. In addition to the price momentum insight above, buying and selling shortly after will still be profitable even if investors have sold too early. A few short-term profits bring a sense of pride and confirm the investors’ belief that they made the right investment.

Hindsight bias can reinforce an investor’s belief that their previous trading strategy was correct and will continue to be profitable in the future. Overconfidence bias gives an illusion of their forecast ability. Conservatism bias makes investors ignore contradicting information or opinions. As a result, investors are still willing to open more long positions at high prices, even using margin to increase purchase power. It further causes increased demand and the stock price continues to rise rapidly.

Yet in the context of absurdly rising stock prices, investors can apply the mean-reversion strategy. They can open short positions when the security price already rises too quickly and expect it will revert back to the reasonable mean.

---


# III. DATA


## 26. Standard Data in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/standard-data-in-algorithmic-trading/*

# Market Data

Market data consists of the following essential data fields:

  * Stock ticker symbol;

  * Order execution time;

  * Order execution price;

  * Order execution volume;

  * Bid price 1, 2, 3 (10 price steps for HNX and UPCOM);

  * Bid volume 1, 2, 3 (10 price steps for HNX and UPCOM);

  * Ask price 1, 2, 3 (10 price steps for HNX and UPCOM);

  * Ask volume 1, 2, 3 (10 price steps for HNX and UPCOM).


These data fields allow investors to use most technical analysis strategies or OHLC charts (Open-High-Low-Close). This is the simplest and most common data group sold under data packages in Vietnam.

Execution data is also categorized based on the type of the transaction such as insider transaction data, foreign investment execution data, and deal execution data.

Insider transaction data is publicly available. However, in Vietnam, insiders may trade in different ways to avoid affecting stock prices and frequent reporting. This data is therefore often unreliable, and it should only be used as a reference.

Foreign investment data represents a strategic group of shareholders. This group plays an important role in making long-term investment decisions. However, it is not as useful for short-term investments.

Deal transaction data has a high volume and reflects the expected prices of the parties involved. In special cases, when foreign investors cannot buy shares directly on the stock exchange, the deal transaction often represents the valuation of foreign investors. However, the public information of the deal transaction may still differ from reality. This group of data is not completely reliable in the Vietnamese market.

# Financial Statement Data

This data group includes: 

  * Income statement; 

  * Balance sheet;

  * Cash flow statement (direct or indirect). 


This data group is widely used in fundamental analysis. However, Vietnamese accounting standards still have many differences from the international standards. Different industries such as manufacturing, banking, securities, and insurance have specific financial report structures. To analyze the whole market, it’s essential to have reference benchmarks.

# Dividend Data and ESOP

The company’s profit-sharing policy and the ESOP program over many years have greatly influenced investor sentiment in the long term. Therefore, data including cash dividends, stock dividends, and bonus shares can be used in algorithmic trading.

ESOP is a special policy to attract corporate talent. However, it’s often abused for personal purposes. When adopting the IFRS, international financial reporting standards, ESOP abuse in Vietnam should be more restricted.

# Macroeconomics Data

Inflation data, interest rates, economic growth, import and export, exchange rates, export orders, money supply, and public investment reports are publicly available macro data. They are often used to predict the economy in the medium term. 

For instance, algorithmic traders can rely on inflation and interest rate data of 2022 to gain insights into the macroeconomic impact on the market and domain-specific businesses.

# Commodity Data

Each particular industry and enterprise will be closely related to the price of imported and exported goods. These prices often move together with the global commodity prices, which are important data to collect. Investors in Vietnam are most interested in common commodities like oil, gold, soybeans, coffee, and meat. Other commodity prices are more complex but still collectible such as international freight shipping prices.

During the Covid pandemic, the supply chains were disrupted. Commodity prices no longer followed normal economic rules. They become important information for seeking trading advantages.

# Index Data

A single stock or a particular industry usually has a certain correlation with the local and global market indices. Therefore market indices need to be stored to have an accurate view of the Vietnamese market or each individual stock in the global context. Besides the data above, there are other types of specialized data. Algorithmic traders can gather them to support algorithm development and seek trading alpha.

---


## 27. Data Cleaning Tutorial

*Fonte: https://hub.algotrade.vn/knowledge-hub/data-cleaning-tutorial/*

Clean, accurate, and complete data is the foundation of an [algorithmic trading system](glossary). Inaccurate data will affect the performance of the algorithm during the testing phase and real trading.

# Common Data Errors

  * _Data collection programming errors._ Common in internal data collection systems and third-party data services.

  * _Partial data loss errors._ Common when the data collection system and storage experience unexpected problems. For example, data sources changing their data structure will lead to data loss errors.

  * _Raw data errors._ Occur when the data supply for the whole market experiences issues that cannot be fixed in a short term. An example is an erroneous buy order for tens of millions of contracts on the Vietnamese derivatives market.

  * _Manual input errors._ Occur on financial statement data and other information that has not been automated at the data entry step.

  * _Empty data field._ Appears when scanning is incorrect on financial statements of stock tickers on UPCOM for example.

  * _Time difference._ Occurs when data sources update with a large delay compared to the time stamp issued. This error is most common in financial statement data of small companies in UPCOM market. 

  * _Past data adjustment._ This is a particularly difficult error to fix when past data is adjusted for various reasons. This error is common in stock data.


In Vietnam, data errors outside the price and volume range also often occur. Algorithmic traders should carefully consider data sources before developing algorithms. For inaccurate and skewed data that cannot be automatically collected, traders should consider skipping this data source until the data cost falls to an acceptable level.

# How to Clean Data

**Standardize Data**

  * _Define data standards._ Different systems will always have different data standards. However, data needs standardization to ensure compatibility, ensuring data retrieval tasks, and system scalability in the long run. For example in a Python system, the time standard is the float data type in Unix timestamp.

  * _Standardize data._ Input**** data typically has different formats compared to those in algorithmic trading systems. It’s important to standardize data before system integration.

  * _Define the trusted data source._ This data source is the most trusted source and can provide first-tier data to the entire market. Based on the price and volume data of Vietnam’s derivative market, HNX is the trusted base data source. The base data source typically has the highest accuracy and stability. Defining and using the trusted base source will enhance the stability and reduce overhead costs of data cleaning.


**Data Validation**

Compare two data sources to validate and clean data. Basic validation techniques include:

  * _Identify missing data._ Add the missing data to the system database or remove it entirely.

  * _Identify data duplicates._ Remove duplicates. Duplicate data is usually related to a listed company event and is often published at different times.

  * _Identify data anomalies._ Remove any anomalies. Anomaly data can be detected using a simple statistical and probability method. An example of data anomalies in the Vietnamese stock market is the unchanged derivative price, as the trading volume exceeds the processing capacity of the trading system. It results in a constant price over a long period of time. Another example is the occurrence of unusually large orders at millions of contracts, while the average daily trading volume is around 200,000 contracts.


  * _Identify invalid data._ Trading prices that exceed ceiling and floor prices or other straightforward constraints are clear signals to review and clean up data. Typically an invalid data point will help identify a range of data that needs cleaning and adjusting.


In addition, some data errors are easy to recognize with a close look. An example is the closing volume in the Vietnamese stock market may not be updated correctly by third-party service providers.

---


## 28. Data Management in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/data-management-in-algorithmic-trading/*

This section covers different data aspects in algorithmic trading. We will discuss the two groups of data and principles of data collection, as well as common data management issues.

# Two Data Groups in Algorithmic Transactions

There are two main groups of data in algorithmic trading: input trading data (market data, financial data, commodity data) and output trading data (algorithmic trading data). Sometimes, the output trading data may serve as input for other algorithms.

  * **Input trading data** includes but is not limited to standard data in algorithmic trading as described in article 26. An example is real-time market data of a financial instrument. Real-time data can run at different speeds depending on the market size.

  * **Output trading data** is the data generated when trading systems operate. They can be both buy and sell signals generated based on input trading data or algorithm trading orders. While the input trading data is to operate algorithms, the data generated during operations is to monitor the algorithms. Besides, this data group is also used to research and develop new algorithms. During operations, it is key to keep only important information so as to not overload the system operator as well as to optimize data storage.


# Two Important Criteria in Selecting Data Sources

Data latency and completeness are two main points when selecting data sources. Meanwhile, defining key concepts and mastering technology is of utmost importance in collecting and managing data.

**Data Latency.** Latency is the time difference between when data is generated versus when an algorithm receives it. Latency is a key aspect of real-time trading, regardless of market size. Investors need to be concerned about data size as the market grows. However, latency always has a higher priority. The reason is in both large and small markets, if the data latency is very large, the [trading algorithm](glossary) will not be able to take advantage of market opportunities. However, in trading data, algorithmic traders may tolerate higher latency than usual.

Data latency can be minimized by accessing the best real-time trading data source. Since latency is the top priority when choosing a data source, it will lead to the critical choice of the physical location of a data collection system or a data server. Due to regional and service limitations, investors should anticipate technical problems when setting up and maintaining services. It’s also optimizes costs when implementing trading algorithms in the future.

**Data Completeness (Data Coverage).** Standard data completeness or coverage is the ratio of data obtained from a source to actual data. For example, a market has a total trading time of 360 minutes. The data source, due to technical limitations, can only record 336 minutes of trading data. In this case, the completeness of the data source is 336 divided by 360, which is approximately 93.33%. In most cases, it’s not straightforward to measure the coverage of transaction data in real time. Therefore, having multiple data sources and cross-checking with each other is of high importance.

# Data Storage and Management in Algorithmic Trading

**Key concept.** The first thing to keep in mind is not the storage system but what data should be stored. Algorithmic traders need to identify what data to store. Some basic concepts right from the beginning are prices, orders, signals, and order execution. Selecting the right concepts helps in planning and designing a more efficient data system. A reliable database contributes to fast, smooth, flexible, and scalable system development. This also makes the data storage system easy to upgrade in the future.

**Technology selection.** After defining concepts and data fields, the choice of the technology stack is not as important. The right tools and skills in technology are more important than the technology choice itself.

**Data storage management**. There are two main types of data storage in algorithmic trading: temporary storage for data trading, and database for historical trading data.

_Temporary storage._ This is a repository of real-time trading data, including market data, index, and commodity data. Since algorithms must reach data as quickly as possible, storing data in an in-memory database, or caching system like Redis is a reasonable choice. Note that the data should have an expiry time. It’s because this data is often used for intraday trading. Temporary storage data from the previous day, or any previous period, will often be unusable. Using improper data can lead to serious consequences, especially for intraday trading algorithms. Therefore, checking data correctness in terms of time, and determining expiry times are mandatory. If data from previous days or periods needs to be accessed, a database is more suitable than a temporary storage system.

_Database._ When a trading day ends, the intraday trading data should be written down in the database for long-term use. This is to research and develop new algorithms, backtest existing algorithms, and improve operating algorithms. Many types of databases are popular like Postgres, MySQL, etc. These databases are used by data management and mining tools like ElasticSearch, Logstash, and Kibana (ELK) to display, illustrate, track, report, summarize, analyze, and evaluate historical data.

---


## 29. Stock Trading API in Vietnam Market

*Fonte: https://hub.algotrade.vn/knowledge-hub/api-in-vietnam-stock-market/*

**API Definition**

An **application programming interface** (API) is a set of definitions and protocols that allow two software to communicate with each other.

To develop an algorithmic trading system, investors need to optimize the process of obtaining data, retrieving positions, and placing/editing/canceling orders through APIs provided by securities companies or exchanges. In Vietnam, the process is implemented with a frequency of approximately one cycle every 02 seconds. In developed markets, the frequency can be thousands of times faster. Investors need programming experience to call API properly, including authentication, key retrieval, connection configuration to the server, sending queries, parsing response packets, performance testing, and security testing.

# API Categories

  * The REST API only returns data when requested.

  * The FIX API returns data immediately upon data update.

  * The RPC API returns data immediately upon data update.


With these three API categories, there’s the speed superiority of FIX and RPC APIs over the remaining.

# Stock Trading API in Vietnam 

A pioneer in providing open APIs for the investor community is the Bank of Investment and Development of Vietnam Securities Joint Stock Company (BSC). DNSE Securities JSC focuses intensively on supporting algorithmic trading through API as well as AmiBroker analysis software. More recently, SSI Securities Joint Stock Company has just launched an API service. With its leading position in the industry for many years, it has marked the official period of widely accepted algorithmic trading in Vietnam. Their detailed API information is available publicly online. Other securities companies have also fully developed their APIs but have not announced them officially yet.

# Which API to Choose

  * _SSI and BSC APIs are suitable for beginner traders who need to familiarize themselves with algorithmic trading and require stability._ In the introductory stage of algorithmic trading, a stable and simple-to-use API with a professional support team is key. BSC has many years of experience in implementing API services. SSI with Q-Trader trading software also meets the needs above.

  * _DNSE is suitable for high-volume experienced traders._ Apart from basic functionality, high-volume traders are most concerned with costs. With the direction focusing on the algorithmic trading market, DNSE is a stock company that meets this criterion when trading large volumes.


Over time, new APIs will roll out with many improvements. Currently, API development is no longer a technological challenge for securities companies. Many big names have joined the market. Traders can expect that big securities companies such as HSC, VND, and VPS will soon announce their own APIs, thereby adding options to the market.

Investors in Vietnam have witnessed a profound quantitative and qualitative shift in the transition from trading over the counter to online trading. A bigger revolution for Vietnamese investors will be from online trading to automated, algorithmic trading.

---


## 30. Search Process for Fastest Data Source

*Fonte: https://hub.algotrade.vn/knowledge-hub/procedure-to-seek-the-fastest-data-source-in-the-vietnam-stock-market/*

# ****Higher Speed, Higher Efficiency

[Algorithmic trader](glossary)s all want access to the fastest data source to improve performance while reducing transaction randomness.

For some algorithms like market-making, scalping, and arbitrage trading, the fastest data source means a lot of real profits. A slower data source only leads to paper profits.

In other algorithms, the fastest data source plays a role of reducing noise. Reducing noise will ensure algorithm performance isn’t the result of randomness, even though noise is not inherently an adversary for trading.

Finding the fastest data source is therefore in high demand for all algorithmic traders, especially for the Vietnamese stock market.

# Available Sources in Vietnam 

There are four main data provider groups, each consisting of multiple data sources.

  * _Live board of security company_ : this is data from live boards of brokerage companies like SSI and VND. There are at least 50 data sources in this group. Some require registration while others offer it for free.

  * _News website_ : data**** from financial news websites like Cafef, Vietstock, and Stockbiz. These websites provide free data, but do not aim to serve traders, so the latency is very high.

  * _Data service provider_ : data from data providers such as Fialda and Fireant. AmiBroker is popular among Vietnamese algorithmic traders. It is one of the most popular data sources.

  * _API:_ the application programming interface provides free data. However, to access data from the API, the algorithmic trader needs programming skills.


# The Speed of Data Group in Vietnam

The ranking of each data group is as follows:

  * _API_ is the fastest group. It’s built exclusively for algorithmic trading from brokerage firms. It’s always the fastest data pool in the market.

  * _Data service provider_ is ranked as good. Data needs standardization and moves through multiple intermediary stations before reaching the end user. This can cause some latency.

  * _Live board of security companies_ is ranked as average only. It only focuses on user experience rather than speed. It definitely does not have the top speed.

  * _News websites are_ the slowest. It aims to provide financial news, and speed isn’t among their priorities.


# Verify the Fastest Data Source in Vietnam

We first collect all the FIX APIs and RPC APIs available in the Vietnamese stock market. We use a simple algorithm to count the number of times each API is fastest. The API with the highest points is the fastest data source in the market. The figure below tests API speed on Feb 14, 2023.

At ALGOTRADE, the daily score is used to determine the current fastest data source. It will automatically be used as the main data for the next trading day.

---


# IV. BACKTESTING


## 31. Philosophical Foundations of Backtesting

*Fonte: https://hub.algotrade.vn/knowledge-hub/philosophical-background-on-algorithm-backtesting/*

Investors often try hard to experiment with a lot of third-party software. They may find many potential trading algorithms but end up losing hard-earned money in a real trading environment. The following five philosophies applied during testing phases can help unravel the root cause.

# Backtesting Can Always Result in Perfect Scores

It's common knowledge that any algorithm can become the holy grail with the right combination of parameters when testing on historical data.

To understand this claim, an algorithm without any superior alpha, or insights, that runs on a full combination of parameters will return a standard distribution of profits, before all fees, taxes, and slippage costs. An algorithmic trader can then select the best parameters and start trading in the real environment. Unsurprisingly, most algorithms will fail due to the results of [backtesting](glossary) and the [optimization](glossary) phase.

# The Real Trading Result Is the Only Thing That Matters

Testing on historical data is to form confident predictions on real trading performance after all. Suppose an algorithm predicts the result of a 20% annual return. What is the confidence level of this prediction in real trading? An algorithm is only ready to run in real life environment if a trader can expect a confidence level of at least 50%.

# Correlation Is to Ensure Reliability

A high degree of correlation across each testing phase increases the reliability. On the contrary, a low degree indicates the testing phase has issues and the results may not be reliable. There are 4 main stages of algorithm evaluation:

  * In-sample backtesting;

  * Out-of-sample backtesting;

  * Paper trading;

  * Small account test.


The higher the correlation between these 4 stages, the more consistent and reliable the algorithm is in real.

# Out-Of-Sample Backtesting May Not Be as Reliable

Many professional traders rely on out-of-sample backtesting after in-sample testing to evaluate an algorithm’s reliability. Although this technique is widely accepted in machine learning, traders can apply it in the wrong way for algorithmic trading. The main reason is that out-of-sample data is still already a known fact traders may already be aware of.

For example, regardless of testing technique, all investors know that 2020 - 2021 is a strong bull market after the Covid-19 pandemic. And 2022 is a year of recession with high interest and high inflation. However, active traders may already be aware of this information before out-of-sample backtesting. Thus, it may not be reliable since out-of-sample data is not completely secret.

# Adding Forward Testing to Ensure Objectivity

[Forward testing](glossary) on never-seen-before data ensures objectivity when evaluating algorithm performance. Note that paper trading is to objectively evaluate the performance. The small account test is to confirm both the technical implementation and the real performance altogether.

---


## 32. Critical Mistakes in Backtesting

*Fonte: https://hub.algotrade.vn/knowledge-hub/critical-errors-on-backtesting-stage/*

Testing on past data provides [algorithmic trader](glossary)s a perspective into the future. They can form reasonable expectations on profit margins, maximum drawdown, and other key indicators. Some serious errors in this phase can make prediction results meaningless and invalid, and leave actual results to randomness.

Properly executing ****[backtesting](glossary) will form reasonable assumptions about the future trading results of the algorithm. Without careful design and proper assumptions, test results can create wrong expectations for high profits while consistently losing on real trades.

Below are five critical mistakes in the backtesting phase.

# Overfitting

This is the most common mistake that gives algorithmic traders the illusion of finding the holy grail. [Overfitting](glossary) can appear in a variety of ways:

  * Buy at the lowest price of the candle chart and vice versa. For example, buy a stock at 100,000 VND even though the current share price is 105,000 VND.

  * Gain knowledge of future events or use [future data](glossary) to make decisions at the moment. A simple approach is to buy a stock if its price rises 20% next month. It can be done in backtesting and often gives outstanding results.

  * Find the best set of parameters.__ By adding parameters to an algorithm, a trader can always find the best set that gives an outstanding return on investment. It’s often confused between overfitting and [optimization](glossary). Many experienced algorithmic traders still do not distinguish these two important concepts.


# Excluding Transaction Fees

Many algorithmic traders set the transaction cost to zero, and expect a small difference in real trading. This is a mistake since transaction fees in the real market significantly reduce profit margins.

As of June 3, 2022, on the Vietnamese derivatives market, the total transaction fees in both directions are approximately 0.12% of trading value. Assuming an active algorithmic trader trades one long position and closes it every day, the investment result will be negative 30% at year-end by transaction fees only. If the expected portfolio return is at an impressive rate of, say, 25%, the trader will still lose at year-end.

The figure below simulates an algorithm with a 25% expected return before transaction fees. It shows the real return after fees in a year with two trades every day:

# Ignore Slippage

The next irrational assumption is zero price slippage. This assumption even causes more harm than zero transaction fees. The concept of slippage is the same as transaction fees. It occurs in every transaction, and the difference is the slippage may be almost twice the transaction fees. From hundreds of thousands of contracts traded on the Vietnamese derivatives market, ALGOTRADE expects a two-way slippage at 0.7 points or 0.25% of trading value with market orders. This cost can significantly reduce the profit margin and can turn a potential algorithm into a disastrous failure.

The figure below simulates an algorithm with a 25% annual expected return before any slippage. It shows the real return after slippage in a year with two trades every day using market orders.

# No Liquidity Restrictions

This is an assumption that makes algorithms unable to trade. It’s more common for large investors. The reason is that in backtesting phases, the algorithm can buy or sell an unlimited number of shares and contracts at the market price. In real trading, algorithmic traders may see positions unmatched in this scenario.

# Fastest Speed on the Market

This is an assumption from many high-frequency traders. They often assume algorithms can achieve the best speeds in the current market. This assumption creates an illusion of outstanding performance but may in fact result in unmatched orders. Even worse, algorithms only buy or sell at a matched price completely different from their expectations.

---


## 33. Backtesting Module

*Fonte: https://hub.algotrade.vn/knowledge-hub/specialized-backtesting-module-benefits-and-development/*

[Backtesting ](glossary)is a core feature of third-party software like AmiBroker, TradingView, and MetaTrader. Below is a detailed analysis of the basic modules necessary to develop a system for backtesting.

# Benefits of Backtesting Module

To institutional investors or professional algorithmic trading, backtesting is a critical screening phase to assess an algorithm’s performance in the future.

When the number of algorithms to test increases, these tasks repeat and lead to a requirement for a standardized testing process. There’s now a need to build standardized testing modules that specialize in testing historical data.

Developing algorithms on testing modules that simulate real trading at the same time allow reusability. Investors will work more efficiently on these modules without the need to program two separate versions.

Last but not least, testing modules are built in a simulated environment. They help limit errors caused by changing between different running environments. It also increases the similarity of test transactions to real trading ones.

# Direction to Develop Backtesting Modules

Testing modules for an algorithm typically have three essential parts.

**Simulate securities companies.** This is a must-have to test trading algorithms on historical data in the long run. This part is to set up a simulated security company to receive orders, match orders, or even cancel orders from trading algorithms. Depending on the virtual account and real market conditions at the time of receiving a simulated order request, it decides to accept or reject the orders. After receiving new orders, it relies on market movements to match orders similar to real trading. A simulated security company has the basic features of a real company, without special cases such as partial order matching. Simulating securities companies requires lots of effort. However, in the long run, it helps investors test algorithms on historical data as objectively as possible.

**Program trading algorithms.** Trading algorithms can receive past data, return trading signals, and execute transactions with a simulated securities company to build a transaction history. The key point is the same piece of code can be applied in all stages: backtesting, [forward testing](glossary), and real trading.

**Reports.** A backtesting system needs to standardize test reports to facilitate horizontal development. The basic parameters that should be included are:

  * Total asset over time;

  * Profit;

  * Maximum drawdown;

  * Sharpe ratio;

  * Ratio of opening profitable/losing positions;

  * Expected value when profitable;

  * Expected value at loss;

  * Longest profit streak;

  * Longest losing streak;

  * Drawdown statistics.


Transaction history is recommended to be exported in Excel format for easy access, inspection, editing, and illustration.

The logic of simulating securities companies and performance and risk assessment is the same for all algorithms. It should be developed separately for reuse in different algorithms. Investors can save effort and minimize programming errors. Developing these modules independently is to simulate the real market and to assess the performance so it will not be affected by any particular algorithm. The assessment will become as objective as possible.

# How to a Securities Company Simulator

Building a securities company simulator is a centerpiece of the backtesting module. In particular, it contains three main components:

  * First is to build a paper trading broker that can receive orders, cancel orders, return order matches, and account status via API.
  * Second is to determine whether an order can match, and in how much volume based on information obtained from market data (volume, price, buy, and sell) at the time of placing the order. The time will be in the past for testing past data, or in the present for testing [future data](glossary). An example is from order matching: the simulator receives a limit order to buy at price X for ticker Y. If after receiving the order, and the order has not been canceled, the market price is less than or equal to X, then we can simulate that this order has been matched.
  * Lastly, all information about placed orders, status, matching results, transaction costs, and account status at times should be saved in the database. These data will be used to assess the algorithm’s performance and risk metrics.


In Vietnam market, note that the period of testing past data has lots of deviations from operations. In addition to common problems like taxes, fees, and slippage, traders should be aware of the volume and unobserved matches. The insufficient volume will reduce the algorithm’s efficiency when operating in a real environment. Unobservable matching data will benefit algorithms using limit orders and negatively impact using market orders.

---


# V. OPTIMIZATION


## 34. Optimizing Trading Algorithms

*Fonte: https://hub.algotrade.vn/knowledge-hub/optimizing-trading-algorithms/*

To trade in a real environment, a [trading algorithm](glossary) must have a logical foundation. It’s different from patterns that generate profits but cannot be interpreted. These patterns can be found by exhaustively searching past data. Past data should only be used to apply financial theory to a particular market.

The [optimization](glossary) process begins with a hypothesis in the form of a preliminary algorithm. It can be proposed by a professional based on their financial knowledge or practical experience. This preliminary algorithm is optimized on a sufficiently long historical data range to produce a complete, stable, and profitable algorithm. The past data range is called the in-sample data of the fine-tuned algorithm. This data range needs to reflect market volatility. The algorithm needs to make sufficient trading orders in this range for its performance to be statistically significant.

A preliminary algorithm is refined by adding new rules and adjusting parameters so that its efficiency in the target market is optimal. The efficiency is measured by an objective function, and the target market is represented by an in-sample data set.

The optimal efficiency is the right balance between risk and return, and not when the algorithm reaches the highest return. The****[Sharpe ratio](glossary) is often selected as the objective function. Limiting the risk of loss also helps an algorithm avoid overfitting. It’s a key issue in the algorithm development process.

[Overfitting](glossary) is a special phenomenon when an algorithm is specifically fine-tuned to get optimal results in specific sample data. However, when the tuned algorithm works on out-of-sample data, the efficiency is significantly reduced. When searching for the optimal parameters, algorithm developers should note two requirements:

  * Good performance in in-sample data;

  * Equivalent performance in out-of-sample data and in real trading.


It’s key to limit overfitting when developing the trading algorithm. Even though there are solid techniques in this area, it’s challenging to remove overfitting completely.

# Find an Optimally Fine-Tuned Algorithm

There are two steps to finding an optimally fine-tuned algorithm.

**1\. Add the Variational Law**

When optimizing an algorithm, the dynamic nature of the market should be noted. Instead of choosing fixed parameters, it’s advisable to create a rule that is a function of the statistical market variation. In this method, trading algorithms can adjust to the moving market, ensuring stability regardless of market conditions.

For example, volatility is an important [indicator](glossary) of market conditions. An algorithm may work differently in different market volatility. The average difference between the highest and lowest price of VN30 in recent days can be a statistical signal for market volatility. Using this signal, an algorithm can adapt itself to work well in different market variations.

**2\. Parameter Search**

After adding market statistics to algorithms, there are possibly algorithm parameters that don’t change frequently and need to determine their values. Parameter space is the set of all possible combinations of these parameter values. The optimization process should be designed to pick the optimal parameter values.

A simple approach is that for each set of parameters, algorithm developers run backtests over past data and pick the best set according to an objective function. This function can be the Sharpe ratio or another criterion that balances risk and return. This method has the limitation that the number of parameter sets can be infinite or very large. In this scenario, there will be insufficient resources to try all possible sets. Another issue is that the set found in this method may not guarantee similar performance in****[future data](glossary). These are the two main problems in the optimization process.

Other methods have been proposed to limit the search space and still select a near-optimal parameter set, such as grid search, priority parameter search, and advanced search algorithm.

_Grid search._ This method is closest to the naive method above. All preset values of the parameter set will be checked. To avoid overfitting, the appropriate set of parameters will be reselected by dividing the data set in the sample into training and validation sets. 

For example, a regression algorithm predicts how much the closing price of VN30F1M will change compared to the previous day’s. It then opens and closes a position at ATO and ATC respectively. For instance, if it predicts a 3% decrease, it will open a short position at ATO and close at ATC. It will make a profit if the prediction is correct. In this algorithm, there are two main parameters to identify:

  * N: the number of previous days used as data for prediction.

  * Alpha (α): the threshold to open a position at ATO. If the price difference is greater than this threshold, the algorithm will open a position at ATO.


In this example, there are 25 sample values of N, and 7 sample values of α to check. Also, the parameter search assumes this range is sufficient to cover the parameter space that is likely to contain the optimal value. Therefore, there are 25 x 7 = 175 different parameter sets. Tables 01 and 02 list the values and performance of these parameters. Based on the following result, the optimal parameter is N = 19 and α = 0.2%. It results in 127.62% profit and a -11.83% maximum drawdown (MDD).

_Priority parameter search._ When there are too many combinations of parameters to evaluate, grid search will be inefficient due to a lack of computational resources. To save time, the parameters that have a great influence on the algorithm should be prioritized by only changing the value of that parameter, while keeping others unchanged.

We can fix α = 1.0%, and change the values of N to the optimal N which is 15. Then we fix this parameter and search for different values of α. Finally, we find the optimal α = 0.3% (and N = 15) with 103.95% profit and -16.20% maximum drawdown (MDD). We find this parameter set by trying 31 different combinations, instead of 175 as with the grid search method.

_Advanced search algorithm._ In advanced search, it’s recommended to discover which direction we should move in the parameter space to find the optimal set, guided by the value of the objective function. In this way, it’s only required to test a much smaller part of the parameter space to find the optimal approximation parameter set.

One of the advanced methods is the hill climbing search. This method searches based on a direction that gradually increases efficiency. It stops when there are no other parameter sets around for higher results. For example, the direction in Table 01 is [N=21, α = 0.3%] → [N=20, α = 0.3%] → [N=19, α = 0.3%] → [N=19, α = 0.2%].

---


## 35. Techniques to Avoid Overfitting

*Fonte: https://hub.algotrade.vn/knowledge-hub/techniques-to-avoid-overfitting/*

# Overfitting Definition

In statistics, [overfitting](glossary) is the result of an analysis that is too precise on a particular data set. It fails to perform well in another data set or to predict [future data](glossary). This phenomenon occurs when the data noise, or residual/unexplained variation, is included to make an unnecessarily complex model, while it should instead be explained by randomness. Since the complex pattern is influenced by random factors, it will not hold true in the future.

For algorithmic trading, overfitting occurs because a fine-tuned algorithm uses models and parameter values that increase the test performance in the sample by randomness. That randomness is unlikely to repeat in the future, which leads to incorrect predictions.

The following figure shows an in-sample overfitting (cubic curve) in a regression problem.

For example, in algorithmic trading, we can have many different versions of the same algorithm. Each has better performance on the in-sample data compared to the previous version because of added rules. The later version gets increasingly more complex than the former ones. The performance of these versions is in the table below.

The first two versions of the algorithm perform well with positive return on out-of-sample data despite the acceptable difference in performance compared to the in-sample data. Meanwhile, version 3 adds new rules and increases in-sample performance, while significantly reducing out-of-sample performance when compared to version 2. In this case, we can conclude that version 3 is an overfit, and version 1 is underfit since it can be improved to outperform in both in-sample and out-of-sample data.

# Techniques to Avoid Overfitting

Here are 05 techniques to avoid overfitting. It should be noted that the techniques only help to eliminate basic overfitting, not undetectable cases. For the latter, we need to use the algorithm testing process after [optimization](glossary).

**Understand Why a Rule Is Right**

When finding a rule that has produced profits in the past, it’s important to explain why the rule produces such returns based on financial theory, or human behavior, not hoping the history will repeat itself in the future. This makes the rule valuable. Combining financial knowledge and market conditions, investors can properly interpret and assess the algorithm's performance when monitoring the trading system. As a result, algorithmic traders can predict the irrationality the moment when this assumption no longer holds true and promptly stop the system or change the algorithm before any disaster.

**Split the Data Into Training and Validation Sets**

After splitting the data set, we only use the training set to optimize the algorithm’s performance. The validation set is to find a version on the optimization path with a reasonable fit to ensure equivalent performance on both data sets (Figure 12).

The idea behind is that randomness in the training and validation sets are different, but the two share a common hidden pattern. Therefore, if a pattern consists of too much randomness only in the training set, it will perform poorly in the validation set where the randomness does not occur. If a version performs well on both data sets, it’s likely the hidden pattern has been found, and the correct rules and parameters have been identified.

In Table 3, using out-of-sample data as a validation set, we can select version 2 as the reasonable fit.

**Choose a Simple Preliminary Algorithm to Start With**

When an expert proposes a preliminary algorithm to test on the target market, there will be a set of multiple versions that can be applied. These versions are basic algorithms but have different enhancement rules and parameter values. During the optimization process, these versions are tested to find the most likely version that can perform well in the real market. If the preliminary algorithm is simple enough, these versions will have a lesser chance of overfitting.

In figure 11, we see the linear model y=0.5x+1.5 is simpler then the cubic polynomial y=x3+(x+0.3)2-x+1. The hidden patterns are mostly simple in real life.

**Drop the Preliminary Algorithm if There Are Too Few Versions for Profit**

After evaluating different versions of the initial algorithm, if there are too few instances that profits, the algorithm hypothesis may not be valid for the target market. The few versions with positive performance may be due to randomness or overfitting of the training data. We should drop the preliminary algorithm at this stage.

**Better Choose a Stable Optimal Point Than a Sharp Optimal Point**

Financial markets are always volatile. The optimal parameter value may change in the future. If a sharp, unstable optimal point is selected, it’s likely the performance will decrease rapidly even though the optimal parameter value changes ever so slightly.

---


## 36. Post-optimization Assessment

*Fonte: https://hub.algotrade.vn/knowledge-hub/post-optimization-assessment/*

An algorithm is considered effective at a point in time if it remains profitable as intended when applied in a target market in the future. After the [optimization](glossary) process, we likely have an effective algorithm on the in-sample data set. However, this algorithm is fine-tuned on the same data set, and there’s a possibility of [overfitting](glossary). To determine the effectiveness of an algorithm, we need to assess the algorithm on never-before-seen data that has never been used to build the model or to fine-tune its parameters. This data set is also called out-of-sample data. Note that this data should be sufficiently representative for the performance statistics to be valid.

# Testing the Algorithm on Out-Of-Sample Data

To assess a [trading algorithm](glossary), we need to carefully evaluate its performance on an out-of-sample data set to find and explain performance dissimilarities if any when applied to in-sample data. The assessment also helps understand the advantages, risks, and behavior of the algorithm in different market conditions. This is key to monitor the algorithm during real trading. From this point, we can detect anomalies to manage risks and find opportunities to improve the algorithm.

The effectiveness of a trading algorithm is evaluated by a comprehensive analysis of transaction records. They include net assets over time and statistics on buys, sells, wins, losses, and the times when the net asset draws down. In these metrics, the maximum drawdown is to assess risk, while monthly returns are used to evaluate rewards. The net asset curve provides an overview of both. The detailed transaction statistics report the algorithm’s behaviors.

An algorithm is considered ineffective if its performance on out-of-sample data shows abnormal results compared to in-sample data. Some examples are losing streaks for a long time, sharp drops, excessive deviation of daily returns, or unmatched risk and reward compared to in-sample performance. Investors should carefully research and identify the reasons for these anomalies to determine the algorithm’s effectiveness. For example, it’s advisable to pay attention to market conditions in the data. It’s a possibility of performance mismatch due to differences in market conditions, not because of the algorithm itself.

Figure 14 is a real-world example of the performance dissimilarity of risk and reward performance between in-sample and out-sample data.

A common way to detect the incompatibility of two trading profiles is to use maximum drawdown (MDD) as a metric. The algorithm will be considered ineffective and unusable when it undergoes a sharp drop exceeding a predefined multiple of in-sample MDD. It’s often used to prevent serious losses when the algorithm is applied on the main account with large capital.

# Algorithm Testing Process

The testing process for a trading algorithm has 4 main stages.

**Testing**on Historical Out-Of-Sample Data****

In this first stage, we test the algorithm on historical out-of-sample data. If its result shows potential and similarity to in-sample performance, we can move to the paper trading phase.

**Paper Trading**

In this stage, we test the algorithm on [future data](glossary). That is, the algorithm is simulated to operate in a real-time trading environment. When receiving a transaction order, algorithm developers will not know in advance how it affects the end result. The goal is to ensure no one can predict the performance of paper trading as it operates in real-time.

The main difference between the first two stages is that the historical out-of-sample data may be used repeatedly for several algorithms. It leads to the possibility of an algorithm overfitting this data set, though not trained and validated on it. This phenomenon is called data depletion. Paper trading helps avoid this since it uses completely new data in the system.

If the algorithm still performs well in paper trading, we know that the algorithm is not an overfit and can proceed to the next phase.

**Small-Account Test**

Paper trading simulates the process from placing an order to its completion. This simulation may not be completely accurate due to data limitations in the Vietnam market. For example, it’s not possible to accurately simulate partial order matches in the derivatives market. The small-account test is designed to solve this problem. It tests the algorithm on future data using a real account with small capital.

Although the performance difference between paper trading and small-account tests is unavoidable, the difference really depends on the algorithm, assuming we provide the best simulation of a security company in paper trading using market data. The goal of a small-account test is to quantify this difference.

If the performance does not result in noticeable deviations, the algorithm can proceed to the final stage to make profits for investors. We move on to real trading on the main account with large capital, where close monitoring is necessary when first applied to the target market.

****Live Monitoring During Real Trading****

At this stage, investors can be confident that the algorithm is not an overfit. Yet the algorithm can become ineffective when factors affecting stock prices have changed. The algorithm may need regular retesting in real trading. When the algorithm's assumption is no longer valid, the algorithm needs to be stopped or adjusted accordingly before causing catastrophic losses.

---


# VI. FORWARD TESTING


## 37. Meaning of Forward Testing

*Fonte: https://hub.algotrade.vn/knowledge-hub/significance-of-forward-testing/*

When coming up with a trading idea or a trading strategy, algorithmic traders will model their idea into a specific algorithm. They then use historical data to test whether an algorithm is profitable or not. They evaluate how this profitability will likely continue in the future to make investment decisions.

In a real trading environment, however, the target market often changes. This can lead to many different scenarios. Some algorithms are only profitable when the market trends upward. Some yield profits in trending markets but undergo big losses when the market does not show any particular trends.

In addition, it’s possible the random test data is perfect for the algorithm, leading to highly positive test results. In practice, it may be difficult to repeat the same scenario. Therefore, the process of developing and evaluating an algorithm should try to test many different scenarios to objectively assess the algorithm’s potential before real trading.

Figure 15 illustrates the process that combines past****[future data](glossary) in the algorithm development and evaluation process.

  * **In-sample data** : a part of past data, also known as in-sample past data, to test and optimize the algorithm. Typically 70% of past data will be used for this purpose.


  * **Out-of-sample data** : includes out-of-sample past data and future unseen data. The purpose is to test an algorithm after the [optimization](glossary) phase whether it can generate stable profits. Out-of-sample data and in-sample data should have no overlap.


****

For example, it’s necessary to test algorithms with the recent 10-year price and volume data from 2012 to 2022. The data from 2012 to 2019 will be the in-sample past data and the rest is out-of-sample past data.

The [backtesting](glossary) process uses both in-sample and out-of-sample data. Normally this data set is sufficient to evaluate algorithms. However, since the testing only uses past data, there’s a possibility of common errors such as skipping slippage and overfitting.

To avoid common errors, the evaluation process takes an extra step to test future data.****[Forward testing](glossary), known as real-time algorithm testing, uses out-of-sample data that is not available at present. Its purpose is to add objectivity to the evaluation process while evaluating the algorithm’s feasibility.

Forward testing has two main stages. The first is paper trading, which is similar to real trading but no actual transactions are made. All transactions are simply recorded for further evaluation. The second stage is performed in a real environment with a small amount of capital. It is to finally test the effectiveness of the algorithm, its hypothesis, and any technical issues in the system. This stage is thus called a small account test.

Backtesting and forward testing are both essential in the algorithm development process. Neither is better than the other. High profits and similar results in both types of tests are important criteria to decide whether to use a particular trading algorithm.

---


## 38. Paper Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/paper-trading/*

Paper trading is the first stage of forward testing. [Future data](glossary) is unseen data. Paper trading thus eliminates overfit from backtesting and the parameter optimization phase. In addition, all transactions in this stage are at the present. We can observe each closely and see the context clearly. It’s easier to deduce and explain the algorithm’s behaviors and its efficiency, thereby improving its performance. In practice, this stage typically lasts 2 months. Below are key points of paper trading to keep in mind:

  * _Ensure consistency._ Do not update, or change the rules, or any algorithm parameters. Any small change in this phase can completely lose the meaning of the testing process: the future data set then becomes equivalent to the past data set. Paper trading becomes the [optimization ](glossary)phase. In the necessary event that a new rule or parameter adjustment is required, one should consider restarting the entire testing process.

  * _Ensure real-time._ Simulation in paper trading should be closest to real environments. The only difference is the order matching results returned from securities companies and any price slippage incurred. Taxes and fees should be fully calculated. Ensuring real-time records help [algorithmic trader](glossary)s have an accurate, intuitive view of the algorithm. If any transaction is delayed compared to real-time, the difference between [forward testing](glossary) and [backtesting](glossary) will no longer be meaningful.

  * _Build test criteria prior to starting._ The algorithm is tested to assess its ability to generate stable profits in the future. Paper trading also assesses the similarity between backtesting and forward-testing results. All the criteria need to be defined so the algorithm’s performance can be verified upon completion.


Figure 16 illustrates how an algorithm is evaluated in the paper trading phase.

At the end of paper trading, the algorithmic trader can test the similarity between the trading performance of the out-of-sample and in-sample data, besides the algorithm’s profitability. At the same time, they can estimate the risk and performance of the algorithm as well as reasonable expectations when the algorithm operates in real life. They can also calculate the [Kelly criterion](glossary) and the algorithm’s compatibility with the current system to make the final decision.

Note that a good [trading algorithm](glossary) still has bad time periods when it cannot be profitable. As long as the algorithm behaves similarly for past periods with similar current market conditions, its future profit potential should still be considered.

---


## 39. Small Account Test

*Fonte: https://hub.algotrade.vn/knowledge-hub/small-account-test/*

Before the algorithm goes live, trading on a small account is the testing phase closest to real trading. This phase has the following benefits.

# Hypothesis Testing

All assumptions in the previous testing stages like price slippage, algorithm activations per day, and order matching rate will be revealed in the real environment. However, some specific assumptions can only be tested with large capital accounts and not at this stage.

# Test the Trading System

All other testing phases do not involve the automated trading system directly. This is the phase to fix any remaining bugs and to check how well the algorithm works with the operating infrastructure and the [algorithmic trading system](glossary). The trading system is considered to be working properly when the operating algorithm is 99% stable compared to the ideal assumption. In principle, a small account test should match the results of paper trading. The following are some key differences to consider when evaluating algorithm performance at this stage.

  * _Order matching time._ The previous tests assume that the orders are executed as soon as a signal appears. They do not account for price delays, data processing, and order placements. Comparing order matching time to ensure low deviation (less than 02 seconds) is a very important criterion at this stage to ensure low deviation. For some strategies that require high speed, code execution [optimization](glossary) can improve performance. It reduces execution latency and the possibility of price slippage, maximizing performance and taking more opportunities.

  * _Order execution price._ The execution price is usually assumed at the current price minus slippage. If calculated correctly, this assumption will be reasonable in the long run. If there are 30 or more trades with matched prices higher than the expected 0.3 points in future contracts, traders should verify their assumptions.

  * _Partial or no match._ This case is often overlooked in a trading simulation. However, it’s inevitable in real life with a sufficiently large account.

  * _Matching ratio vs assumption._ Compare the order matching statistics in small account tests with previous tests. It’s especially important for algorithms using limit orders.

  * _Operating time (uptime)._ Check system stability. If the system works under 99% of the trading time, it should not proceed to real trading.


Keep in mind that, for trading multiple algorithms, the trading system has its own testing method. A small account test is only to check how well the algorithm fits with the existing system. It’s not a test for the trading system itself.

# Prevent Overfitting in Sufficiently Long Operations

This is the most crucial point in small account tests: any overfit algorithm will likely fail at this stage. 30 transactions are sufficient to evaluate an algorithm’s operation.

To determine whether poor outcomes of small account tests stem from randomness or faulty assumptions, the [algorithmic trader](glossary) must analyze the situation carefully. More than 95% of the time, the problem lies in making incorrect hypotheses. Pinpointing the root cause will enhance algorithmic thinking greatly.

The example below shows how to use an algorithmic benchmark to evaluate a small account test.

If the test meets either of the criteria above, we can proceed to real trading.

---


# VII. REAL TRADING


## 40. Algorithm in Real Environment

*Fonte: https://hub.algotrade.vn/knowledge-hub/algorithm-in-real-environment/*

After completing 08 stages from hypothesizing to small account tests, the algorithm can now trade on the real market and earn a profit. Handling 100% of transactions automatically is a step towards “financial independence”, “financial freedom”, or “passive income”. However, there are still a few critical aspects to consider in this phase.

# Parameter Setting

The algorithm parameters for real market trading is usually the same as for small account tests, except for capital size. However, this may not be the same with hyper-large capital. It’s because investors have to modify the parameters during operation to ensure the algorithm’s reliability in the real market versus the testing phase. Therefore, market-making and market-neutral strategies require special attention.

# Define Expectations

Based on [backtesting](glossary), [forward testing](glossary), and the algorithm group, traders can set basic expectations for the algorithm to detect any unexpectedly large deviations. Note that the criteria differ for each algorithm. However, here are some common criteria to meet before running the algorithm in real trading:

  * Expected annual profit;

  * MDD;

  * Sharpe ratio;

  * Average slippage.


Some algorithms need learning indicators and these indicators are often more important than the ones above. Some leading indicators for limit order strategies are as follows.

  * Number of signals per week;

  * Number of matched orders/signals.


Traders need to monitor any significant difference in any of the criteria and learn to adapt to this new information, especially during the first 3 months of algorithm operation. They also need to prepare for the worst-case scenario to stop the algorithm at a predefined threshold, usually a multiple of MDD.

# Online Monitoring

At the start of the live operation, traders should monitor online to handle any real-time issues. Such can come from data, algorithms, systems, securities companies, and reporting systems. These issues are especially frequent with the first algorithms. In some special cases, the system cannot close the opened position, and manual intervention is required. After acquiring enough experience, algorithm traders can skip this task.

# Fix Technical Bugs

Even after many testing phases, an operating algorithm is still not free from technical bugs. It’s totally normal to have occasional errors. However algorithmic traders should fix bugs as soon as possible. In our experience, technical failures often happen in the first month, and then drop by 90% in the next months.

# System Fine-Tuning

There are three common factors that lead to system tuning:

  * Financial markets are always changing. Some changes are quick and sudden, such as laws and policies. This can completely change the investment environment and it’s necessary to fine-tune the system to quickly adapt.

  * The original concept to form the algorithm hypothesis has changed. Over time, more data and information are updated, making the initial hypothesis change. As these concepts change, traders should consider testing for plausibility and fine-tuning. If the change is too big, algorithm traders should consider forming a new algorithm instead.

  * Real trading data provide further important information. This is an effective feedback loop in algorithmic trading. Traders create algorithms and algorithms generate data. This gives algorithmic graders more information and more relevant perspectives. They can upgrade the algorithm to a more complete version.


# Capital Allocation

It’s important how the trader will act when the algorithm makes a profit or a loss. Will they use the strategy of having a fixed capital for the algorithm, meaning taking profits if any, and vice versa? Will they choose a compound interest strategy that will use the maximum available capital at each time? This decision can greatly affect the long-term performance of algorithmic trading, especially for multi-algorithm trading.

After backtesting and forward testing in a scientific way, algorithm traders can trust the profitability of their algorithms, at least in the short term without major changes in the environment. They still, however, need to check for risks periodically.

---


## 41. Evaluation of Execution Algorithms With TWAP and VWAP

*Fonte: https://hub.algotrade.vn/knowledge-hub/use-twap-and-wwap-benchmarks-to-evaluate-trade-execution/*

Trade execution evaluation measures and compares how well different execution algorithms work. So traders can choose the best ones to achieve their trading goals and reduce transaction costs.

Execution efficiency is measured by comparing the average order execution price with a reference price. It’s to see if the order was executed too high or too low. Two common reference prices are: volume-weighted average price (VWAP) and time-weighted average price (TWAP).

# **Volume-weighted average price**

VWAP is the average price of all trades executed during the calculation period, weighted by their volume. It’s calculated using the following formula:

Where

– Pi is the trade execution price for trade i;

– Qi is the execution volume of trade i.

VWAP reflects all market activity, supply and demand for all market participants, so it provides a reasonable standard for evaluating trade execution. 

Here’s the formula to evaluate trade performance:

Where

– P is the average order execution price;

– S is the direction of the opened position (S = 1: long position, S = -1: short position)

For example, an investor executes a buy order with an average order execution price of 20,500 VNĐ. VWAP during the trading day is 20.000 VNĐ.

This means that investors bought on average 2.5% higher than other buyers during the day.

# Time-Weighted Average Price

TWAP is the simple average price of all trades executed during the calculation period:

Where:

– Pi is the execution price for trade i;

– N is the number of execution price.

TWAP does not consider trading volume. So investors use TWAP when they want to ignore outlier trades. Outlier trades can be caused by large orders at low or high prices during the calculation period.

Công thức đánh giá hiệu suất thực thi giao dịch:

Where:

– P is the average order execution price

– S is the direction of the opened position (S = 1: long position, S = -1: short position)

# Trading Application

For index investing strategies, especially for mutual funds, the annual returns are usually similar to the benchmark index. In this case, transaction execution may be the most important factor in the end result besides administrative costs, fees, and taxes.

The following is an example of how execution costs affect two index funds.

As shown above, investment fund B performs 2% better than investment fund A. In this example, the only difference in performance is the main reason for the success or failure of the fund manager.

Execution costs also matter for individual investors in Vietnam. Frequent trading and the high volatility of each stock can make individual investors overlook the impact of execution costs. However, with an account turnover rate of 2 times per month, i.e. 24 times per year, an average execution cost of 0.5% is equivalent to 12% annually. In a normal market, it would not be surprising if 95% of individual investors lose money with this execution cost.

---


## 42. Measuring Implementation Shortfall

*Fonte: https://hub.algotrade.vn/knowledge-hub/measuring-implementation-shortfall/*

To test if the [trading algorithm](glossary) works well in real trading, we need to compare the paper trading results and the actual trading results. Algorithmic traders can start by measuring and analyzing the reasons for any differences. They should fix problems that might happen during trade execution. A commonly used analytical method is to use [implementation shortfall](glossary).

# Formula

The implementation shortfall (IS) measures how much the paper profit differs from the actual return. We can use the following formula:

Paper return is the theoretical profit if we could fill all our orders at the desired price and volume without incurring any costs. The formula is:

Where:

– S is the total volume of open positions, S > 0 in the case of opening a long position, while S < 0 for a short position;

– Pd is the price when we decide to open a position;

– Pn is the current price.

The actual return is what we really earned based on executed trades. We can use this formula:

Where:

– sj is the matched volume in the transaction j;

– pj is the matched price in transaction j;

– Fees are transaction fees and applicable taxes.

Combining the above formulas, we get:

IS is decomposed into three components, explaining the three reasons for the discrepancy:

  * _Price slippage:_ the price may change and may not match our plan from the decision-making moment to the time of placing an order.

  * _Opportunity cost:_ matching volume is not enough compared to our plan;

  * _Fees:_ transaction fees and taxes.


Price slippage can be further decomposed into two more components: delay costs and transaction costs.

Where P0 is the stock price at the time of placing the order.

  * _Delay cost:_ when an order cannot be placed immediately after the decision is made, it results in a price change from the decision-making moment to the time of order placing.

  * _Transaction cost:_ depending on market liquidity, order type (limit order, market order, etc.), or system errors may result in orders being matched at different prices.


# Example of Implementation Shortfall

Assume that at 09:15, the share price of VINGROUP (HOSE: VIC) is 60,000 VND per share, and we decide to buy 10,000 VIC shares.

At 09:20, the system starts to place orders. At this moment, the stock price has gone up to 60,100 VND.

At the end of the day, the closing price of VIC is 60,800 VND.

By the end of the trading day, we can only buy 8,000 shares and pay an average fee and tax of 200 VND per share

Below is the detailed matching orders:

Implementation shortfall is as follows:

Delay cost = 8.000 × 60.100 − 8.000 × 60.000 = 800.000

Transaction cost = 482.500.000 − 8.000 × 60.100 = 1.700.000

Opportunity cost = (10.000 − 8.000) × (60.800 − 60.000) =1.600.000

Fees and taxes = 8.000 × 200 = 1.600.000

Implementation shortfall = 800.000 + 1.700.000 + 1.600.000 + 1.600.000 = 5.700.000

Implementation shortfall is not always bad. In many cases, they can help us trade at a better price, or trade less and avoid a big loss when there’s a delay in trade execution.

However, algorithmic traders should be fully aware of the implementation shortfall and need to measure and evaluate the causes and implement reasonable solutions to ensure the costs don’t get out of control. For example, we can reduce the delay costs by placing orders faster after we decide to trade. An [algorithmic trading system](glossary) can optimize this to under 60 milliseconds.

In the case of high-volume trading on a market with low liquidity, implementation shortfall would be the top priority. In this situation, we can consider execution algorithms like VWAP and TWAP.

---


# VIII. EVALUATION CRITERIA FOR ALGORITHMS


## 43. Return Rate

*Fonte: https://hub.algotrade.vn/knowledge-hub/evaluation-of-algorithmic-performance/*

Return rate assessment is the process of measuring the profitability and the risk of a trading algorithm over a specific time period. It can be used to answer the following questions:

  * Is the return rate high or low, compared to which benchmark?

  * Is the algorithm taking too much risk to increase its chances of making a profit?

  * Is the algorithm profitable due to skill or luck?


# Relative return rate

The relative return rate is the rate of return on a portfolio relative to a benchmark. The benchmark is selected depending on the nature of the algorithm. For example, a [trading algorithm](glossary) that trades underlying stocks may use the VN-Index benchmark, while a market-neutral algorithm may use the risk-free rate instead.

For example, algorithm A trades underlying stocks under a dominant beta strategy, while algorithm B trades on a market-neutral approach. During the same 1-year period (Jan 1, 2021, to Dec 31, 2021), both algorithms achieved a return rate of 20%.

In absolute terms, the two algorithms are equally profitable. However, in relative terms, there’s a big difference. It’s due to the two algorithms having different benchmarks. For algorithm A, the benchmark is the VN-Index, which actually increased by about 34% during the comparison period. For algorithm B, the benchmark is the 3% risk-free rate.

The two algorithms have equal absolute returns but different relative returns. Algorithm A has a worse result than the benchmark (20% - 34% = -14%), while algorithm B has a better result than the benchmark (20% - 3% = 17%). This difference is most evident in bad years in the market.

# Sharpe ratio - return on risk

The main goal of investing is to maximize returns. However, the higher the return, the higher the risk. Therefore, when evaluating the rate of return, it’s necessary to consider the risk factor altogether.

The [Sharpe ratio](glossary) , named after the American economist William Sharpe, can solve this problem by dividing the return rate by the risk parameter. This allows for the evaluation of the investment performance on the basis of balancing between return and investment risk.

The formula for the Sharpe ratio is as follows:

Sharpe ratio = (Rp – Rf)÷σp

where:

– Rp is the portfolio’s return

– Rf is the risk-free return rate

– σp is the portfolio’s standard deviation, representing risks. The Sharpe scale rating threshold is as follows:

In the algorithm [optimization](glossary) stage, it’s necessary to consider whether additional profits are due to rational optimization or simply taking on higher risks. Instead of focusing on increasing the expected return, investors should focus on increasing the Sharpe ratio. A high expected return is good, but it’s only optimal if it doesn’t excessively increase the risk.

# Skill or luck

Imagine two investors A and B randomly buy a stock and hold it for a year. Investor A’s stock price goes up many times while it’s the complete opposite for investor B. Does that mean investor A has better investment skills than investor B?

Sometimes, high profits are just a matter of luck. An algorithm that has a stable performance can still suffer big losses due to unforeseen events. On the other hand, an algorithm that has very high profits but has only a few trades may just be lucky rather than effective.

When an algorithm has enough trades, the random factors will cancel each other out. It’s important for algorithm traders to distinguish between luck and skill in their trading process. To achieve consistent returns and beat the average market over the long term, skill always matters more than luck.

However, the return rate is not the only aspect that needs to be considered to fully evaluate the algorithm’s performance. One aspect is the worst-case scenario when running the algorithm. What should be done when the losses exceed the acceptable limit? This issue will be discussed in the maximum drawdown (MDD) article.

Another aspect is how to use leverage effectively. When and how much leverage should the algorithm use? The formula to find the optimal leverage parameter will be presented in the article on the Kelly criterion.

---


## 44. Maximum Drawdown in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/maximum-drawdown-in-algorithmic-trading/*

When trading stocks, investors are often concerned with the following risk-related questions: “How much money am I likely to lose if the market moves in a direction that is not as I expected? How long will it take me to get back to my original position if a loss unfortunately occurs?”

To answer these questions, we can use a concept called drawdown. Drawdown is the percentage of capital lost from a peak to the lowest point before a new peak is reached.

For example, suppose an investor buys FPT stock at 100,000 VND. The stock then rises to 115.000 VND (creating a new high) and then falls continuously to 90.000 VND (creating a new low). The stock then recovers and is currently priced at 117.000 VND (new high). The drawdown in this example is:

(115.000 - 90.000) ÷ 115.000 = 21,74%

# Maximum Drawdown (MDD) In Algorithmic Trading

In algorithmic trading, investors can continuously open and close many different positions. These positions will contribute to an increase or decrease in the total investment. Suppose an investor has 1 billion VND of initial investment to invest in an [algorithmic trading system](glossary). The invested capital changes over time as in Figure 18.

During the running time of the [trading algorithm](glossary), there may be different drawdown time periods with different values. The one with the largest value will be called Maximum Drawdown (MDD). In the example above, MDD will be 17.24%. MDD can be understood as the worst loss situation occurring in the timeframe under consideration.

# How to Use MDD

The theoretical MDD from [backtesting](glossary) can be used to estimate the potential risk of the algorithm in real trading. However, if the real MDD exceeds the backtest MDD significantly, it means that the latter is no longer reliable. In that case, investors should pause the algorithm to review its performance.

At ALGOTRADE, we will stop and review an algorithm when its real MDD reaches 150% of the backtest MDD. This is based on the assumption that the historical data used for backtesting may not fully capture the long-term performance.

The table below compares the backtested and real MDDs of our current algorithms, as of Apr 1, 2023.

From these MDDs, we can see that the “Moon” algorithm involves the highest risk, while the “Genesis” algorithm is the safest. When allocating capital to different algorithms, investors can use MDD as a parameter to make decisions based on risk tolerance and return expectations.

---


## 45. Kelly Criterion – Definition and Application

*Fonte: https://hub.algotrade.vn/knowledge-hub/kelly-criterion-definition-and-application/*

The [Kelly criterion](glossary) is the optimal ratio of assets to risk on each trade to maximize the long-term results. Different algorithms may need different amounts of capital or different amounts of leverage to perform well. The Kelly criterion shows that it’s not always optimal to risk 100% of our assets on every trade.

# Kelly’s Formula

The Kelly criterion was first developed for a game to find the optimal ratio to bet. In this game, you either double your money or lose it in every bet. For example, suppose you have a 60% chance of winning on each bet and you can bet 300 times. Intuitively, if you bet all your capital every time, you would go bankrupt sooner or later even with a positive expected return on each bet. The optimal bet should thus be less than 100%.

The formula for the best bet is:

f* = p - q÷b = p - (1 - p)÷b 

where:

– f* is the optimal percentage to bet;

– p is the chance of winning;

– q is the chance of losing (q = 1 − p);

– b is the ratio between the amount won to the amount lost.

We can explain this formula as follows:

Kelly(%) = Chance of winning − Chance of losing ÷ (amount won ÷ amount lost)

Using the formula for the example above:

Kelly(%) = 60% − 40% ÷ 1 = 20%

So betting 20% of your total money is the best strategy in this example.

Note that this formula implies that you should never bet on anything with a negative expected return.

# Investment Formula

Investing often involves partial losses, unlike gambling where the player may lose everything. There’s a need for a more universal form of the Kelly criterion to be applicable in the investment field:

f* = p÷a - q÷b

where:

– f* is the optimal percentage to bet;

– p is the chance of winning;

– q is the chance of losing (q = 1 − p);

– a is the percentage of capital lost when losing;

– b is the percentage of capital gained when winning.

One of the challenges of using Kelly is that it requires knowing the exact return on investment for each scenario, which is very hard to do in investing. Therefore, the Kelly criterion is not very popular among investors.

# Kelly Criterion for Algorithmic Trading

According to the law of large numbers, algorithmic traders can estimate the long-term outcomes of their investments, such as expected return, MDD, winning rate, losing rate, and the profit or loss ratio in each case. These parameters enable the use of the Kelly criterion.

For example, after carefully [backtesting](glossary) and [forward testing](glossary), an [algorithmic trader](glossary) finds out an algorithm has the following performance and expectations:

Intuitively, if two consecutive trades have 1 successful and 1 unsuccessful trade, this algorithm will make this profit:

(1 + 2%)*(1 - 1,84%) - 1 = 0,12%

This profit margin is small, so the trader uses maximum leverage to maximize their profit. In the Vietnamese derivative market, they use the default leverage of 5, hoping to make a profit of 0.12%*5 = 0.6% after one losing trade and one winning trade.

After a year of trading, they keep losing without knowing the reason. The Kelly criterion is the answer.

A good algorithm turns into a losing investment by using the default leverage on the Vietnamese derivatives market.

To find the optimal leverage parameter, Kelly’s formula can be applied as follows:

f*= 50%÷1.84% - 50%÷2% = 2.17

Using the Kelly criterion as above, the algorithmic trader will make a significant profit instead of a loss, while only using parts of the leverage. This approach can also benefit the entire trading system, as it allows another algorithm to take advantage of the unused capital. 

Note that using too much leverage will increase borrowing costs and transaction fees. It will negatively affect the final performance of the algorithm.

The Kelly criterion is a decisive parameter for algorithmic traders in gold, forex, and crypto markets. In these markets, the leverage can be up to 500 times the invested capital.

---


# IX. OPTIMIZATION IN MULTI-ALGORITHM TRADING


## 46. Capital Optimization on Multi-Algorithms System

*Fonte: https://hub.algotrade.vn/knowledge-hub/capital-optimization-on-multi-algorithms-system/*

[Optimization](glossary) is a common topic to improve investment results. But how can traders optimize capital allocation among different real-time trading algorithms in real-time? This article explains an approach to optimize that in real time.

# Basic Approach

A simple way is to allocate a separate account for each algorithm. So that the account balance reflects each algorithm’s performance. This method is straightforward and suitable for traders who use only one single algorithm. The need for multi-algorithm optimization arises when running multiple algorithms at the same time.

To illustrate this point, let’s look at an example from the Vietnamese derivatives market:

Using the basic approach, we would need three separate accounts with a minimum of 40 contracts each, for a total of 120 contracts.

# Integrated Approach

Another way is to merge all three algorithms into one single account. This way after integration will hold 10 short contracts (20 long contracts and 30 short contracts) instead of 50 contracts. In addition, the minimum capital will be reduced from 120 to 80 contracts. The calculation is as follows:

Minimal capital = Current portfolio + Capital balance = 10 + (20 + 10 + 40) = 80 

# Comparison Between the Basic and Integrated Approach

The integrated approach can achieve the same performance as the simple approach while lowering the initial investment by 33.33%. This is a significant advantage in algorithmic trading.

What if all three algorithms at the same time have long positions? How does the integrated approach handle this situation?

# Optimization

To answer this question, we need to consider the following factors.

In this context, 99% of the operational capacity means we are willing to miss one trade out of every 100 trades.

To get the right answers to the questions above, we need to check all the past trades. The trick here is to trust the law of large numbers and not stress too much about missed trades. A system that has a 20% expected return at 100% capacity will yield a 19.8% expected return at 99% capacity.

For instance, if an [algorithmic trader](glossary) gives these answers,

We can estimate the system’s expected return as follows:

This indicates that capital optimization has a major impact on the overall account performance.

ALGOTRADE currently opts to operate at 99% capacity. This decision ensures that the system benefits from the concurrent operation of multiple algorithms while reducing the performance loss due to missed trades. The key message is to accept missing 1-5% of trades for the greater good of the entire system.

# Implementation

  * _Accounting feature._ We need an internal accounting system to separate the trade records and the algorithms’ performance since they all run on the same account.

  * _Risk management feature._ A multi-algorithm account can face a domino effect that can stop the entire system or cause huge losses. We need proper risk management to ensure the safe operation of the whole system. Also, we need to prepare for the scenario of zero capital balance, in case the system sends continuous requests and accidentally causes a DDoS attack on the broker’s server.

  * _Queuing feature_**.** Sort signals by priority queue where delayed signals are listed in the 1% - 5% rare and never executed. In Vietnam’s algorithmic trading environment, we can limit latency to 100 milliseconds.


Optimizing the capital for multi-algorithm trading will be a big challenge in the beginning, but the rewards will be well worth it. Professional algorithmic traders should seriously consider this optimization to scale the system exponentially.

---


## 47. Beta Optimization

*Fonte: https://hub.algotrade.vn/knowledge-hub/beta-optimization-on-multi-algorithms-system/*

Imagine your system trades a lot of positions on a typical day. Then a rare “black swan” event happens. You realize the system has accumulated too many positions in the same direction, and your total capital is severely affected. How can you prevent such events in the future? This article will help you through these situations.

# Prerequisites

The system must be able to generate alpha for beta [optimization](glossary) to be beneficial.

These parameters can be legally done through all major brokers in Vietnam.

# Beta Optimization

A professional trader in Vietnam usually has an absolute beta between 1.5 and 3. We recommend an optimal beta range from 0.8 to 1.2, with an acceptable beta range is 0.5 to 1.5. This metric, though not mathematically proven, can be estimated on the following basis.

First, the market always grows in the long run due to economic growth. At a conceptual level, a long position is more profitable in the long run than a short position. We favor the algorithm with more chances of opening a long position to take advantage of the general market beta. While big losses do happen in times of crisis or catastrophic macro events, it’s the risk that a system must accept. The beta strategy achieves about a 7% annual return in the Vietnamese stock market. The return rate is similar to a savings account, while there are more risks in the stock market. However, the assumption of a 7% annual return supports the concept of a positive beta system.

Second, keeping beta between 0.8 to 1.2 makes the system more resilient to unexpected black swan events. The system can withstand any market crash unless all assets become worthless.

Third, the optimal beta helps reduce margin costs. In the long term, borrowing is not a good strategy. As of 2022, the margin rates in Vietnam range from 9% to 14% per annum.

Finally, with a beta of 1 (and a portfolio split evenly between stocks and derivatives), there’s still 40% of the capital left for other strategies such as the market-neutral strategy. The alpha from these strategies from this 40% capital can boost the performance in tough times and diversify the system further.

# Suggestions When the Beta Is Outside the Optimal Range

  * _Below lower limit:_ prioritize algorithms that favor long positions and avoid opening more short positions.

  * _Above upper limit:_ prioritize algorithms that favor short positions and avoid opening more long positions.


In simple terms, when the system overbuys, it will ignore any coming buy signals and only accept neutral or the opposite signal. It will miss out on profits from a long position and lose everything from a black swan event.

When the system has many long positions or short positions, with the same winning probability, opening a position in the opposite direction will be much more profitable in the long run.

---


## 48. Leverage Transaction Data

*Fonte: https://hub.algotrade.vn/knowledge-hub/leverage-transaction-data/*

# Importance of Trading Data in Vietnam

In the Vietnamese derivatives market, API data, live boards from data providers are not actual order matching data.

The table below is an example data source that returns VN30F1M at 11:29:58, matching 820 contracts at a price of 1082. This data can be interpreted as around 11:29:58, there are 820 contracts reached at the 1082 range. The standard margin of error is usually around 0.3 points when the market has low fluctuation. However, it can go up to several points in the case of high volatility. For example, the deviation can be up to 30 - 40 points in the case of “call margin”.

The cause of this deviation is due to the phenomenon of “tick aggregation” - adding up many ticks in a period of time and returning a single tick. In Vietnam, the ticking time usually falls in about 02 seconds. The data returned can also be delayed by several minutes or even be unavailable for a period of time due to usually unpublished reasons. This means that, even with access to the best data source in Vietnam, the data still has deviations from reality. Therefore, traders may consider using algorithm-generated trading data to collect hidden data with absolute precision.

# Conditions to Collect Trading Data

The necessary condition is a high-frequency [algorithmic trading system](glossary). The data is returned continuously enough to reflect the general market, especially at sensitive times when the actual matching price and the hypothetical price highly deviate.

The sufficient condition is that the system should have many algorithms enough. Algorithm diversity will picture a market overview, thereby detecting favorable market conditions for each algorithm and vice versa. Furthermore, trading algorithms need to have a variety of strategies to avoid collecting the same data. Various trading strategies with different order types will enrich trade data. A typical example is the momentum strategy will give market execution data while market making strategy will give limited order matching data.

# Practical Application

The first application of order matching data is to estimate the extent of market slippage. From thousands of orders matched, slippage can be calculated with high confidence. It helps increase the reliability of [backtesting](glossary) and paper trading. It should be noted high slippage is detrimental for algorithms using market orders but advantageous for algorithms with limit orders.

Traders should also get statistics of “sensitive” times of the market when the algorithms operate at a completely different speed compared to the average. At these times, the transaction frequency can be up to 10 times higher than normal. Any system improvement will bring outstanding results for automated trading.

Another important application of order-matching data is to form market expectations, thereby optimizing capital allocation to different trading strategies. An example is for the [momentum trading strategy](glossary) and mean-reversion strategy.

The last is to catch unusual transactions in the market, bringing operational advantages to the system. The principle is that if an unusual event occurs frequently, it’s likely an important signal to follow.

Combine market data and trading data helps ALGOTRADE adapt to different scenarios. For example, our system still operated reliably when live boards and market data in Vietnam were not stable during the Covid-19 pandemic.

---


# X. ALGORITHMIC TRADING PRACTICE


## 49. Models or Randomness

*Fonte: https://hub.algotrade.vn/knowledge-hub/models-or-randomness/*

In finance, it’s difficult to distinguish between skills and luck. In the short term, luck can be up to 95% of total results. In the long term, however, skills will be 95% of the total results instead. Proven algorithms eliminate luck or randomness in the long run and they are important milestones for [algorithmic trader](glossary)s to succeed.

Here are the 3 price charts of stocks A, B, and C over the last 1000 days. In your opinion, which stock will trend up, trend down, or trend sideways?

Mark your answer below and see the right answer.

Do you think stock A will go sideways or trend down without recovery?

Do you believe stock B will rise strongly? Do you stock C will move into a correction in the near term?

The final answer for all three stocks cannot be predicted. It’s because the three graphs above are purely from a lab simulation. It simulates the next day’s price is normally distributed around the previous one, ranging from -7% to 7% (statistics from HOSE standard deviation).

The truth is the next day’s price is random, unpredictable, and independent of the previous 1000 days in all graphs above. This is a prime example of a striking similarity when comparing price change by model and by randomness.

# The Danger of Confusing Patterns and Randomness

If an algorithmic trader finds a winning model from thousands of stocks like A, B, and C, what would the long-term outcome be? According to the law of large numbers, no matter what models were discovered, investors will have their assets slowly decline due to the effect of fees, taxes, and slippage. This is the main reason why most passive trading funds are more efficient than active funds, with management and trading fees included. In other words, in a stochastic market, excessive trading can only lead to excessive losses with unmeasurable fees.

In the financial world, the biggest reason that causes the confusion between a predictive model and randomness is that wrong investments can still make profits and vice versa. In other professions such as musicians, pilots, engineers, and artists, the right decision will usually have corresponding positive feedback and vice versa. In finance, the feedback typically has lots of noise. Following a few specific cases can lead investors in the wrong direction. What if you make a bad investment but still get profits five times in a row? Or conversely, what if you make a great decision but suffer losses five times in a row?

This confusion can bring extremely negative results in the long run. As an example, inexperienced investors with no knowledge of the stock market can still make profits as large as multiple times of their investment assets. At that point, they may feel like they already identified the right investment model and start using margin and debt instruments, or receive investment trusts. However, when a catastrophe happens, these investors may lose all the profits accumulated from the previous period.

This investment model has been widely popular during the Covid period when new investors entered the market and accidentally made huge profits in just a very short time. This pattern will likely continue in the future and is not limited to the stock market.

# How to Identify Predictive Models

Distinguishing patterns from randomness is a complicated process since they both appear exactly the same. Even randomness may yield better results in the short term. There are two main methods to identify patterns and avoid randomness in algorithmic trading:

First, use multiple rounds of rigorous testing with a large number of transactions to ensure that the odds to gain long-term profits after all fees and taxes are much greater than the 50% threshold. Algorithmic traders need to understand the steps of [backtesting](glossary), [optimization](glossary), and [forward testing ](glossary)for detailed implementation.

Second, use economic fundamentals in forming the algorithm hypothesis. A profitable algorithm is not everything. It needs a solid explanation. For example, a stock from a well-performing company with trustworthy reports is much better than a sharply rising stock for unknown reasons. In the long term, algorithms using machine learning may grow beyond human understanding. However, in the long term, understanding the source of profits will ensure the system operates stably and builds sustainable growth.

---


## 50. Is Algorithmic Trading a Zero-Sum Game

*Fonte: https://hub.algotrade.vn/knowledge-hub/is-algorithmic-trading-a-zero-sum-game/*

A zero-sum game is a competitive scenario where one side’s gain is equal to the other side’s loss. In algorithmic trading, for example, if one investor makes a profit, does that always mean that other investors will lose money?

**Is Stock Investing a Zero-Sum Game?**

Before we get to the key question, let’s take a look at general stock investing with a hypothetical scenario.

Five investors A, B, C, D, and E pooled their capital to start an ALGOTRADE company, with an initial capital of 100 billion VND. Each invested 20 billion VND and owned 20% of the company’s shares.

Three days later, A decided to sell all his shares to G. A agreed to sell at a loss for just 18 billion VND to speed up the process.

A few days later, G found H, who was optimistic about ALGOTRADE’s potential, and offered to pay 23 billion VND for all 20%, and G agreed to sell.

In just a short term, nothing special happened in the business and the total value of ALGOTRADE remained at 100 billion VND. G made a short-term profit of 5 billion VND, while A lost 2 billion and H lost another 3 billion due to paying 23 billion VND for an asset worth 20 billion VND only. The sum of all six investors was zero.

****

Two years later, ALGOTRADE prospered and the company’s value increased 150% to 150 billion VND. The share price of the investors thus rose accordingly.

The cash flows of all six investors over these two years were as follows:

****

After two years, the total net benefit of all six investors was 50 billion VND, even though A still lost 2 billion VND.

If there are no major events in the short term like war, natural disasters, etc., the core value of a business hardly changes in a few days. Buying and selling stocks for short-term gains can be seen as a zero-sum game.

In the long term, if there are macro and micro events directly affecting the business fundamentals, the total welfare of the inventors will be either greater or lower than zero depending on the events. In other words, investing in stocks over the long term is a non-zero-sum game.

From a positive perspective, the profits of publicly listed companies tend to grow over time along with general macroeconomic growth. Investors will share the good performance of the business - a game with a sum greater than zero where everyone wins.

**Is Derivatives Trading a Zero-Sum Game?**

Ignoring taxes and fees, VN30F futures trading is a zero-sum game because all of the trading cash flow is not put into businesses, only transferred from losers to winners. In fact, if all fees and taxes are included, it results in a negative-sum game.

**Is Algorithmic Trading a Zero-Sum Game?**

Whether algorithmic trading is a zero-sum game depends on the strategy used. Some strategies are based on short-term movements like scalping and day trading. These are prime examples of a zero-sum game. In the long term, without a clear alpha, these strategies will lose money because of taxes, fees, and price slippage.

Most other investment strategies have a positive sum, where the total benefit is greater than zero. A good example is long-term investing using algorithms that expect to profit from the overall growth of the economy. This is a positive-sum game, where everyone wins in the long run.

Moreover, when the market is inefficient, information is not updated fully, quickly, and transparently, and the process of evaluating and analyzing information becomes inaccurate. The process of making investment decisions becomes inefficient. As a result, the stock price deviates significantly from its true value. It results in huge wins and heavy losses. It’s also a zero-sum game but with a wide gap between winners and losers. This can have negative consequences for the overall stock market and the economy: liquidity decreases, good businesses have difficulties raising capital for production and cannot create added value in the long term. Algorithmic trading strategies like arbitrage,****[market neutral strategy](glossary), etc. can help increase the market liquidity and reduce the gap between winners and losers in the short term, making the market more efficient. When the economy grows steadily and sustainably, all investors will win in the long run.

The execution algorithms that reduce trading costs in large-volume transactions are also not part of the zero-sum game. 

Especially, the market-making algorithms help increase liquidity, match trading orders, and also contribute greatly to the development of the general market.

****

In conclusion, an investor’s approach will decide whether they are participating in a zero-sum game or not. Certainly, positive-sum games are always beneficial for investors in the long run.

---


## 51. What to Do When in Doubt of Your Trading Algorithm

*Fonte: https://hub.algotrade.vn/knowledge-hub/what-to-do-when-second-guessing-your-algorithm/*

The market appears to plummet, but your algorithm is about to likely open long positions. Would you decide to interfere with the system and place orders manually?

You may be tempted to override an algorithm and trade manually when the market seems to go against it. This is a common mistake for inexperienced algorithmic traders. You implemented the algorithm, and you may think you know better than the algorithm does. In reality, however, interfering with an operating algorithm may do more harm than good.

# Four Consequences From Interfering With the Algorithm

  * _Drive emotional trading._[Algorithmic trader](glossary)s leverage computers and tested algorithms to make rational decisions. If you abandon this advantage for a gut feeling, you are going against the essence of algorithmic trading. Every time you interfere with the automated system, you move further away from becoming a true algorithmic trader. You should always be careful not to cross the line between intervention and non-intervention. In the long run, fully trusting the algorithm can help you build a successful career. It will also motivate you to be confident and thorough in every algorithmic aspect. This mindset will benefit you greatly in the future.

  * _Increase your stress and reduce your self-confidence._ There are two possible scenarios when you stop the algorithm and open a position in the opposite direction. If you make a profit, you will lose confidence in the algorithm. This is frustrating since you will have to decide every time your feeling differs from what the algorithm does. Should you let the algorithm run or manually intervene as you used to? If you make a loss, you will waste your efforts and feel regretful. The short-term results may vary, but the long-term results are the same: you become stressed and lack confidence.

  * _Reduce your free time._ The biggest reward that algorithmic traders get is free time. If you give up automated trading for manual trading, you will have to spend all your time monitoring the algorithm to intervene at the right moment. Whether you make a profit or not, you are giving up the best benefit of algorithmic trading.

  * _Invalidate your statistics._ What**** do the statistics of your algorithm mean after interventions? Nobody knows because the data is no longer reliable. This will make it very hard to evaluate and improve your algorithm.


# What to Do When You Doubt Your Algorithm

The answer is to try to exploit new ideas without interfering with the running algorithm. Below’s a model to explain this concept.

If your doubt is purely emotional and not quantifiable, you should consider doing nothing. Sometimes, the doubt may persist. One trick to help relieve emotional pressure is to make small trades on another account. This way, you can satisfy your emotion and keep the integrity of your algorithmic data, while also having manual data for analysis.

If your doubt is quantifiable, you should save the idea and consider it as a potentially new algorithm, or a new feature for future development.

This approach preserves valuable information from your doubt if it exists while keeping the running algorithm untouched. In the long run, this will be very helpful for harnessing both your creativity and your trust in your algorithms.

---


## 52. Scams in Algorithmic Trading: 07 Major Characteristics

*Fonte: https://hub.algotrade.vn/knowledge-hub/scams-in-algorithmic-trading-07-major-characteristics/*

Some scammers often use high-tech terms like neural networks, artificial intelligence, machine learning, and market sentiment in algorithmic trading to deceive naive investors and make unrightful income. This is quite common in Vietnam’s stock market. Investors can save a lot of money by knowing the 07 key features of scammers in algorithmic trading.

## **1\. 100% Success Rate**

The first rule of a scammer is to appear perfect to the victim, never losing in any trade. This creates an illusion for investors that winning is easy. If an investor sees someone claiming or showing themselves as an absolute winner in any way, they have probably found a scammer.

## **2\. Fail to Provide a Complete Statement**

A scammer cannot have a good transaction statement, so they cannot provide this information. At best, the scammer can only show some profitable trades but never a complete statement.

## **3\. Always Announce Position Opening/Closing Points Late**

The scammer cannot provide real-time position opening/closing points because they do not exist in the system. Instead, they announce the positions after the fact to ensure a 100% success rate.

A typical example is that in a bull market scenario . A scammer will post a chart image like the one above with colorful indicators and claim: bought VN30F1M at 1045.0 points and imply an unrealized profit of 10 points.

The result of this late announcement in position opening/closing is that the unrealized attractive profits are never executable.

There’s a term for this type of scammer: “time machine” traders. They are traders who can buy and sell in the past.

The stereotype for this group is as follows:

  * If VN30F1M increases by 5 points, they announce they purchased at the current VN30F1M price minus 5.

  * If VN30F1M decreases by 5 points, they announce they shorted at the current VN30F1M price plus 5.


## **4.**Hyperactivity****

Scammers need to constantly impress and reassure their investors with their fake ability to generate high returns and consistent wins. To keep up the illusion of stability, scammers will devote most of their time to providing false information that shows a steady win every day. In some extreme cases, scammers will claim to have made a profit every 15 minutes or less.

## **5\. Lead to Internal Channels**

Scammers rely on “service fees” as their income source. They have to persuade inventors to join some exclusive private channel. In Vietnam, these channels are usually chat groups like Zalo or Telegram. Scammers will use various tactics within the private chat group to extract “service fees” from investors. Some other scammers may offer complete investment authorization services where investors may never get their investment back.

Note that in private channels, about 95% of all accounts are fake and are controlled by scammers to create a bandwagon effect. This effect is meant to convince the victim of the scammer’s superior skill and make it easy for the victim to fall for the scam.

## **6\. Personal Attack Right After Bei Criticized**

A perfect image is crucial for attracting more victims, so any criticism will be taken very personally by the scammer. This is a hidden feature that investors can test to see how scammers react. Remember scammers often control multiple accounts to ensure their majority in any argument.

## **7\. No Programming Skills**

Since scammers spend most of their time and energy in luring naive investors, scammers won’t have any time to learn or practice any programming skills. This group usually has no programming knowledge or skills at all. A simple direct question on programming will usually be ignored.

The philosophy of scammers is to make naive investors believe in the possibility of making money quickly without any risk. By understanding the philosophies of algorithmic trading scams and the characteristics of scammers, investors new to algorithmic trading can avoid falling into these traps.

---


## 53. Third-Party Software in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/third-party-software-in-algorithmic-trading/*

In Vietnam, [algorithmic trader](glossary)s can be divided into 2 groups. The first trades via third-party software such as AmiBroker, MetaTrader, and TradingView, in the order of popularity. The remaining built their own system, from as simple as Excel, to as complex as Python, C, and Java. The third-party software group accounts for about 80% of the algorithmic trading community in Vietnam.

# About AmiBroker

AmiBroker is a user-friendly software that only requires basic programming skills. It can be used by different types of investors, from beginners to experts in algorithmic trading.

The software can handle various types of data sources. The easiest one is historical data that can be used to backtest trading strategies. Another option is to buy real-time data from vendors for an annual fee of around 01 to 05 million VND. However, this option may have some drawbacks such as high latency and data errors. Alternatively, traders can collect their own data for free and make the program themselves with low latency using the AmiBroker DLL plug-in.

AmiBroker is designed specifically for****[backtesting](glossary) and technical analysis. The software provides many tools to analyze market data and calculate technical indicators. The advantage is the speed of testing and [optimization](glossary). To fully automate the trading system, users need to use APIs provided by securities companies. A disadvantage of AmiBroker is that the standard format for input data only includes OHLCV, Aux1, Aux2. Other factors such as financial statements, market sentiment, news and events are not taken into account in technical analysis. However, users can directly fill in the parameters on the AFL files (AmiBroker Formula Language - a programming language designed by AmiBroker) or import the TXT file to add data.

Let’s compare the pros and cons of using third-party software versus building a Python and API system for algorithmic trading.

# Pros

  * _Reliable._ These software are used by hundreds of thousands of traders around the world, so they are very stable and dependable. Investors can trust them to run smoothly and consistently.

  * _Time-saving._ Building a trading system that covers all the basic functions can take years or even never be completed. With AmiBroker, MetaTrader, and TradingView, investors can have a ready-made system in a few hours at a reasonable cost.

  * _Excellent for technical analysis._ These software originated from foreign exchange market (Forex), so they have great features for technical analysis traders who use price and volume data as inputs.


# Cons

  * _Hard to customize._ These software are designed for the global market. Any changes to adapt to Vietnamese market conditions will be challenging.

  * _Lack of fundamental data for the Vietnamese market._ Information on financial reports of companies listed in Vietnam is usually not fully integrated. If investors want to carry out in-depth fundamental analysis, AmiBroker and MetaTrader will unlikely be satisfactory.

  * _Hard to access account positions._ Investors can only access account information through the API, so AmiBroker and MetaTrader cannot automatically know the account status, which may lead to many unnecessary trading errors. However, there’s the AmiPy plug-in for algorithmic trading, though it requires Python programming skills.

  * _Limited support for multi-algorithm trading._ AmiBroker and MetaTrader can only support one algorithm per account.


The table below summarizes the experience of using third-party software versus the Python API system in Vietnam.

Investors can use both AmiBroker and Python to optimize the trading system. Python has many libraries that support data analysis and statistical computation, which investors can use to build predictive models, combine different data sources, and analyze data at high speed. Machine learning is a new trend in algorithmic trading that investors can only accomplish with Python.

The most important factor in choosing an algorithmic trading approach is suitability. Third-party software is geared towards beginners who need a quick and easy algorithmic trading experience. To become a professional algorithmic trader who can develop various trading strategies, investors will need a trading system that can be customized to a high degree.

---


## 54. Is Algorithmic Trading Preferable for All Traders

*Fonte: https://hub.algotrade.vn/knowledge-hub/is-algorithmic-trading-appropriate-for-all-investors/*

In the future, algorithmic trading will dominate the Vietnamese market. However, it will be accessible only to a few investors or institutions. It’s still not a tool for the mass market. The following are some types of investors or institutions that can benefit from algorithm trading.

# Investment Funds or Proprietary Trading Firms With Large and Frequent Trading Volumes

Investment funds and proprietary trading firms need to execute their investment decisions efficiently and effectively. They face many challenges such as staff costs, management, and most importantly price slippage. An [algorithmic trading system](glossary) will yield similar returns with minimal operating costs.

For example, Dragon Capital needs to sell 50 million HPG stocks and buy 20 million FPT in the Vietnamese market. This task may require several weeks for a trading team to complete. With an algorithmic trading system, a fund manager only needs to input the desired outcome and the system will handle the rest, while providing real-time updates. Moreover, an automated trading system can work on more than 100 stocks simultaneously, which is impossible for human traders.

# Index ETFs

Index ETFs follow mathematical formulas to adjust their portfolios constantly to ensure their performance follows the tracking index. This task can be done daily by an algorithmic trading system in the whole market. It can calculate the buy/sell volumes and prices to place orders and generate reports.

# Professional Investors With Established Investment Methods

Professional investors have developed their own investment methods. These methods can bring profits to their clients or themselves. They can automate their decision-making and trading processes by using an algorithmic system. The main difference between professional investors and new investors is that they have a stable investment formula that can be programmed, thus leveraging the power of algorithmic trading.

At ALGOTRADE, we use algorithmic trading to rebalance our portfolio by scanning the financial statements of more than 1,600 listed companies. The process usually takes several hours.

# Mathematical or Risk Management Experts**  
**

Math and risk management experts may already have profitable investment strategies. However, they cannot execute them manually. Some examples that involve math are scalping or [pair trading](glossary). These algorithms require continuous order placement and cancellation, which can only be done via an algorithmic trading system.

At ALGOTRADE, we use our algorithmic trading system to trade thousands of futures contracts every day with optimal capital allocation.

# Algorithmic Trading Systems Are Not for Everyone

New investors without a clear and sustainable investment method may be disappointed by the actual results of an algorithmic system when trying to automate their investment through technical analysis models or indicators. They may be looking for the holy grail to get rich every day but they likely overlook the flaws in [backtesting](glossary) or the costs involved in real trading. These investors should start small and gradually improve their skills. Poor trading performance often comes from unreliable backtesting results or inaccurate cost estimation.

---


## 55. How to Become an Algorithmic Trader

*Fonte: https://hub.algotrade.vn/knowledge-hub/how-to-become-an-algorithmic-trader/*

If you want to grow your career as a professional [algorithmic trader](glossary), let’s explore the essentials below.

**1\. In-Depth Financial Knowledge**

You’ll need in-depth knowledge of the financial markets as well as an understanding of legal structures, taxes, and applicable fees. It will be challenging to just rely on volume and price data without knowing anything about the market. Algorithmic trading requires lots of effort to customize the system according to your needs. Algorithmic trading is more suitable for those who already can make consistent profits with traditional methods.

Estimated percentage of traders with in-depth financial knowledge: 5%.

**2\. Software Development Skills**

You need to have data skills, such as data collection, data cleaning, and data management. Furthermore, system [optimization](glossary) and server management with high programming skills are critical to building an [algorithmic trading system](glossary). The more developed the market is, the easier it is to accomplish this.

Note that the system development skills require building an entire system from scratch without third-party software like AmiBroker, MetaTrader, or TradingView.

Estimated percentage of traders with technical backgrounds among the remaining traders: 3%.

**3\. Motivation**

Being a software engineer with in-depth financial knowledge is necessary but may be insufficient. You’ll need personal motivation to start and realize the project. There will be distractions like family, health, time, or other life interests.

Estimated percentage of traders with motivation among the remaining traders: 25%.

**4\. Investment Capital**

Investment capital is required to start an algorithmic trading career. Without initial capital, algorithmic traders may not earn enough to cover living costs. In Vietnam, the estimated minimum capital is 3.75 billion VND (around US$160,000) while it would be US$700,000 in the US.

Assume the expected return in Vietnam from algorithmic trading is 15% per annum. The basic living cost is 25 million VND a month, or 300 million VND a year, with an estimated inflation of 7%. The minimum starting capital is:

0.3 ÷ (15% - 7%) = 3.75 billion VND

A similar calculation applies to the US with the following estimates: inflation at 2%, expected return at 12%, and basic living cost at US$70,000. The minimal starting capital is then:

70.000 ÷ (12% - 2%) = US$700.000

These numbers are not a significant investment, but for an individual, they are not small either.

Estimated percentage of traders with sufficient investment capital among the remaining traders: 10%.

**5\. Long-Term Profit**

An algorithmic trader needs to make profits in the long run, not just in the short term. Many algorithms do lose their edge over time and need to be adjusted or replaced. Thus, algorithmic traders need to keep researching and developing new algorithms.

Estimated percentage of traders with sufficient long-term profits among the remaining traders: 35%.

**6\. No Stability Required**

Investors need to be comfortable with uncertainty and randomness. It’s challenging to predict the profits in just a month. Without the right mindset, investors may not have enough patience during difficult times. Not everyone with the right tools is ready to become an algorithmic trader.

Estimated percentage of traders with the right mindset among the remaining traders: 50%.

**7\. Choosing Algorithmic Trading as a Career**

This criterion is quite tricky. Investors may have all skills and qualities to be algorithmic traders, but they may have many other opportunities from large corporations. Will they pick algorithmic trading if they have other career options? Some will, and some won’t.

Estimated percentage of traders who would stick to algorithmic trading: 20%.

**Estimated Number of Algorithmic Traders in Vietnam**

Let’s make a rough estimate of how many algorithmic traders there are in Vietnam. Assume there are 2.5 million individual traders, which is roughly half of the 4.93 million brokerage accounts in Vietnam as of August 2022:

2.500.000 × 5% × 3% × 25% × 10% × 35% × 50% × 20% ≈ 3

Our estimate is that there are only 03 professional individual algorithmic traders in Vietnam or one algorithmic trader for every one million individual traders in Vietnam.

Worldwide, with a population of 7.75 billion, let’s assume 5% trades in the financial markets, which results in 387.5 million individuals. There would be around 387 algorithm traders globally.

Therefore, it can be seen that if one wants to pursue a career in algorithmic trading, it’s important to combine the professional skills of many excellent individuals.

---


## 56. How to Learn Programming Skills for Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/how-to-learn-programming-skills-to-do-algorithmic-trading/*

Many wonder how to learn coding or a programming language. This article will provide directions and give resources to help you learn programming.

# Which Programming Language to Learn

The key question is not what programming language you should learn but how to learn to code. The most important factor in learning is the programming mindset. It takes time to develop the right mindset; however, some languages will help you train better than others.

In our experience, Python is the easiest language for beginners to learn and practice because it’s most similar to natural language. Some other programming concepts and techniques may be better expressed in other languages like C or C++. Many university programming courses still start with C and C++ for introductory classes. A famous example is the CS50 course from Harvard University.

If you have a class of choice, it’s best to follow the programming language taught in the class.

# Where to Learn Programming

There are many ways to learn programming such as in computer science majors during college, or vocational schools. Or you can also take short courses at IT centers. There are also online courses and other materials for self-study. These options will be presented more in-depth below.

**Study at formal colleges or after-school centers.** These are face-to-face, offline learning. If possible, formal education at a university or vocational school is a great option. However, it’s also the most expensive in terms of time and money. This option may not be suitable for those who have worked or studied a different discipline. Short-term courses (from 3 to 6 months), mostly outside working hours, are another option for working professionals. Offline classes help learners interact directly with instructors and shorten the learning time compared to self-study. These formal courses also make it easy for learners to engage in a community of fellow learners for lifelong connections. In summary, offline classes should be taken seriously if possible.

**Online courses and online materials.** Beginners can head to online platforms that help learn to code directly in the web browser like Codecademy and CodeSchool; online learning communities and online course marketplaces such as Skillshare and Udemy. There are also formal online courses such as Coursera, edX, and Udacity. Each has different pros and cons for learning how to program.

_Online platform to program directly in the browser._ There are many platforms like this but two stand out: Codecademy and CodeSchool. Both offer a wide range of courses for all levels from beginner to advanced in different programming languages such as Python and Java.

The advantage of these platforms is that learners can try and practice programming right in the web browser, without having to install and configure any programming language and supporting tools on a computer. This makes it easier for beginners to start programming. However, this option does not help learners understand how a programming language actually works in a computer system. When they need to develop a program that can run on a real system, they will need to learn the software development process and the computer system.

_Online course marketplace and online learning communities._ Udemy and Skillshare are two great examples of this type. Learners can find many courses related to programming, such as Python, Java, etc. These courses are created by independent content creators. The variety will help learners have more options to find suitable approaches and content for themselves. However, most of these classes are not free, and learners may have difficulty choosing the right courses due to the variety.

_Formal online courses._ These are the first major open online course platforms (MOOCs –Massive Open Online Courses), launched in 2011 and 2012 by professors from Stanford University (Coursera, Udacity), Harvard University, and MIT (edX).

These platforms offer courses from mainstream programs of top universities around the world. These courses can be an alternative to traditional face-to-face classes at university. These platforms have gradually structured their programs to be more relevant to online students.

For example, a course that initially lasts a few months (typically 3 to 4 months) is now broken down into several 1-month courses. So learners can keep up with the pace more easily. This is the closest option to traditional offline university courses. Learners can expect to learn programming from scratch in different programming languages. However, for those who don’t like the traditional way of learning, it can be difficult and sometimes boring to follow these courses.

In general, whether it’s an online or face-to-face class, learners need to carefully consider their needs and efforts (in terms of time and money) to choose a suitable option. A clear goal, like being able to write a simple Python program in 6 months while working full-time, would be helpful to motivate learners on the path ahead.

# What if You Don’t Have Enough Time and Money to Learn Programming but Still Want to Pursue Algorithmic Trading?

This is also the key question ALGOTRADE founders have when starting the company. Our short-term goal is to make tools so that traders don’t need to know how to program to still start their journey with algorithmic trading. We are working hard to bring this tool to customers in the near future. We’ll keep you updated!

---


# XI. INTEL CENTER – SUPPORT CHANNEL


## 57. Intel Center Overview

*Fonte: https://hub.algotrade.vn/knowledge-hub/intel-center-overview/*

Data plays an important role for algorithmic trading. It helps develop ideas and test algorithm hypotheses. At ALGOTRADE, we build Intel Center that collects and analyzes data that can improve algorithmic trading performance.

Our first version targets the derivatives market, which attracts over 95% of algorithmic traders. The derivatives market is based on the VN30 index. Our Intel Center provides relevant information on the VN30 stocks, the VN30F futures contracts, and other factors that may benefit the trader’s investment. ALGOTRADE focuses on providing exclusive information that’s not publicly available to give investors a competitive edge.

Intel Center has two main sections, raw data and processed advanced data.

# Raw Data

  * _Live board:_ the live board includes VN30-Index stocks and VN30F futures contracts with basic information such as current price, volume, bid/ask prices, and bid/ask volumes.

  * _Real-time prices of major global market indices:_ They include the US 500 Cash, Nikkei 225, Shanghai, Hang Seng, KOSPI, FTSE 100 Futures, DAX Futures, and CAC 40 Futures.


# Processed Advanced Data

Our live board tracks the trading activities of foreign investors on VN30 stocks to identify market trends. It includes cumulative trading value together with historical data. Foreign investors’ activities on VN30 are expected to be more informative for the derivatives market than foreign investors’ activities on VN-Index.

Our Intel Center tracks foreign investors’ activities through their real-time holdings of futures contracts. The number of contracts is categorized into 4 types of contracts available in the Vietnamese market. Based on this information and historical comparison, it’s possible to estimate the level of optimism and pessimism of investors in the Vietnamese stock market in the medium term.

In future versions, Intel Center will add more features to support traders, such as:

  * _VN30-VIX:_ an index to measure volatility from VN30.

  * _Foreign Activity Tracker:_ a detailed tracking tool for foreign investors’ ownership in stocks.


In the long term, ALGOTRADE can provide data API to algorithmic traders to access and use this specialized data for their decision making and many other features.

---


## 58. Foreign Trading Data

*Fonte: https://hub.algotrade.vn/knowledge-hub/foreign-trading-data/*

# Foreign Investors

Foreign group is someone who registers an account and trades on the Vietnamese stock market. Foreign investors can be individuals, organizations, or foreign investment funds, such as Vinacapital VietNam(VOF), VietNam Holding Limited, and VietNam Equity Fund.

The stock exchange in Vietnam publishes and shares information about foreign investors to all other investors.

Here are key reasons why investors should pay attention to foreign trading data on stocks, especially in the VN30-Index.

  * _Stable cash flow._ Foreign investors include ETFs or investment funds from China, Taiwan, Korea, Europe, and America. They usually have large and slow-moving cash flows, which tend to last for a brief period of time. Knowing the net buying or selling trends of foreign investors can help traders limit their risk and increase the expected profit.

  * _Large cash flow._ The amount of money that ETFs and funds invest in Vietnam is still small. However, it’s still significant compared to the size of the Vietnamese market.

  * _Professional cash flow._ The Vietnamese market has many technical barriers and is not fully open to the majority of foreign investors. Only a very few professional investors or investment funds can access it. Therefore, their trading behaviors reflect the expectations from a special group of professionals.

  * _Long-term cash flow._ Foreign investors usually buy and hold stocks rather than trading them in a short-term of within a few day. Foreign transactions typically move the market’s valuation into new equilibrium. Even though they have a small share in terms of trading volume, if we consider the long-term investment and ignore short-term transactions, the trading value of foreign investors has a significant impact on the Vietnamese stock market.

  * _VN30 is the underlying asset of the futures contact._ The basis (the gap between VN30F and VN30) varies over time, but it needs to converge to 0 on expiration days. Foreign trading data on large-cap stocks of VN30 will thus directly influence the derivatives market.

  * _Simulated cash flow._ Some local investors collect foreign trading data to make investment decisions. They mostly hold similar positions to foreign investors. That means when they see a sudden large net trading volume from foreign investors, they will likely follow suit and amplify the impact of foreign investors.


Intel Center provides 2 specialized charts (Figure 25 and Figure 26) related to foreign trading data, focusing on stocks in the VN30-Index and VN30F futures contracts.

# Position Accumulation of VN30F From Foreign Investors

Figure 25 below shows the cumulative chart of foreign investors in VN30F and the daily number of contracts they buy and sell.

For example, as of Sep 9, 2022, foreign investors have a total of 14.512 long positions, including 8,465 VN30F1M contracts, 5,494 VN30F2M contracts, 447 VN30F1Q contracts, and 106 VN30F2Q contracts.

This index can help predict the future investment directions of foreign investors because they can buy derivatives contracts first and buy stocks later to limit price slippage. In the example above, foreign investors hold 14,512 long positions of VN30F at 950 points, equivalent to a future contract at 95 million VND. Assume that 70% of these contracts are to hedge the opening price of the underlying securities position. We can estimate foreign investors will be net buyers in the Vietnamese stock market:

70% x 14.512 x 95.000.000 = 965 billion VND

This estimate gives investors more information to invest in the market.

# Trading Value of VN30 Stocks From Foreign Investors

Statistics on foreign transactions is based on the net transaction value in the whole Vietnamese market. However, for traders in the derivatives market, the trading value specifically on VN30 stocks is more meaningful than on VN-Index.

ALGOTRADE created the chart “trading value of VN30 stocks from foreign investors” (Figure 26) to provide real-time foreign transaction data on VN30.

This chart can provide future predictive value since foreign investors are usually stable in the long run. For example, when foreign investors switch from net selling to strong net buying as in the period from November 1, 2022, to November 18, 2022, local investors can expect the trend to continue for many months if market prices stay stable.

# Top Stock Changes in Foreign Ownership

Rank 5 stocks that are bought and sold the most by foreign investors compared to the foreign ownership room for each. The formula for calculating the change rate is:

(Buy amount – Sell amount)/(Foreign ownership room х Total number of shares)

The result is a relative value that shows how foreign investors decide for each stock or company. Traders can use these data to determine the net trading trend of foreign investors.

Top stocks with foreign ownership change will be most valuable when looking at a week (5 trading days) or a month (20 days). When looking at a longer term, or much shorter term (like within a day), it’s only a reference and does not offer as much information value.

---


## 59. Daily Accumulative Foreign Trading Value in VN30

*Fonte: https://hub.algotrade.vn/knowledge-hub/daily-accumulative-foreign-trading-in-vn30/*

Daily trading value of foreign investors on VN30 can be a key factor in determining investment direction of the derivatives market and the underlying stock market, both in short and medium terms. It’s especially important for intraday trading strategies. Below is a reference guide to make use of this value in forecasting market trends.

# Important Thresholds

The thresholds in the table below are collected at the end of a trading day. During trading days, it’s possible to estimate the end-of-day value based on simple predictive models.

In the long run, investors can refer to the following percentage thresholds.

# Exclude Put-through Orders

Put-through transactions do not occur through order matching. Their public prices often have no real value, so they don’t directly affect market expectations. Currently, in Vietnam, put-through orders are used to transfer assets among legal entities for various purposes outside of trading. The data on put-through orders is noisy and should be excluded to ensure data accuracy.

# Combine Cumulative Charts of Foreign Investors’ Futures Contracts

The accumulation of futures contracts from foreign investors is a strong trend [indicator](glossary) because they tend to trade futures contracts before executing stock orders to stabilize the trading price. Thus it’s possible to combine the net trading value and the cumulative charts of foreign investors’ futures contracts for trading. The table below is a simple example.

In a more complex forecast, it’s possible to convert the net trading value into the number of futures contracts to estimate the future cash flow of foreign investors.

For example, foreign investors have a net buy volume of 200 billion VND in the market. Assume VN30 is at 1000 points, which means each future contract is priced at 100 million VND. The net buy volume is equivalent to 2000 futures contracts. On the derivatives market, if foreign investors sell 500 futures contracts, then their total trading value is still positive at 1500 futures contracts. It can still be seen as a positive sign from foreign investors to the stock market.

---


# XII. ALGOTRADE LAB – FIRST STEP TO ALGORITHMIC TRADING


## 60. Algotrade Lab Overview

*Fonte: https://hub.algotrade.vn/knowledge-hub/algotrade-lab-overview/*

Building an automated [algorithmic trading system](glossary) for the Vietnamese market in Python or C is challenging. Even with a strong background, it can take up to six months for an average [algorithmic trader](glossary) to build them through APIs.

To bring algorithmic trading closer to investors, we develop ALGOTRADE LAB, a free service that lets you experience algorithmic trading right away even when you don’t know how to program. You can connect your personal securities accounts to our system and set up your own trading preferences. The system will handle the rest automatically, and you can intervene or stop it at any time.

With ALGOTRADE LAB, investors can acquire the following experience:

  * _Automatic trading._ After successfully setting up API connections, the system will execute your orders based on your setting automatically, unless you opt to intervene or stop the system.

  * _Continuous data processing by ticks._ The system will adjust your orders according to every price change in the market.

  * _Super fast order execution._ The system will place your orders much faster than traditional trading methods. In some cases, you can see the price appears in the system before it appears in the market. The system can sometimes order at prices not yet available in the market.


# Important Notes

  * _The service uses SSI securities JSC’s API._ Currently, there are only a few securities companies that provide public APIs for their clients. ALGOTRADE chooses SSI’s API because it’s easily accessible to the majority of investors.

  * _Investors need to establish API connections._ ALGOTRADE LAB is a tool to support investors to perform transactions on their own accounts through API. Investors set up trading parameters: based on their requirements/wishes. To ensure safety, investors should only deposit sufficient money in the account to open up to 01 futures contract.

  * _The algorithm is not expected to make profits._ The lab uses the SMA algorithm, detailed in article 61. It’s simple and accessible and the goal is to help investors have a detailed view of the operation of an automated [trading algorithm](glossary). Note that SMA isn’t guaranteed to make profits. In fact, over the long term, this algorithm on average tends to incur losses.

  * _Profits or losses solely belong to investors._ During the lab experience, there will be lucky investors who make profits and vice versa. ALGOTRADE LAB hopes that investors will see this result as a result of luck, not the result of the algorithm.

  * _Any asset changes in securities accounts are within the scope of investors’ rights and responsibilities._ ALGOTRADE will not have any responsibility and liabilities related to investors’ profits or losses.

  * _ALGOTRADE LAB uses Python programming language._ We choose Python programming language to provide the algorithmic trading experience for investors. The source code is publicly available. Investors will see detailed information processing with each price tick.

  * _The service is completely free._ ALGOTRADE LAB service is completely free, without any benefits from related parties, including SSI Securities JSC.


# Why You Should Try Algorithmic Trading Now

In algorithmic trading, real experience is highly valuable compared to just a theoretical approach. In developed countries, only professional traders or professionals working at investment banks and investment funds have the ability to gain experience in the field. Therefore, this is a good opportunity for investors to gain experience in algorithmic trading. Moreover, investors can adjust algorithm parameters to suit investment preferences. This experience is hard to find in trading software like AmiBroker, MetaTrader, or TradingView.

For investors interested in algorithmic trading, the ALGOTRADE LAB experience will help them find new directions to create their own technical analysis and automated trading systems. They no longer have to rely on third-party software.

For other investors, the experience will help investors understand the market in the near future. When trading on the Vietnamese stock market, they will anticipate how most transactions take place, thereby developing a strategy most suitable for their investment preference.

---


## 61. Introduction to SMA Algorithm

*Fonte: https://hub.algotrade.vn/knowledge-hub/introduction-to-sma-algorithm/*

# Definition of SMA

The moving average (MA) is one of the classic tools used by technical analysts. Simple moving average (SMA) is the most common form of MA, defined as follows:

  * Collect past price points data: Pt-N+1 ...,Pt-3,Pt-2,Pt-1,Pt;

  * Select the number of price points (N) to be averaged;

  * Calculate the average of the last N price points:


SMA(N)t = (Pt \+ P(t-1) \+ P(t-2) \+ ... + P(t-N+1)) ÷ N

# SMA Algorithm

**Hypothesis.** When the price starts to rise again after a downtrend, the price line crossing over the SMA signals an uptrend that is expected to continue in the short term. Conversely, when the price starts to fall after an uptrend, a drop below the SMA signals the beginning of a downtrend.

# Strategy Group

****

**Market.** Derivatives market – futures contracts VN30F1M.

**When to Open Positions**

  * Independent variable: VN30F1M price by ticks.

  * Dependent variable:


SMA(N)t = (Pt \+ P(t-1) \+ P(t-2) \+ ... + P(t-N+1)) ÷ N

where Pt is the current price of VN30F1M, Pt-1 is the previous tick price.

  * Parameter: the number of tick price points (N) to calculate the average, default = 2000.

  * Place a limit order (LO) to buy at the ceiling price or sell at the floor price as soon as there’s a signal to open a position.


If Pt-1 < SMA(N)t-1 and Pt ≥ SMA(N)t then open a buy position;

If Pt-1 > SMA(N)t-1 and Pt ≤ SMA(N)t then open a sell position.

  * Only trade 01 contract maximum for each position. Limit 03 positions maximum per day (03 transactions to open positions and 03 transactions to close positions).


**When to Close Positions**

  * Place orders to sell at the floor price or buy at the ceiling price as soon as the target is reached.


Take-profit point = Position opening price + Expected profit

  * If Pt ≤ (Price to open the position - Stop loss) then place an order to buy at the ceiling price or sell at the floor price to close the position (stop loss). The stop loss threshold can be adjusted.

  * No positions remain overnight. At the ATC sessions, if the account still has an open position, then close the position with an ATC order.


**Results**

  * Expected profit: N/A;

  * Maximum drawdown (MDD): N/A.


**Note**

  * The SMA algorithm works well when the market has a clear trend.

  * SMA algorithm is a popular and simple algorithm in technical analysis, designed to illustrate the concept of _“trading algorithm”_ and test the automated system. Therefore, investors should note that this algorithm does not guarantee profits.

---


## 62. How to Register for API at SSI Securities JSC

*Fonte: https://hub.algotrade.vn/knowledge-hub/how-to-register-for-api-at-ssi-securities-jsc/*

Currently SSI Securities Joint Stock Company provides Fast Connect API service to customers with the following details (updated March 31, 2023):

# How to Sign Up for Fast Connect API

Contact the branch office of SSI Securities JSC to register and subscribe to the service.

# How to Create a Connection Key

Visit [iboard.ssi.com.vn](http://www.iboard.ssi.com.vn/) > Support > API services > Click on the “key” icon to generate a connection key > Select “Generate new connection key” > Click “Continue” > Enter OTP verification code > Click “Confirm”

After completing the steps above, the system will generate the key to save and start using the service.

At this point, you will have access to the API tool to start a new journey as an algorithmic trader and experience automated trading at ALGOTRADE LAB.

---


## 63. Experience Algotrade Lab

*Fonte: https://hub.algotrade.vn/knowledge-hub/experience-algotrade-lab/*

After opening an account at SSI for the derivatives market, registering for the API service, investors can experience algorithmic trading at ALGOTRADE LAB with a minimum deposit to open 01 futures contract in their account. The high-level steps are as follows:

Open an account > Sign in > Set up API connection > Algorithmic parameter configuration > Algorithm launch > Algorithm monitoring

# Open an Account and Sign In

Submit your account details at [www.algotrade.vn/lab](http://www.algotrade.vn/lab) > Receive account information by email > Access [www.lab.algotrade.vn](http://www.lab.algotrade.vn/) and login to get started.

The directory structure of the algorithm includes:

  * _config.ipynb:_ to configure the API and configure the parameters of the SMA algorithm;

  * _data.ipynb:_ to store tick values of VN30F1M futures contract and compute SMA(t);

  * _db.ipynb:_ a simple database to store order status, net profit/loss, etc.

  * _main.ipynb:_ implement the algorithm and review execution log in real-time;

  * _logs.log:_ contains the SMA value and all order information the algorithm has traded (only to check algorithm accuracy).


# Set Up Api Connections

At the main interface of ALGOTRADE LAB, open file “config.ipynb” > Enter the required information/desired information in the following lines: CONSUMER_ID, CONSUMER_SECRET, PRIVATE_KEY, ACCOUNT, OTP**.**

# Algorithm Parameter Configuration

Under the API connection key input, investors can adjust the algorithm parameters to their wishes. The following parameters can be changed:

  * CUT_LOSS_THRESHOLD: stop loss parameter. When reaching this threshold, the system will automatically close all open positions with market orders. The stop loss value will be derived from the current price and the actual open price, not the theoretical price. The default parameter is -3.

  * TAKE_PROFIT_THRESHOLD: take-profit parameter. The default parameter is 3. The system will automatically take profits when reaching this threshold.

  * MAX_ROUND: the number of times the algorithm can activate. One activation means one open position and one close position. The default parameter is 3, so there are 6 transactions in total. This is to ensure the investor’s experience without excessive trading per day.

  * START_TRADING_TIME: the algorithm start time. Investors can set any time during trading hours from 09:00:00 to 14:30:00. The default is 09:00:00.


After adjusting the configuration, click save (Ctrl + S or Command + S) to update the changes to the system. Here’s an example illustrating an investor who has completed the API connection and parameter configuration:

# Algorithm Launch

After connecting the API and configuring algorithm parameters at the main.ipynb file, select ”Kernel” > click “Restart Kernel and Run All Cells” to start the algorithm.

# Algorithm Monitoring

At the ALGOTRADE LAB interface, open “main.ipynb” to observe two key parts:

  * _“SSI Algorithm Demo”:_ shows the code of the SMA algorithm.


  * _“If you want to show log realtime …”:_ located under “SSI Algorithm Demo”, it displays real-time trading algorithm status updates.


After initializing the algorithm, the prompt _“If you want to show log realtime …”_ will continuously show updated information.

# Stop the Algorithm

In the file main.ipynb, click “Kernel” > “Shut Down Kernel” to stop the algorithm. The status line “KeyboardInterrupt” will display when the algorithm stops successfully.

# 

# **Adjusting Algorithm Parameters During Operations**

If you want to change the algorithm parameters when the system is running, you can do the following:

Open “config.ipynb” > Re-enter new parameters to be changed > Click save (Ctrl + S or Command + S) > In the main interface, click ”Kernel” > click “Restart Kernel and Run All Cells” to restart the algorithm.

Note it’s not necessary to stop the algorithm when changing its parameters.

# Source Code

The following is a detailed explanation of the main source code snippets.

Import necessary libraries to run the algorithm, including the internal ALGOTRADE library.

Process position data from SSI, update the opened positions as well as the total profit/loss when the positions are closed. Then update the status of OPEN_POSITION to the initial state (None) to be able to open new positions if the algorithm spots new signals.

Initialize pub/sub redis to receive processed tick data as well as order status placed by the algorithm.

This is the function to open a new position with key information: ACCOUNT is the user account; F1 is the futures contract VN30F1M; side is ‘BUY’ or ‘SELL’; and price is the price to place orders.

This is the main part of the algorithm. After receiving one new tick, the system will compute SMA(N)(t) và SMA(N)(t-1)and check the condition:

  * If Price(t-1) < SMA(N)(t-1) and Price(t) >= SMA(N)(t) then the system will a new long position

  * If Price(t-1) > SMA(N)(t-1)and Price(t)  <= SMA(N)(t) then the system will open a new short position


If the unrealized profit/loss (for the opened position) exceeds the profit/loss thresholds defined in the file "config.ipynb", then an opposite position will be opened to take profits or stop loss with a limit order at the ceiling or floor price.

At 14:29:50, if the position is still open then the system will open an opposite position to close it at ATC.

---


## 64. SMA Algorithm Configuration and Monitoring Experience

*Fonte: https://hub.algotrade.vn/knowledge-hub/configuration-experience-and-sma-algorithm-monitoring/*

# Parameter Recommendations

The SMA algorithm is used to test the algorithmic trading system, not to seek profit. The fact has shown that, in the long run, this algorithm tends to make losses. To avoid big losses during the first algorithmic trading experience, it’s recommended to set a cut-loss threshold as follows:

  * If you choose a stop-loss at CUT_LOSS_THRESHOLD = -x 

  * Then the take profit threshold should be  
TAKE_PROFIT_THRESHOLD = x + Compensation for taxes, fees, & slippage.


The compensation for taxes, fees, and slippage is added to take sufficient profit to cover the trading expenses.

For example, if you choose CUT_LOSS_THRESHOLD to -3 points; the taxes, fees, and slippage is approximately 1 point; then TAKE_PROFIT_THRESHOLD should be 4 points.

Note, the added compensation value should not be too large; since it’s more likely the position will reach stop-loss threshold before having a chance to take any profit.

For MAX_ROUND (the maximum number of open positions), it’s recommended to set the max value to 3 to get a feeling of the algorithm. When the algorithm opens a buy position and makes a profit, the next new position will be a sell position (the opposite to the previous one). In contrast, if it realizes a loss, the next new position will be a buy position (the same position to the previous one).

For START_TRADING_TIME, it’s a simple but important parameter. The algorithm is most effective during periods of markets with clear and continuous up trends or down trends. Therefore, the right start time will greatly contribute to trading performance. For example, suppose investors observe that between 10:00:00 and 11:00:00, the market mostly maintains sideways trends. Then they can choose to activate the algorithm outside of this period to increase the profit likelihood.

# Trading System Monitoring

During the system’s operation, investors can see the status updates continuously. For the best experience, investors can open the ALGOTRADE LAB interface together with SSI’s live board interface to monitor and compare information.

Upon a successful start, stock price and SMA algorithm information will be updated in real time:

LAST_PX(t) is the current price of VN30F1M and LAST_PX(t-1) is the previous one. The corresponding SMAs are SMA(t) and SMA(t-1).

When reaching the signal to open a position, the trading order is sent and the system updates the status line:

In this example, LAST_PX(t) is lower than SMA(t) and is trending up; when LAST_PX(t)) exceeds SMA(t), the system automatically sends a buy order.

The system continuously updates the profit/loss status when opening a position:

Unrealized Profit/Loss = 0.1 means the current profit is at 0.1 point, equivalent to 10,000 VND profit in a securities account.

When the position reaches the stop-loss threshold, the system will show the following status upon automatically closing the position:

Similarly when the position reaches the take-profit threshold and gets closed, the system will show the following status:

To avoid technical errors, do not manually trade while the algorithmic trading system is operating.

However, the system can encounter unexpected bugs and are unable to close positions, despite reaching the take-profit or stop-loss threshold. In this case, it’s important to stop the system and place a manual order to close the positions to avoid unexpected consequences.

---


# OTHER ARTICLES


## Sortino Ratio

*Fonte: https://hub.algotrade.vn/knowledge-hub/sortino-ratio/*

Many traders and investment managers require a means to measure and evaluate portfolio managers and trading systems. Risk-adjusted metrics play a pivotal role in this evaluation. It’s because more returns can always be achieved from taking more risks, inherent in the leverage nature of the futures markets. While Sharpe ratio is the most widely used risk-adjusted measure since its introduction in 1966, Sortino ratio offers an alternative perspective and improves Sharpe ratio in specific aspects.

Sortino ratio, developed by Frank A. Sortino in the 1980s, is a risk-adjusted performance measure of a portfolio. It’s similar to Sharpe Ratio, which was named after William Sharpe. The key difference is that the Sortino ratio differentiates harmful volatility from overall volatility. It can be viewed as a modification of Sharpe Ratio, but it only considers the standard deviation of the downside risk, rather than that of the entire upside plus downside risks.

# Formula and Calculation

Sortino ratio penalizes those returns failing a specific target, or minimum acceptable return. On the other hand, Sharpe ratio penalizes any upside or downside difference. The formula and calculation of Sortino is as follows:

where:

  * Rp is the actual portfolio return,

  * T is the target return or the minimum acceptable return, and

  * DR is the downside risk.


The downside risk from a data sample over N periods is calculated as follows:

where Ri is the portfolio return in time period i and T is the minimum acceptable return.

In post-modern portfolio theory, another way to view the downside risk is the square-root of the probability-weighted squared below-target return:

where r is the random variable representing the return and f(r) is its probability function.

Both forms have their values in practice. Some practitioners use the discrete calculation due to its simplicity, while others use the continuous form in post-modern portfolio theory.

It’s interesting to note that in 1959, Nobel laureate Harry Markowitz recognized that investors primarily care about downside deviation when developing Modern Portfolio Theory. Hence using the downside deviation would be more appropriate than using the standard deviation. However, Markowitz used variance (the square of deviation) in his Modern Portfolio Theory since downside deviation was computationally impractical at the time.

# **Key Features**

Sharpe ratio penalizes both upside and downside deviation, which means one can achieve higher Sharpe ratio by removing the largest positive return. This is undesirable as investors certainly welcome large positive returns. Additionally, for a positively-skewed investment strategy (e.g. trend following), the performance is often achieved with lower risk than Sharpe ratio suggests. Indeed, for a skewed/non-normal distribution of returns, Sharpe ratio often falls short and becomes a poor performance measure.

The Sortino ratio focuses only on the negative deviation from the minimum acceptable return, which is thought to give a better view of risk-adjusted performance since positive deviation is indeed a benefit. It is also a useful way for investors, analysts, and portfolio managers to evaluate a portfolio for a given level of bad risk.

Similar to Sharpe ratio, a higher Sortino ratio is better. When looking at two portfolios, a rational investor would prefer the one with a higher Sortino ratio as it yields higher return per every unit of bad risk. The following table shows the recommended range:

# **Example**

In this example, we will calculate the annual Sortino ratio for the following set of annual returns:

  * Annual returns: 19%, 12%, 23%, -5%, 15%, 6%, 13%, -4%,

  * Target return: 7%.


We calculate the excess return and the downside difference with the min function:

The numerator in Sortino ratio is the average of excess return:

The denominator DR in Sortino ratio is calculated as follows:

The Sortino ratio is then:

# **Conclusion**

The Sortino ratio provides a more nuanced view of risk compared to other risk-adjusted performance measures. By focusing on downside risk, it offers valuable insights for investors to optimize their portfolios against potential losses. As with any financial metrics, it’s better to use Sortino ratio in conjunction with other measures and not in isolation.

---


## Information Ratio

*Fonte: https://hub.algotrade.vn/knowledge-hub/information-ratio/*

In 2023, VNINDEX rallied 12.2%. As a smart beta strategy on the equity market, achieving a return below this benchmark should be considered a failure. It’s because it falls short of the passive investing strategy. Surprisingly, under Sharpe ratio, an algorithm trader with 2023’s performance of only 9% may still find that their strategy remains successful as this metric remains sufficiently positive.

This apparent contradiction suggests that the Sharpe ratio becomes less relevant when relative return means more than absolute return. As a result, the Information Ratio was introduced to emphasize the relative return rather than the absolute return.

# Information Ratio

Information Ratio is a performance measure in finance to evaluate the risk-adjusted relative return of an investment portfolio.

It emphasizes the relative return achieved by comparing the excess return (with respect to a benchmark like VN-Index) to the tracking error. The tracking error represents the volatility of the deviation from the benchmark.

The formula:

In which:

RP : Portfolio Return

RB : Benchmark Return

RA : Active Return, the difference between the portfolio return and the benchmark return  
σ(·) is the standard deviation function

A higher IR indicates that the investment has generated better risk-adjusted returns relative to its benchmark. It suggests that the investment strategy or manager has added value beyond what can be explained by market movements alone.

The Information Ratio is often used to evaluate algorithm performance along with its consistency known as tracking error (standard deviation). A low tracking error indicates consistent performance. A high tracking error suggests volatile returns that may not consistently in the long run.

Note that, if the risk-free rate is the benchmark, and there’s no risk associated with the benchmark return, the Information Ratio and Sharpe Ratio should yield the same result. 

# **Sharpe Ratio or Information Ratio in Algorithmic Trading?**

In Algorithmic Trading, certain strategies such as smart beta or uptrend grid (commonly known as the bull market grid), Information Ratio give investors deeper insight on algorithm performance when compared with Sharpe Ratio.

However, in other strategies such as market neutral, price momentum, mean-reversion, event-driven, market-making, scalping, ETF Front-Runner, Arbitrage, Grid and Sniffing, Sharpe Ratio remains a useful metric.

In short, any long bias strategies should use Information Ratio instead of Sharpe Ratio.

The following table summarizes the key differences.

# Additional Usage of Information Ratio

An algorithmic trader can use the recommended IR range below to quickly evaluate the robustness of an algorithm performance.

Lastly, Information Ratio can serve not only as a primary criterion to evaluate long bias strategies but also as an objective function in the optimization phase.

In conclusion, understanding Information Ratio and its applications provides algorithmic traders a practical metric to evaluate algorithm performance, potentially helping to improve investment decisions.

---


## Fundamental Analysis and Technical Analysis

*Fonte: https://hub.algotrade.vn/knowledge-hub/fundamental-analysis-and-technical-analysis/*

Fundamental analysis and technical analysis are two popular methods used in stock investment. They are to evaluate the potential of financial instruments and make investment decisions. However, these two methods have key differences in their approaches and objectives.

# Fundamental Analysis

Fundamental analysis (FA) involves evaluating publicly available information and building pricing models to estimate the intrinsic value of an asset.

In the context of stock investment, fundamental analysis includes a detailed evaluation of a company’s business model, financial conditions, and impacting macroeconomic factors. The main objective is to identify companies with better growth prospects than what the market price reflects. Also, analysts or investment managers create asset pricing models to estimate the intrinsic value. If the current price is significantly lower than the estimated intrinsic value, portfolio managers may consider increasing the allocation to the stock in their investment portfolio.

Fundamental analysis includes part or all of the following process:

  * **Business analysis**


  *     * Determine the business model: understanding how a company generates revenue, profit, and competitive advantages.

    * Analyze financial reports: using financial ratios to evaluate operational efficiency, financial conditions, and potential profit of a company.

    * Analyze business leadership: assessing the experience and capabilities of the business leaders.


  * **Sector and competitor analysis**


  *     * Identify the main competitors: identify companies that have similar products or services and assess their competitiveness.

    * Identify industry trends: identify growth trends, changes in the industry, and their impacts on the company.


  * **Forecasts.** Use financial models and historical data to forecast future revenues, expenses, and cash flows.

  * **Stock valuation.** Use valuation models such as discounted cash flow, dividend discount, price-to-earnings ratio model to determine the intrinsic value of stocks.


# Technical Analysis

Technical analysis (TA) is a method to predict the future price trend of an asset based on its historical data on prices and trading volumes. Technical analysts use various types of charts, graphs, indicators, and patterns to identify potential buying and selling points.

Technical analysis is based on the underlying logic:

  * Supply and demand determine prices.

  * Changes in supply and demand - both in volumes and price levels - can cause price changes.

  * Past action can be used to predict future price trends.


With this logic, this approach can be used for any financial instruments (such as stocks, bonds, commodities, currencies, and futures) as long as it is traded in the free market system. A free market is defined as a system where buyers and sellers engage in voluntary trade without external interference or hindrance. Also prices are set based on the interaction between supply and demand in real time.

In practice, however, technical analysis is mostly effective in highly liquid markets. These markets have a large trading volume, providing ample data for analysis and enhancing prediction accuracy. Additionally, in this environment, small transactions have less impact on prices. This makes technical signals more recognizable, minimizes noise, and increases the reliability of analysis.

The main tools in technical analysis are as follows:

  * **Charts:** These visual representations show price and trading volume data over time. Common chart types include line charts, candlestick charts, and bar charts. They help traders visualize historical price movements and identify patterns like head and shoulders pattern, diamond pattern, cup and handle pattern.

  * **Indicators:** Indicators are technical analysis tools built on math formulas. They use price and volume data on charts to offer investors insights into market trends, momentum, and potential reversal signals. Some popular technical indicators include Relative Strength Index (RSI), Moving Average Convergence Divergence (MACD), and Bollinger Bands.


# **Differences Between Fundamental and Technical Analysis**

Fundamental analysis and technical analysis differ primarily in the data that analysts use. Technical analysts rely on price and trading volume data, which are considered objective because they reflect market transactions. In contrast, fundamental analysts rely on business financial statement data. These are entirely objective because they contain accounting estimates and assumptions during aggregation. Moreover, financial statements are potentially subject to fraud, distorting the analytical significance of the data. For instance, businesses may hide losses and exaggerate profits in their financial reports.

Regardless of the data or strategy, analysts must rely on historical information to make informed judgments and predictions. Both fundamental and technical analyses involve a subjective aspect from the user. Technical analysts interpret price charts and technical indicators. It means they need to be able to recognize patterns and make predictions about future market trends. On the other hand, fundamental analysts assess a business’s financial conditions, growth prospects, and risk factors based on information from financial statements and other sources.

Technical analysis requires less in-depth knowledge of financial instruments compared to fundamental analysis. In stock investing, technical analysis focuses on price charts, trading volumes, and indicators to identify movement trends, support/resistance levels, and buy/sell signals. While they may not research deeply into a company’s business, it’s essential to recognize that market volatility and external factors persist. Therefore, when using technical analysis, understanding the company’s business model, financial conditions, and risk factors remains important for informed investment decisions.

Summary of the key differences between fundamental and technical analysis:

# 

# 

# 

# 

# 

# 

# 

# 

# 

# 

# 

# **Fundamental and Technical Analysis in Algorithmic Trading**

Both fundamental and technical analysis can help algorithmic traders in formulating algorithmic hypotheses. Fundamental analysis guides decisions on which stocks to buy, helping to build stock selection strategies and determine each stock’s weight in the portfolio. On the other hand, technical analysis informs strategies for opening positions, taking profit and stopping losses. These factors are important components in developing a trading algorithm. Algorithmic traders can flexibly use fundamental and/or technical analysis depending on their goals in long-term investment or short-term scalping.

Also, it’s essential to recognize that while a pricing model derived from fundamental or technical analysis may be useful in a specific market, it’s not universally applicable to every market at all times. Regardless of the method used, algorithmic traders should conduct comprehensive testing and optimization to establish a solid scientific foundation and confidence level before applying algorithms to real trading.

With fundamental analysis, it can be a challenge for algorithmic traders to collect and process data. Fundamental analysis mainly uses financial statement data. However, this data often has the following problems:

  * **Data quality:**


  *     * Accuracy: financial statements can be manipulated or erroneous for different reasons.

    * Completeness: some businesses may not disclose sufficient financial information, or even disclose inaccurate information.

    * Comparability: businesses may use different account methods and standards that have changed over different periods, making data comparison more challenging.


  * **Accessibility:**


  *     * Financial data can be published in various formats, making data collection and analysis difficult.

    * Collecting financial data can be expensive, especially for historical data or data from unlisted businesses.

    * Financial statements may not be fully explained, making it difficult to understand and use the data. Financial data analysis requires an algorithmic trader with specialized knowledge of accounting and finance.


Compared to fundamental analysis, technical analysis data is easier to collect and process. However, tick price and volume data still require integrity. In the Vietnamese stock market, integrity can be achieved in the derivatives market but there may still be limitations in the equity market.

In algorithmic trading, the contrasting nature of fundamental and technical analysis lies in their underlying assumptions. For instance, growth in after-tax earnings is usually a good sign. However, whether the stock price rising beyond its peak is a good sign or not is still difficult to explain scientifically. The answer can only rely on statistics and data models. Therefore, algorithmic traders should build a habit of understanding underlying assumptions before forming algorithm trading hypotheses.

---


## Smart Beta Backtesting Procedure

*Fonte: https://hub.algotrade.vn/knowledge-hub/smart-beta-backtesting-procedure/*

Smart Beta has emerged as a highly promising technique in the finance industry. Its scalability and compatibility with other algorithms make it an essential step. This writing aims to standardize the smart beta backtesting process.

In the context of the Vietnam stock market, which differs significantly from the global market, algorithmic traders can follow this process to fully automate the smart beta backtesting process.

## 1\. Data

To enhance efficiency and accuracy, it’s advisable to store data in a database. While many service providers offer algorithmic traders access to such data, it mainly works for visualization and gaining insights into specific criteria. However, it may not be suitable for large-scale market assessments.

Keep in mind there are distinct financial report structures for four different industries, including manufacturing, banking, securities, and insurance. A complete database provides full access to all these reports.

Database design requires flexibility since accounting standards may change over time. Such changes could require adjustments or the inclusion of additional information in the existing data.

## 2\. Data Cleansing

Algorithmic traders often find this stage frustrating because data cleansing efforts in the Vietnamese stock market gives limited value. Despite using top-tier data providers in Vietnam, various errors still persist. Some common roost causes include:

  * Manual input: Manually entering data from files into a database often results in many errors. Algotrade has found many examples where input errors deviate significantly from the original values, sometimes by a factor of ten (adding or removing a zero in the number)

  * Change of law: In 2014, new regulations on reporting standards changed for the industrial sector after 200/2014/TT-BTC took effect Feb 05, 2015. As a result, the reporting format has changed both forward and backward in time. The challenge is in ensuring compatibility between the old and new formats. This change of law may happen to different sectors independently at different times. For instance, debt buying activities, previously not reported in the banking sector, are now part of the standard reporting practice.

  * Future updates: By 2025, many companies in Vietnam will need to adhere to the International Financial Reporting Standard (IFRS). Once again, data structures may undergo modification, requiring algorithmic traders to prepare for this impending change. Subtle yet critical changes may happen, such as listing items like Employee Stock Ownership Plans (ESOP) as expenses.


In the context of the Vietnamese stock market, there are two key recommendations for data cleansing. First, consider a sum check to assess the overall error in the whole market. The sum check function can provide true/false results for each category and its components, as well as the magnitude of the difference. Second, evaluate the cost associated with data cleansing to determine whether it’s worth fixing or ignoring. Sometimes, the data is not very insightful but the effort required for correction is prohibitively high. In these cases, algorithmic traders may opt to use valid data (e.g. category numbers) while disregarding specific components. For instance, they can use operating cash flow as input parameters but ignoring the components of operating cash flow.

## 3\. Single factor backtesting

After handling the database, algorithmic traders might opt for single-factor backtesting first instead of multi-factor backtesting. This allows for clearer assessment of each factor’s contribution. After that, they can combine effective factors together to create a multi-factor backtesting approach.

When considering single factors to backtest, it’s not restricted to standard ratios. Any relevant metric derived from a usable dataset can offer much value. Some common single factors that investors often start with include P/E ratio, P/B ratio, ROE (return on equity), Operating Cash Flow, Profit Margin, and Equity Growth.

Here is a sample backtesting report for receivables turnover ratio: [Link](https://www.algotrade.vn/_files/ugd/5a3731_1ee99307c94c4c85ac5c905439ff5a31.pdf)

## 4\. Multi-factor backtesting

After completing single-factor backtesting, there are three approaches to create multi-factor criteria. The first two are more common. The first is to combine working single factors by merging them together. The second is a centralization method - use critical findings from single-factor backtesting as a pivot while only changing other subfactors. Lastly, algorithmic traders can randomly mix any combination of the factors they choose.

It’s advisable that each multi-factor backtesting should include 3 to 7 factors. Too few factors may lead to a volatile algorithm, while too many can result in a small pool of qualified stocks and model overfitting.

A multi-factor backtesting sample using 3 factors: Operating Cash Flow Growth, Debt Repayment and ROE is as follows: [Here](https://www.algotrade.vn/_files/ugd/5a3731_32f7cae0615c41e48df0d8962e28401e.pdf)

## 5\. Execution phase

Besides finding a combination of factors, algorithmic traders must thoroughly consider several other aspects.

Entry prices may be different from backtesting because real-time entry prices reflect current market prices, whereas during backtesting periods, entry prices are often based on closing prices.

Rebalancing periods significantly impact fees and algorithm stability. Excessive rebalancing can lead to higher fees, while infrequent rebalancing may reduce the algorithm’s effectiveness. The choice of rebalancing period greatly influences overall algorithm performance.

Asset weights is a complex subject, though it should be considered in the latter stage of smart beta strategies. For the initial stage, equal weights are recommended in smart beta backtesting for simplicity.

Execution algorithms also must be employed when traders execute orders for several days in a large account. Recall that TWAP, VWAP and POV are the most common execution algorithms.

# Key Notes

In the real world, besides identifying performance factors, liquidity plays a crucial role. In fact, liquidity is critical. Without accounting for liquidity, any findings may be useless because no transactions can be made.

When configuring backtesting settings, algorithmic traders should distribute data ranges for in-sample backtesting, parameter optimization, and out-of-sample backtesting to validate factors and models.

Algorithmic traders might also consider incorporating technical indicators to improve entry points, especially if they are familiar with technical analysis.

---


## Biases in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/biases-in-algorithmic-trading/*

Investment decisions often appear dry and precise. Investing in the real world, however, is far more nuanced. Classical research studied psychological factors influencing investment decisions, drawing connections between finance and psychology since 1912 in George Selden’s book, “Psychology of the Stock Market”. Decades later, the arrival of Prospect Theory in 1979 by Amos Tversky and Daniel Kahneman and the concept of “mental accounting” by Richard Thaler in 1980 marked the rise of behavioral finance.

In the digital age, algorithmic trading has revolutionized investment strategies. It equips portfolio managers with powerful tools for constructing and executing portfolios. Algorithms provide speed and precision in the stock market. However, they aren’t magic bullets. Biases can still affect their development, data selection, and model interpretation. Portfolio managers, being humans, can still hold biases that seep into the algorithmic decision-making process. These biases can lead to suboptimal outcomes despite advanced computing technology.

This article explores investment biases specific to algorithmic and quantitative trading. We identify two main categories of biases: systematic and behavioral biases. Investors and portfolio managers exhibit systematic biases during system development in the quantitative processes. Conversely, they introduce behavioral biases through ad-hoc decisions influenced by their human behavior. Over time, both types of biases lead to suboptimal performance, which requires careful reviews and updates to quantitative trading systems.

# Systematic Biases

Even with superb algorithmic models, a system can still underperform compared to a benchmark due to suboptimal training data and algorithmic design. Moreover, inadequate data may even lead to catastrophic losses.

**Look-ahead bias.** A simple example is to train an algorithm to predict tomorrow’s weather based on tomorrow’s forecasts. When testing a trading strategy in simulations or backtests, if an algorithm’s trading signal relies on future data that was not available at the time, the results become skewed. This bias occurs when information from the future influences decisions made in the past.

Another example arises in global strategies related to time zones. Failing to account for time zone differences in time-stamped data can lead to events occurring out of order. That is, events in different countries may happen in different order with time zone corrections. Lastly, for strategies relying on sentiment analysis, algorithmic traders should exercise caution when using sentiment dictionaries that may have been trained on forward-looking data.

**Overfitting bias.** This bias occurs when an algorithm becomes too finely tuned to a specific data range. It may perform exceptional on the chosen data set, but may fail to generalize effectively to the broader market. Machine learning researchers can inadvertently introduce mixed bias if they train their hyper-parameters on the entire data sample and then use the same hyper-parameters to backtest.

Another example of overfitting bias arises from skewed straining data. If an algorithm is trained primarily on data from a bull market, a bear market, or a sideway, it may not accurately represent the full market spectrum. Consequently, any resulting trading strategy could prove ineffective in the real market.

To mitigate overfitting, one approach is to use data holdout for validation. This involves withholding a portion of the training data for validation purposes and it can either be time-series holdout or asset holdout.

For time-series holdout, there are two common approaches: withhold a continuous time range, typically towards the end of the time-series data, or withhold several interleaved stretches within the training window. For example, hold out the last 12 months for validation, or hold out periods of every other week within the training data.

For asset holdout, make sure the withheld asset does not introduce further bias, e.g. a specific market capitalization, trading liquidity, industry, or geos. The holdout should have the same broad characteristics as the overall market.

**Design bias.** Designing algorithms can introduce a hidden bias. When we exclusively focus on successful trading strategies, we inadvertently create a system with a blind spot. This narrow perspective can distort our perception of risk and potential returns. If the market conditions that made these strategies successful change, this bias can lead to devastating losses.

The quality of training data used in algorithmic design is critical. If the data fails to represent the entire market, resulting trading strategies may suffer from limitations. Also, a lack of diversity in the training data can hinder an algorithm’s ability to adapt to various market situations and economic structures. For example, a trading algorithm trained during the booming years of the car manufacturing industry might struggle when a different sector becomes the country’s largest.

# Behavioral Biases

While algorithmic trading relies on mathematical models, historical data, and automated execution, it remains fundamentally influenced by human behavior. Even with sophisticated computing systems, algorithmic traders and portfolio managers can exhibit behavioral biases specific to quantitative trading.

**Confirmation bias.** This bias involves seeking information that confirms existing beliefs and trading decisions. Investors may disregard contradictory evidence, leading to skewed perceptions and suboptimal performance.

In the context of algorithmic trading, portfolio managers may make the mistake of selective backtesting their strategies. A portfolio manager might focus on time frames where their strategies are known to perform well, ignoring unfavorable periods. Also managers may dismiss negative news about a stock in the portfolio, assuming such instances are outliers.

**Overconfidence bias.** This bias refers to the tendency of individuals, including portfolio managers, to overestimate their abilities, knowledge, and accuracy. Managers may believe they have more control over market outcomes than they actually do. This illusion of control leads to excessive trading, and unnecessary adjustments to algorithms.

Algorithmic traders may downplay risks associated with their strategies, ignoring any risk management protocols. They might dismiss signals that challenge their existing positions. They may ignore warning signs, assuming their models are foolproof.

**Anchoring bias.** This bias occurs when we overly rely on initial information when making decisions. In the context of algorithmic trading, if a stock was initially priced high, a portfolio manager can anchor their valuation to this information, even if market conditions suggest otherwise.

When designing trading algorithms, anchoring can occur in parameter selection. If an algorithm was initially calibrated with certain thresholds, subsequent adjustments might be biased by these initial settings.

**Hindsight bias.** Individuals tend to perceive past events as being more predictable than they actually were. Algorithmic traders may become overconfident when they believe they can predict market movements after the facts. They may retroactively adjust their strategies based on outcomes, ignoring the uncertainty during real-time decision-making. Furthermore, algorithmic traders may underestimate the risks associated with certain trades, assuming they could have foreseen adverse outcomes. 

**Availability bias.** Portfolio managers may favor easily accessible information. When evaluating algorithms, portfolio managers may unconsciously prioritize outcomes that come to mind quickly, even if these outcomes are not statistically representative.

Algorithmic traders may give importance to recent market events, especially when they are emotionally charged (e.g. from a sudden market crash). These events become more memorable, leading to biased decision-making.

Availability bias also affects the choice of historical data used for training algorithms. Managers may select data aligned with their recent experiences, ignoring equally important but less accessible information. This bias can distort trading strategies. Portfolio managers may overemphasize recent market trends, leading to excessive buying or selling. Algorithms trained on biased data may perpetuate these patterns.

# ****Conclusion

Keep in mind that every algorithm, no matter how advanced, reflects human psychology. Recognize this fact, adapt, and make wise trading decisions. As portfolio managers, the role extends beyond writing code. It involves comprehending both the markets and ourselves.

Financial literacy is crucial. Informed investors who grasp these biases are better equipped to make choices. Also, creating a well-defined investment plan based on risk tolerance and long-term objectives promotes discipline and helps avoid emotionally driven decisions.

By acknowledging these biases and fostering a culture of critical analysis, portfolio managers can leverage algorithmic trading while minimizing its potential drawbacks. Algorithm trading is a tool, and like any tool, its effectiveness depends on understanding its limitations and using it responsibly.

---


## Popular Technical Analysis Indicators

*Fonte: https://hub.algotrade.vn/knowledge-hub/popular-technical-analysis-indicators/*

# Overview

Technical indicators are mathematical calculations used in financial markets to analyze trading data on prices and volumes. The general purpose is to predict price trends, identify potential entry and exit points, and assess trading risks.

Based on their intended purpose, technical indicators are classified into 4 groups: Trend-Following Indicators, Volatility Indicators, Momentum/Oscillators and Volume Indicators.

**Trend-following indicators** assist investors in determining whether the price of a security is generally trending upwards, downwards, or sideways, as well as assessing the strength of that trend.

Several widely recognized trend-following indicators are:

  * Simple Moving Average (SMA)

  * Exponentially Smoothed Moving Average (EMA)

  * Linearly Weighted Moving Average (LWMA)

  * Wilder’s Moving Average

  * Average Directional Movement Index (ADX)


**Volatility indicators** are to assess price volatility. An increase in price volatility following a period of stability (low volatility) may signal a potential breakout from the previous price range.

Common volatility indicators include:

  * Bollinger Band

  * Keltner Band

  * STARC Band

  * Average True Range

  * Divergence Index


**Momentum/Oscillators** focus on measuring the speed at which prices are moving and whether that speed is increasing or decreasing. These indicators typically have a defined range of values (for example, from 0 to 100 or from -100 to +100). When the indicator reaches an excessively high level, it may indicate that the asset is overbought, suggesting that the price has risen too rapidly (experiencing significant acceleration) and may subsequently move sideways or reverse downward. Conversely, if the indicator reaches an extremely low level, it may indicate an oversold condition, suggesting that the price has declined too quickly and may then move sideways or reverse its downtrend, transitioning into an upward movement.

Some popular momentum/oscillators include:

  * Relative Strength Index

  * Momentum/Rate of Change

  * Moving Average Convergence/Divergence

  * Stochastic Oscillator

  * William's %R

  * Larry Williams’ Accumulation/Distribution Oscillator

  * Relative Vigor Index

  * True Strength Index

  * Vortex Indicator


And volume indicators, by analyzing volume alongside price action, traders can extract valuable information about the strength of a trend or identify potential reversal points.

Some commonly used volume indicators are:

  * On-Balance Volume

  * Money Flow Index

  * Larry Williams’ Accumulation/Distribution Line

  * Marc Chaikin’ Accumulation/Distribution Indicator

  * Chaikin’s Money Flow

  * Volume Rate of Change

  * Ease of Movement

  * Positive Volume Index/Negative Volume Index

  * Volume-Weighted MACD

  * Klinger Oscillator

  * Aspray’s Demand Oscillator


# Consideration When Using Tick Data to Calculate Technical Analysis Indicators

Tick data represents the most detailed form of data, capturing every price fluctuation of a security within a specific time period. It includes all transactions made, enabling investors to monitor even the smallest price changes. Additionally, it incorporates information on price and volume for bid/ask (3 price increments for securities listed on HSX and 10 price increments for securities listed on HNX).

The data used for technical analysis indicators consists of OHLC data. OHLC stands for Open - High - Low - Close, which is a common data format used to depict the price movements of an asset over fixed, uniform time intervals (such as 1 minute, 5 minutes, 1 hour, 1 day). OHLC data is derived from tick data, using solely matched transaction information. It comprises five primary pieces of information:

  * Opening price (Open): The first matched price within the period under consideration.

  * Highest price (High): The highest matched price within the period under consideration.

  * Lowest price (Low): The lowest matched price within the period under consideration.

  * Closing price (Close): The final matched price within the period under consideration.

  * Trading volume: The total volume of matched trades within the period under consideration.


When using technical analysis indicators, investors must first select an analysis time frame, such as 1 minute, 5 minutes, 1 hour, or 1 day, to convert tick data into OHLC data before calculation. 

The chosen time frame is a critical parameter that determines the effectiveness of the technical analysis indicator. The selection of an appropriate time frame depends on the investor's investment time horizon. For short-term investments and frequent trading, investors may opt for shorter analysis time frames such as 1 minute, 5 minutes, or 1 hour. Conversely, for long-term investments and less frequent trading, investors may prefer longer analysis time frames such as 1 day, 1 week, or 1 month. Selecting the appropriate analysis time frame will enable investors to accurately assess market trends and make effective trading decisions.

# The Application of Technical Analysis Indicators in Algorithmic Trading

Technical analysis indicators are precise calculations with specific outcomes, making them readily applicable to algorithmic trading. However, a deep understanding of each indicator's nature, its measurement function and operational mechanics is crucial in developing an effective trading algorithm.

In addition to employing existing formulas, algorithmic traders can create many other indicators based on their investment expertise and experience. By expanding data sources and adopting innovative calculation methods, algorithmic traders can gain a competitive advantage over peers who rely solely on popular tools. For example, algorithmic traders can enhance their indicator calculations based on both bid price and bid volume data to obtain a more comprehensive view of market sentiment and predict more accurate price trends, compared to relying solely on matched price and matched volume data.

---


## Stock Price Prediction – A Discipline Branch Within Social Science

*Fonte: https://hub.algotrade.vn/knowledge-hub/stock-price-prediction-a-discipline-branch-within-social-science/*

Drawing solely from data, such as financial statements, price, volume, and macro reports while employing robust models with artificial intelligence and machine learning, every single argument leads to the conclusion: stock price prediction, while not purely a random walk, should be exact science. This article opts to an alternative viewpoint, asserting stock price prediction is a specialized branch within social science.

# Is Stock Price Purely Random?

Many passive investing strategies believe that stock price prediction is purely random and unpredictable. A practical application of this philosophy is to invest in exchange-traded funds (ETFs). For retail investors, this approach has proven effective in reducing huge fees while achieving comparable long-term performance to active investment. However, there’s also evidence that stock prices are not purely random.

First, if stock prices were entirely random, how could the market consistently yield positive returns over the long term? Even naïve investors recognize that the overall economy tends to improve gradually after years. This leads to index growth and resulting profits. This approach with passive investing supports the low-fee approach and proves the stock market index is predictable in the long horizon.

Second, if stock prices were purely random, a company’s market capitalization would be detached from its core business fundamentals. This implies that a startup in Vietnam could be as valuable as Alphabet (Google), which does not make sense.

Third, considering that financial markets serve as the backbone of major global economies, how can stock prices operate purely on randomness? The impact of governance intervention and monetary policy further proves the connection between stock markets and the broader economic systems.

Considering these arguments, it becomes clear that stock prices exhibit some randomness but are not purely random. According to the Efficient Market Theory, stock prices are not random, and no one can make profits in the stock market since all available information is already reflected in the stock price. This theory assumes that all market stakeholders have the same precise knowledge and consistently agree on stock prices for every event. From the global development history, however, achieving global consensus on a random event is an unrealistic expectation.

In short, stock prices are not purely random.

# Is Stock Price Prediction an Exact Science?

To answer this question, let’s explore factors that may impact stock prices.

No |  Category |  Details  
---|---|---  
1 |  Global Event |  Covid 19 changes the economic landscape and establishes a new fair price and equilibrium for almost all financial assets.  
2 |  Macro Economics |  Sharp decrease in Interest Rate in late 2023 supports a strong rally of VN-index  
3 |  Geopolitical |  Changes in bond policy in 2022 adversely impact Novaland (HOSE:NVL) and Phat Dat Corporation (HOSE:PDR)  
4 |  Sector |  The global adoption of artificial intelligence (AI) has a positive impact on FPT Corporation (HOSE:FPT)  
5 |  Financial Statements |  Positive financial reports typically lead to an increase in stock prices  
6 |  Market Data |  The current price and trading volume serve as indicators of the supply and demand equilibrium.  
7 |  Specific Company Event |  VNDirect Securities Company experienced a security breach, which is expected to negatively impact their stock price.  
8 |  Ethics |  Price manipulator, Fraud  
  
****

While this list is not exhaustive, it highlights factors impacting stock prices. Despite an investor’s efforts, predicting future outcomes remains challenging due to the unpredictable nature of events. For example, the Covid-19 pandemic is a one-time event and no models can predict how it affects stock prices. Thus, stock price prediction isn’t an exact science. Trying to predict with high accuracy can be futile given the mix of predictable and unpredictable factors.

This leads to an essential insight: there’s no highly accurate model for stock price prediction. To quantify this argument, let’s compare this to natural science. Natural science relies on models. Like in physics, Newton’s universal law of gravitation and classical mechanics models yield convincing outcomes, such as an apple falling to the earth. In production, accuracy often exceeds 99.99%. Scientific models typically prove themselves with over 95% confidence. However, in stock trading, our guess of good model accuracy after all fees and taxes is only around 55%.

Trading stands apart due to a key insight: even completely wrong actions can yield favorable results with a high probability (around 35%). In other scientific fields, wrong decisions only bring disasters.

In short, a wrong action gives a trader 35% chance of success, while a right action increases it to 55%. The challenge lies in discerning whether a successful result comes from a right or wrong action. This makes stock trading extremely hard. In self-driving car design, if the car sees a red light, it must stop. That’s common knowledge, and a right action with known good results. In trading, however, no rewards or penalties can be traced by right or wrong actions.

Fortunately, algorithmic traders leverage the rule of large numbers to profit from robust models. Proving a model’s effectiveness involves applying machine learning and statistical techniques.

# Stock Price Prediction – A Discipline Branch Within Social Science

Social science differs from exact science since it deals with social and human aspects. However, there are many interesting links between social science and stock price prediction.

First, there are way too many factors that cannot be fully understood in both disciplines. Imagine solving a decision-making problem with only 2 known factors while the total number of impacting factors is 20.

Second, attributing a single outcome is exceptionally challenging. It’s difficult to trace back a good result to a right decision or a wrong decision. Looking at the past data may give obvious explanations, yet the future remains highly unpredictable.

Third, despite years of research, no concrete methods for accurate predictions exist. In the article “The Forecasting Collaborative. Insights into the accuracy of social scientists’ forecasts of societal change”, experts in social science still cannot foresee societal changes and make predictions reliably. This is similar to the story of stock trading experts.

Lastly, societal changes impact the economy, directly influencing market indices. This is a strong connection between the two disciplines. If one can predict the next societal shift and economic shift, they can make huge profits in trading. In essence, mastering sociology holds immense value for stock price prediction.

In summary, this article suggests that stock price prediction and social science exhibit commonalities. It proposes that grasping sociology could enhance stock price prediction more than learning exact science such as artificial intelligence and machine learning. It’s important to note that predicting societal changes may not directly impact an individual stock, but can significantly influence an entire economic sector or a market index.

---


## Challenges in Economic Forecasting

*Fonte: https://hub.algotrade.vn/knowledge-hub/challenges-in-economic-forecasting/*

Economic forecasting is vital for businesses and policymakers. It informs investment decisions, resource allocation, and economic interventions. However, economic forecasting is a complex endeavor. Despite advanced models and big data, analysts often struggle to accurately predict the future. Forecasting involves predicting future economic conditions based on historical data, trends, and various technical indicators. Yet there’s always an underlying factor of uncertainty. Peter L. Bernstein, the editor of The Journal of Portfolio Management, wrote: “fundamental law of investing is the uncertainty of the future”.

This article discusses challenges in developing capital market forecasts. Setting wrong expectations of the capital market can lead to faulty portfolios. Keeping the same investment structure through evolving markets leads to suboptimal performance, while excessively changing portfolio composition may incur huge fees and costs with no additional benefits. The balancing act requires deep understanding of asset classes, although it’s not without challenges in a number of aspects.

# Economic Data Reliability

Economic data is collected from various sources, including government agencies, surveys, and private corporations. Surveys and samples are used to estimate broader economic trends. However, if the sample is biased toward certain industries or demographics, it can distort the overall economic health. Also data often exhibit seasonal patterns (e.g. agricultural cycles, or holiday spending in the retail sector). These fluctuations can obscure underlying trends and introduce further errors if the underlying patterns change unexpectedly.

Economic indicators are often released with a time lag. For example, quarterly financial statements get published several weeks after quarter ends, and yearly audited reports are published months after year ends. High-level macroeconomic indicators such as employment reports are typically weeks after the reference period. The International Monetary Funds sometimes reports data for developing economies with a lag of two years. This requires forecasters and analysts to work with preliminary data while anticipating revisions. Sometimes these revisions are substantial, which may give totally different inferences.

Economic data can be subject to measurement errors. These errors occur during data gathering, estimation, or aggregation. An example is misclassifying capital flows can distort economic indicators. When analyzing time series data, if forecasters only consider entities that survived until the end of the period, the resulting statistics may be affected by survivorship bias. This bias occurs since we ignore those that did not survive, leading to potentially incorrect conclusions.

**The past and the future.** Economic forecasting relies on past data to identify trends and patterns. However, using historical estimates as a sole foundation to forecast can introduce several limitations.

**Nonstationarity.** Economies are dynamic systems that constantly adapt to technological advancements (e.g. artificial intelligence in industries), demographic shifts (e.g. aging population), and changing consumer behavior (e.g. traditional shopping to e-commerce). Historical data is only a snapshot of the past economic state. If the data doesn’t reflect the ongoing changes, the economic models may miss critical turning points.

**Unique events.** Historical data is based on past events. However, unforeseen events like pandemics, natural disasters, or major geo-political changes can disrupt historical trends in unpredictable ways. Forecasts relying solely on historical estimates may not be able to account for these black-swan events, leading to inaccurate predictions of the future economic state.

**Extrapolation limitations.** A core function of economic forecasting is to extrapolate historical trends into the future. This approach assumes that past patterns will continue. It may not always be the case. Economic behavior can change abruptly, rendering historical trends unreliable to predict the future. An example is a high ex post (after-the-fact) return can be a poor estimate of ex ante (before-the-fact) expected return. Similarly, considering risk measures such as value at risk, a high ex post risk can be a biased measure of ex ante risk.

Analysts generally benefit from using the longest data history available. This practice ensures stationarity, as sample statistics derived from a longer history tend to be more stable than those with fewer observations. Although it might be tempting to use higher-frequency data (like weekly instead of monthly), it doesn’t guarantee more precise estimates. While higher-frequency data can enhance the precision of sample variances, covariances, and correlations, it doesn’t improve the mean estimate.

In the context of big data where many variables are involved, having a substantial number of observations becomes essential. For instance, when calculating a sample covariance matrix, it’s necessary to have more observations than the total number of variables (e.g. assets). This challenge often arises in investment analysis at the national or global scale. Also, it’s important to consider whether trading data follow a normal distribution or not. In the case of historical asset returns, they often display skewness and heavy tails, which lead them to deviate from normality. Addressing this non-normality can be analytically complex and costly.

# Model Uncertainty

Economic models are similar in essence. They represent a simplified version of reality, capturing the interplay between various factors. However the challenge lies in selecting factors to include and represent them mathematically. The inherent limitations in any model simplification certainly contribute to model uncertainty.

The majority of economic variables and their potential relationships can lead to a dilemma. Choosing which variables to include and which to leave out can introduce a selection bias. This behavioral bias may eventually lead to uncertainty and inaccurate forecasts.

Economic models rely on mathematical equations to represent complex economic relationships. These equations are, by necessity, simplifications for readability. The real world is often messy with disruptive events. Simplifications in data modeling like normality or linearity adds an element of uncertainty into future forecasts. In practice, besides simplified models, there are complex ones that may become opaque black boxes. It’s conceptually challenging to understand how these models arrive at those predictions. It’s even more difficult to assess the model’s reliability and trace the source of potential errors.

When model assumptions become flawed, it often leads to catastrophic uncertainty and disastrous consequences. While parameter uncertainty and input uncertainty can be mitigated through different statistical approaches (e.g. estimation errors and attention to unobserved random variables), incomplete model assumptions can crumble the entire forecast.

An example is from the financial crisis when many economic models leading up to 2008 assumed continued stability in the housing market and the financial system. These models assume housing price declines are geographically isolated. They failed to account for the risks associated with complex financial instruments like mortgage-backed securities, made by institutions who had very little incentive to vet loan quality.

Another example is in the 90s when most models set the long-term equity expectation higher and reallocated more capital into equities due to the rise of internet web-based business sectors. This led to further equity price appreciation. It misread the technological disruption, and many forecasts overestimated the internet potential on established industries with infinite growth fallacy. The bubble eventually burst in 2000, and the NASDAQ stock exchange, heavily weighted towards tech stocks, plummeted. This reminds the dangers of basing forecasts on assumptions that misaligned economic reality.

Economists, nevertheless, are working to reduce uncertainty and improve model accuracy in different approaches. One is to employ a technique of model ensembling, using multiple models instead of relying on a single model. This involves running multiple models with different assumptions and combining their forecasts. This approach is to mitigate the model biases and provide robustness. Another approach is to employ Bayesian statistics. It allows economists to incorporate prior knowledge into the model. By factoring in economic knowledge, it can be helpful when dealing with high levels of uncertainty to improve the model’s adaptability. Also a technical approach to research models is to conduct stress tests. Economists often run simulations to explore how models behave under various exogenous shocks and unforeseen events, providing valuable insights into the potential outcomes and model limitations.

---


## Five Personal Factors Influencing Investment Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/five-personal-factors-influencing-investment-strategy/*

Each individual has unique investment objectives, whether it is saving capital for retirement, growing capital, or generating a steady income for short-term needs. Clearly defining investment objectives is the foundation for building an effective investment strategy that aligns with each individual's objective.

The qualitative investment objective to quantify includes two main factors, the return objective and risk tolerance. These two elements are closely related. Investment strategies offering high returns often entail higher levels of risk. Therefore, investors must carefully weigh return objectives against risk tolerance when selecting an appropriate investment strategy. Additionally, investors' return objectives and risk tolerance should be considered in the context of their specific constraints, such as investment capital size, time horizon and liquidity requirements. These factors directly impact investors' risk tolerance, consequently influencing their return objectives.

Overall, building an investment strategy tailored to each investor requires consideration of the following 05 factors:

  * Return objective;

  * Risk tolerance;

  * Investment capital size;

  * Time horizon; and

  * Liquidity needs.


# Return Objective

Return objective refers to the percentage of return an investor aims to achieve within a specified time horizon to meet a financial objective. Return objective can be expressed in various forms, such as:

  * Average percentage over a time horizon. For instance, an average annual capital growth of 15% within 3 years.

  * Specific amount. For example, reaching a profit of 10 billion VND in the current year on an investment of 100 billion VND.

  * Benchmark comparison. For instance, outperforming the VNIndex by an average return of 7%. 


Return objectives play an important role in guiding and evaluating investment performance. Comparing actual return achieved with return objective helps investors evaluate the effectiveness of deployed investment strategies. When actual returns do not reach the objective, investors can adjust the investment strategies accordingly to improve performance.

Keep in mind that return objectives should be realistic. An unrealistic return objective such as 100% per year can lead to excessively risky strategies that pose the threat of total asset loss.

# Risk Tolerance

Risk tolerance refers to an investor's willingness and ability to withstand fluctuations in asset value while pursuing their financial objectives. In other words, it indicates an investor's capacity to tolerate the risk of loss during their investment journey.

An investor's risk tolerance is influenced by two factors:

  * Willingness to bear risk is the psychological comfort level of an investor regarding the potential for financial losses. It relates to their mindset concerning uncertainty and the potential negative outcomes. In other words, willingness to bear risk is the psychological threshold of an investor.

  * Risk capacity refers to the maximum level of loss an investor can bear, taking into account their actual financial circumstances. This ensures that any losses incurred do not affect their financial plan or ability to achieve investment objectives.


Risk tolerance is the equilibrium between an investor's willingness to bear risk and their risk capacity. If the investor's willingness to bear risk outweighs their risk capacity, they should opt for an investment strategy aligned with their actual risk capacity. Conversely, if their risk capacity is significantly higher than their willingness to bear risk, the investor may have missed a profitable opportunity by adopting an overly cautious investment strategy.

# Capital Size

Capital size impacts investment decisions in many different aspects. An investment capital that is too small may limit the asset options, as some assets require a minimum capital to participate. Moreover, limited investment capital may also limit the ability to diversify investment portfolios to minimize risks.

Certain investment strategies may yield optimal results with limited capital. Overcommitting capital to these strategies can result in unexpected outcomes. It is necessary to carefully assess the appropriateness of investment strategies with the existing capital size to ensure optimal efficiency.

With a significant capital size, investors may encounter the risk of price slippage during transaction execution. During such instances, building algorithms to optimize transaction costs tailored to each investment strategy type can significantly impact investment performance.

The capital size also indirectly influences stock trading fees. Investors with substantial capital may have the opportunities to negotiate lower transaction fees, thereby reducing costs and improving investment performance.

# Time Horizon

Time horizon refers to the duration an investor intends to hold their investment before needing to access the funds. Time horizon can be categorized as short-term (less than 1 year), medium-term (1 to 5 years) or long-term (over 5 years).

Investors may pursue multiple financial objectives simultaneously, with each objective corresponding to a distinct time horizon. With a long-term time horizon, investors are able to tolerate higher levels of risk since they have more time to navigate through short-term market fluctuations and potentially recover from losses. Conversely, short-term time horizons require a conservative investment strategy that prioritizes liquidity.

In practice, time horizons of less than 3 years often yield relatively unpredictable outcomes due to market fluctuations. Returns tend to be more stable with the time horizons of over 5 years.

# Liquidity Needs

Liquidity needs refer to the extent to which investors require the conversion of their investments into cash. Investors with high liquidity needs are those who require cash from their investments regularly or urgently. For example, individuals nearing retirement may have high liquidity needs to cover their living expenses, while businesses may require cash for unexpected operational costs. On the contrary, investors with low liquidity needs do not frequently or urgently require cash from their investments.

The liquidity of each investment asset type varies - Liquidity refers to the ability to easily and quickly convert an investment asset into cash without significantly impacting its value. Investors need to carefully assess their personal liquidity needs and thoroughly understand the liquidity characteristics of each asset type to build an appropriate and efficient investment strategy.

---


## Feature Improvement Procedure for Live Algorithms

*Fonte: https://hub.algotrade.vn/knowledge-hub/feature-improvement-procedure-for-live-algorithms/*

Over time, new ideas for enhancing a live algorithm will inevitably emerge. This arises from the limitation that backtesting and forward testing alone cannot fully reflect the algorithm’s real performance. In essence, new ideas that can be developed into new features will arise. The challenge lies in how an algorithmic trader can confidently transition an original algorithm to the updated version, ensuring substantial improvements. This article outlines the standard procedure for updating features in a liverun algorithm.

# Beta System

The idea is very straightforward: achieving confidence in improvements requires comparing two live algorithm versions. Thus, there’s a need to run these versions in parallel. Algorithmic traders may propose using a smaller initial capital for an alternative algorithm version. However, for safety reasons and to reduce risk of untested technical bugs, a Beta System is recommended as a good practice.

A Beta system is sophisticated like the production system but differs in key aspects. First, it operates with limited capital to minimize risks. Second, it doesn’t have the same group of all live algorithms to maximize capital utilization. Third, it allows frequent updates daily to an algorithm and manual adjustments to trading logs, which is nearly impossible in a large-scale production system.

Although setting up and maintaining a parallel version may be costly at the beginning, the long-term benefits will be well worth it. Refactoring the system into independent core functions can significantly reduce setup costs by sharing the same core functions between both systems.

# Benchmark

Algorithms are usually benchmarked against the risk-free rate or market indices. However, in this case, an alternative benchmark is necessary: the original version of the algorithm itself.

When upgrading features, it’s common to test performance in a live environment. Though this isn’t sufficient to determine the value of a new feature. Algorithm traders should be careful not to upgrade to a new version solely based on positive results, as the original might yield even better outcomes.

To assess which version is superior, consider each day as a race, and analyze the trade log produced by each version. The version that consistently performs better has a higher likelihood of becoming the production version.

# Comparison Criteria

The upgraded version will be deployed in the production system if it successfully meets all three criteria during the comparison phase.

**Excess Alpha:** The difference in returns between the upgrade version and the original version is recommended to be a key criterion.

**Excess Alpha = Alpha of Upgraded version – Alpha of Original version**

The excess alpha, when plotted against historical data and live running data, is often expected to be positive. A positive excess alpha indicates the upgraded version outperforms the original version. If the excess alpha remains positive and stable during live running, consistent with historical backtesting results, it serves as a robust indicator of significant feature improvement.

**Example plot of excess alpha**

In the example above, a negative excess alpha indicates that a feature is not yet suitable for deployment in the production system. To meet the passing criterion, the accumulated excess alpha must remain positive and stable over a specific period of time or a certain number of trades, depending on the algorithm’s nature.

**MDD of Excess Alpha:** Maximum drawdown of excess alpha.

This criterion serves as a stop-loss threshold if the performance of the upgraded version falls significantly below that of the original version. To meet the passing criteria, during the live comparison phase, the maximum drawdown (MDD) excess alpha should not drop below this threshold as observed in backtesting.

**Return:** Regardless of good excess alpha and maximum drawdown of excess alpha, an upgraded version must achieve a positive return compared to the risk-free rate or market index. Besides this, another possible case is the upgraded version has reduced risk but also lowered reward. In this situation, the algorithm may not necessarily improve overall return but will limit risk exposure. Thus, ensuring a positive return relative to the algorithm benchmark becomes the third criterion to consider.

In conclusion, following this procedure allows algorithmic traders to confidently upgrade live-running algorithms. It’s essential to define the time horizon for trades or the duration before entering the comparison phase. If the upgraded version doesn’t qualify but still offers values, conducting paper trading comparison can help assess feature robustness. After paper trading, algorithmic traders can start a new comparison testing phase.

---


## Overfitting and How to Mitigate It

*Fonte: https://hub.algotrade.vn/knowledge-hub/overfitting-and-how-to-mitigate-it/*

Algorithmic trading uses computer algorithms to automate trading decisions. These systems manage investment portfolios and execute orders with the goal of generating positive returns in the financial market. A key component of algorithmic trading is the identification of trading signals, also known as alphas.

In the field of quantitative trading, there are two primary methods for generating alphas. The first method is idea-driven, where alphas are derived from various sources, including trading hypotheses, journal papers, anecdotes, or spontaneous ideas. Quantitative traders transform these ideas into potential trading signals. The second method is data-driven, where alphas are generated from technical analysis, pattern recognition, machine learning models, or economic analysis of financial reports. These alphas can be extracted from datasets that are either collected internally or obtained from external data service providers.

No matter where the alpha comes from, a comprehensive and rigorous verification process is essential. Algorithmic traders estimate the potential for positive returns in real trading scenarios. Backtesting is a vital part of this process, as it evaluates potential returns and considers the maximum drawdown a strategy might encounter. Top-tier quantitative trading firms prioritize robust backtesting and market simulations to solidify their investment performance. This article highlights the fundamental concepts in backtesting and the common pitfalls of overfitting in this process.

# Backtesting

In finance, predictions based on time-series data do not assure absolute certainty for individual instances. In fact, predictions are only feasible in a statistical sense: random errors average out to a reasonable degree of accuracy only over a large number of predictions. Even leading trading firms experience losses in real trading, despite positive returns in market simulations. It’s thus important to allocate capital appropriately among different alphas and trading strategies.

In financial research, many assumptions prove incorrect. Many experiments yield negative results. Only a handful of trading signals have the potential to consistently generate profits in real trading. This is because financial markets often behave counterintuitively. The initial model may work in the market but only have weak effects, overshadowed by other factors. Market simulations and backtesting are therefore essential to figure out potential strategies.

Backtesting enables quantitative traders to simulate their strategies on historical data. It recreates trades that would have happened in the past based on set rules. This allows traders to evaluate the effectiveness of their strategies. The underlying assumption is that if a strategy performed well in the past, it’s likely to do well in the future. A model that didn’t perform well in the past is unlikely to be considered for real trading.

Backtesting also provides vital statistical feedback on specific trading strategies. Key metrics include net profit or loss, volatility, maximum drawdown, annualized return, and risk-adjusted measures such as Sharpe ratio, Sortino ratio, and Information ratio. These metrics help traders compare the performance of their system with existing industry standards.

There are several methods for backtesting. The simplest is the explanatory approach, which examines historical trading data. For example, an algorithmic trader might test a new rule-based Smart Beta portfolio on historical data to predict its future potential. Another technique is the Monte Carlo simulation, which models the uncertainties in the financial market that influence stock and futures prices, resulting in a range of potential returns. A more sophisticated method involves using advanced pricing models to determine the price of assets and derivatives. Examples include the Black-Scholes model (1973), the stochastic volatility model (1976), the jump-diffusion model (1996), and recent data-driven models enabled by advancements in computing and artificial intelligence. The research of neural networks in the past decade, such as variational autoencoders (VAEs) and generative adversarial networks (GANs) shows promising potential in working with financial time-series data.

# Overfitting

In real trading, however, many factors will influence investment performance. Positive backtesting results do not necessarily translate into a profitable strategy for several reasons. First, the current financial market may differ from the historical period used in backtesting. Market rules and participants are constantly changing, and new technologies often change trading behaviors. Second, real trades incur commissions and transaction costs, and the trades themselves can impact the market at a large net asset value. This leads to price slippage and implementation shortfall in unfavorable directions. Lastly, overfitting could occur, where algorithmic traders select alphas from favorable backtesting results due to random chance or emotional bias, but these alphas may have limited predictive power.

Overfitting is the inherent risk in any backtesting process. It happens when a trading strategy is overly adjusted to fit historical data, capturing not just the underlying market signals but also noise and random fluctuations. A seemingly significant correlation or spurious relationship from the historical data may lack the fundamental causes and economic grounds to recur in the future. With enormous computing power, the likelihood of discovering random correlations increases, as does the risk of overfitting. 

Complex trading strategies that excel on historical data may have detailed rules and parameters specifically optimized for the training set. However, they may not perform well with new, unseen data because they were optimized under specific conditions, such as the pandemic, which may not recur at a similar scale.

Similar to machine learning, there’s always the bias and variance trade-off in finance. Overfitting happens when a trading strategy captures both the true underlying patterns and excessive variance. Selecting results with impressive backtesting, known as cherry-picking, is a behavioral bias that often leads to overfitting. Excessive parameter optimization can also result in overfitting. Therefore, it’s critical to strike a balance between fitting the data and maintaining the robustness of the strategy.

# How to Mitigate Overfitting

In statistics and machine learning, different methods have been proposed to avoid overfitting during the learning process. Examples are tenfold cross-validation, regularization, and prior probability. Recently, academic research papers addressing overfitting have been published in the field of quantitative finance. Drawing from concepts in statistical learning, the following are some strategies for mitigating overfitting in backtesting. 

**Out-of-sample testing.** This involves dividing historical time series data into two or more segments. The idea is to reserve a portion of the historical data to serve as unseen test sets. This reserved partition acts as a proxy for real trading. It’s important to note that out-of-sample periods should not be prior to the training data, as the training data may already absorb past events.

**Cross-validation.** This is a technique used to evaluate how effectively a model can generalize to new, unseen data, similar to out-of-sample testing. An example is in smart beta development. Good alphas typically work across various assets, exchanges, and regions. For example, equity models created in the US can be applied to Asian markets, or models developed for one exchange can be used on another within the same country.

**Increase in-sample Sharpe ratio requirement.** A higher Sharpe ratio in the training set reduces the risk of overfitting in the validation set and in real trading. It’s often recommended to train the model over a longer historical period to capture a diverse range of market events. Extending the backtesting period reduces the chance of accidental overfitting. The number of backtesting days needed to confirm a certain Sharpe ratio level often grows exponentially with the ratio target.

**Minimize parameters and operations.** Overfitting is often a result of a model having too many parameters. These parameters enable the model to closely fit the training data, capturing more noise than actual signals. By reducing the number of parameters helps models become less susceptible to changes in parameters. Fewer parameters often lead to improved generalization.

**Walk-forward optimization.** This is a technique that helps mitigate the risk of overfitting by dividing historical data into overlapping periods. Each segment consists of an in-sample period and an out-of-sample period. For each segment, the parameters are trained using the in-sample period and evaluated on an out-of-sample period. This process is repeated over all segments, and the average results from all out-of-sample periods give a realistic estimate of the strategy’s performance. This method helps find adaptive strategies to different market conditions, and prevent overfitting to a specific timeframe.

# Conclusion

Creating portfolios with genuine alpha strategies that capture the essence of market dynamics leads to profitability. While backtesting is crucial for discovering these alphas, it can also introduce overfitting, resulting in a misleading sense of assurance in profitability. Building a robust system requires finding the right mix of sophistication and adaptability to ensure strategies succeed in real-world conditions, not just in historical simulations and paper trading.

To prevent overfitting, it’s essential to pinpoint robust alphas that serve as a reliable guide. These alphas should be resilient to changes in market specifics or conditions. Financial markets are often characterized by their historical tendencies and gradual evolution, reflecting traders’ activities. An alpha that was effective in the past may not be profitable moving forward. Continuously refining strategies with a robust backtesting framework is crucial for future success.

---


## Moving Average

*Fonte: https://hub.algotrade.vn/knowledge-hub/moving-average/*

# What Is a Moving Average?

**Moving average** (MA) is the average price of a security over a specific number of periods. Moving average smoothes out short-term price fluctuations, giving technical analysts a clearer view of market trends (Figure 1).

Technical analysts often use a **Simple Moving Average** (SMA), in which each price level is equally weighted in calculating the calculation. Some technical analysts prefer to use an **Exponential Moving Average** (EMA), also known as an exponentially smoothed moving average, where the most recent price levels have the greatest weight, decreasing exponentially for older prices.

**A Linearly Weighted Moving Average** (LWMA) is another type of moving average similar to EMA, however, instead of exponential smoothing, LWMA assigns linearly decreasing weights to older prices. 

# Formula

Below is the calculation formula for the 03 types of moving averages mentioned above.

**Simple Moving Average (SMA)**

Where:

  * N: The number of periods used to calculate the average (the period length can be 1 minute, 5 minutes, 1 hour, 1 day, etc.)

  * SMAt(N): Simple moving average at period t, calculated based on stock price of the most recent N periods; 

  * Pt: Stock price at period t (can be closing price, opening price, high price, low price or average price of the period).


**Exponential Moving Average (EMA)**

Where: 

  * EMAt(N): exponential moving average at period t.


**Linearly Weighted Moving Average (LWMA)**

Where:

  * LWMAt(N): linearly weighted moving average at period t, calculated based on the stock prices of the most recent N periods.


# Example of Moving Average Calculation

Presented below are the calculation results for SMA, EMA and LWMA based on daily price data of FPT from 2/1/2024 to 15/1/2024, using the coefficient N = 5 days. The price used in calculation is the closing price of each day (unit: 1.000 VND).

The SMA calculation for 8/1/2024 and 9/1/2024 is calculated as follows:

The LWMA calculation for 8/1/2024 and 9/1/2024 is calculated as follows:

To calculate the EMA, it is important to determine the initial EMA value. Typically, this value is achieved by using the SMA formula:

After determining the initial EMA, the EMA for 9/1/2024 and 10/1/2024 is calculated as follows:

# How to Use

Moving averages can be used in various ways. Firstly, whether the price is above or below the moving average is a signal for trend identification. In general, when the price crosses above the moving average, it indicates an uptrend in the stock. Conversely, when the price falls below the moving average, it suggests a downtrend in the stock.

Secondly, the distance between the moving average and price is also important information. After a downtrend, when the price returns to the moving average, this line can act as resistance level. Similarly, when the price begins to decrease after an uptrend, the moving average can act as a support level.

Additionally, two or more moving averages can be combined for enhanced analysis. The 5-day moving average is often used as a short-term momentum indicator, while the 20-day or 60-day moving average can be viewed as a long-term trend indicator. When the 5-day moving average crosses above the long-term moving average can be used as a buy signal, and conversely, the 5-day moving average crosses below the long-term moving average can be used as a sell signal.

In algorithmic trading both in Vietnam and globally, the moving average is the most commonly used technical indicator. All third-party softwares such as AmiBroker, TradingView or MetaTrader have integrated moving average indicators due to its simplicity of calculation as well as its application across various financial markets, owing to its reliance solely on price and volume data. Despite its status as a foundational concept in technical analysis, the profitability of this indicator has dwindled considerably.

---


## How to Integrate Expert Input

*Fonte: https://hub.algotrade.vn/knowledge-hub/expert-input-how-to-handle/*

In the context of algorithmic trading, one often encounters situations where end users have additional information that could influence decisions regarding the capital allocation to specific financial instruments in their portfolios. For instance, consider a fund manager with extensive experience in macroeconomics and geopolitics who has insights about upcoming events. This fund manager may want to adjust their portfolio by selling certain stocks and buying others based on their knowledge.

However, a challenge arises when the fund manager directly intervenes in the existing portfolio. Such interference can compromise data integrity, making it difficult to accurately assess system performance in subsequent decision-making processes. It’s important to note that the input from experts often consists of sentiment, which cannot be translated into logical sequences for algorithmic formulation.

The following is the recommendations to strike a balance between the algorithm integrity and expert input.

# Do Allow Interference

To benefit from expert insights, it’s essential to allow adjustments to existing portfolios. Other than that, there’s no alternative method to unlock valuable information that can enhance the current portfolio. To maintain transparency and minimize uncertainties, it’s advisable to publish a target portfolio along with the rationale before taking action. This practice prevents emotional interference but also helps subsequent analyses. It might seem counterintuitive to document expert ideas before implementation, it’s a recommended approach for sustainable growth.

# Customize Expert Inputs in a Semi-algo

To ensure the integrity of the original algorithm, any input from experts should be put into a separate semi-algorithm. This process involves technically separating two trading accounts with parallel accounting, which ensures that data integrity is maintained for both algorithms.

To simplify, consider this in two steps: First, the original algorithm operates without any external interference; second, based on the original algorithm’s portfolio, an expert uses the semi-algorithm to execute actions. These actions are tracked separately within the semi-algorithm and do not directly affect the original algorithm. Notably, the semi-algorithm can sell financial instruments from the original algorithm, which is not a common practice. In simpler terms, the semi-algorithm borrows assets from the original algorithm then performs its own actions.

# Quantify Expert Performance

Based on expert-matched orders, all criteria including return rate, maximum drawdown, Sharpe ratio, and Information Ratio, can be employed in a typical algorithm. After a thorough analysis of expert performance, decisions can be made on how to utilize their input to enhance the overall system performance. It’s important to note that when two algorithms run in parallel on the same account, the total return must equal the sum of the original algorithm and the expert’s semi-algorithm. 

# Review Expert Performance

This phase is critical to develop the future system. Does the expert’s input enhance or reduce the system’s performance? A transparent answer must be made.

In an ideal scenario, an expert’s insights lead to significant alpha generation. In such cases, adding the expert’s decision into manual trading becomes the ideal choice. Even better, if feasible, integrating the decision-making process of experts as a feature within the algorithm itself is the ultimate goal.

However, when the results from expert input are lackluster, or even negative, a different approach should be adopted. Fully relying on the original algorithm, without any expert judgments, may be the optimal decision. This strategy maintains performance while saving valuable time for the expert. Either way, it’s advisable to quantify the benefits from expert inputs, even though this approach can be challenging in certain circumstances.

In summary, expert input can be seen as an independent algorithm running alongside the live trading system. The key distinction lies in the expert’s ability to leverage the current portfolio as input to optimize trading performance. Evaluating expert input with metrics like the Sharpe ratio, return rates, and maximum drawdown allows us to quantify their overall value for future decision-making.

---


## Intraday Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/intraday-algorithmic-trading/*

Algorithmic trading has transformed financial markets by automating trading processes. It relies on computer programs to execute predefined strategies. These strategies analyze market data like price, volume, technical indicators, and financial statements to make decisions without human intervention.

Intraday trading involves short-term buying and selling of financial instruments, often within the same trading day. Common instruments include index futures and commodity futures. Developed markets offer additional trading options such as stocks, options, and currencies. The significant disparity between open interests in futures contracts and daily trading volume highlights the rapid growth of intraday trading in recent years.

This article focuses on the evolution of intraday trading and delves into the impact of computer algorithms on intraday trading, particularly algorithms in quantitative finance and high-frequency trading.

# History of Intraday Trading

The majority of investments in the stock market are long-term investments. They can be in the form of ETF investing or stock selections. For instance, a smart-beta portfolio assumes the global economy will improve over an extended period, leading to long positions being held most of the time. In contrast, intraday trading involves speculating on securities within the same trading day. Traders buy and sell financial instruments, anticipating whether their prices will rise or fall during that day. Intraday traders also exploit potential market inefficiencies to seize short-term opportunities.

Typically, intraday trading involves closing all open positions before or during the ATC session to avoid overnight risks and price gaps. This practice is commonly known as overnight-0 strategies. However, as the field evolves, some traders employ a related form of intraday trading where they hold positions overnight. It certainly incurs higher fees but aims to capitalize on favorable price gaps when the market opens in the near term.

Intraday trading is relatively new in the context of stock market history, and has significantly impacted financial markets. The first stock ticker tape system was invented in 1867 by Edward Calahan. However, intraday trading didn’t gain prominence in the US market until the creation of electronic communication networks (such as Instinet) in 1969 and the automated quotation system (like NASDAQ) in 1971. Subsequent deregulation of commissions in 1975 allowed traders to execute more frequent trades without excessive costs, fostering active trading. The 1990s witnessed a revolution with the advent of electronic trading platforms powered by computers. These platforms enabled faster trade execution and significantly increased trading liquidity.

# How Algorithms Impact Intraday Trading

Computers have revolutionized trading by allowing traders to execute predefined strategies through computer programs and algorithms. These lightning-fast machines enable algorithmic traders to react swiftly to market movements, benefiting intraday traders. Manually capturing rapidly arising and disappearing opportunities during the trading day has become nearly impossible.

Unlike human traders, computer programs operate neutrally, adhering strictly to predefined rules and avoiding impulsive decisions driven by emotions like fear or greed. Algorithmic trading efficiently manages large trading volumes across different stocks and future contracts. It helps traders handle a large number of positions in various markets.

In the field of quantitative finance, algorithms play a pivotal role in various intraday trading techniques. The following are examples of current practice.

**High-frequency trading (HFT).** HFT is a specialized form of algorithmic trading that aims to execute a large number of trades within extremely short time intervals, often measured in milliseconds or microseconds. Intraday traders utilize HFT strategies to take advantage of rapid price fluctuations. HFT algorithms analyze real-time tick data, identifying trading signals and executing orders at optimal prices. In practice, these algorithms, for example, react quickly to specific events, such as earnings announcements, economic data releases, or news articles, allowing traders to profit from short-term price movements. The speed and precision of HFT play a crucial role in achieving success in intraday trading.

**Scalping.** This strategy is a popular approach where traders aim to make small profits from multiple trades by capitalizing on small price movements. Unlike long-term strategies, scalping involves buying and selling trades within seconds or minutes. Scalping strategies often work futures contracts or on highly liquid stocks with tight bid-ask spreads. It’s advisable to avoid illiquid instruments since that may lead to price slippage and execution delays. In practice, scalping works best during strongly trending market conditions.

**Statistical arbitrage.** This trading strategy involves capitalizing on price differences by buying and selling the same or similar assets. The goal is to exploit inefficiencies in pricing across related assets. There are several common types of arbitrage, including pairs trading, a market-neutral approach, and risk arbitrage. Intraday traders employ these strategies to profit from short-lived discrepancies. For example, an algorithm might simultaneously purchase an undervalued stock while selling an overvalued stock in a correlated pair, with the expectation that their prices will eventually revert to their true values. Generally, this strategy can be an overnight-0 strategy, or it can hold assets over days or weeks before liquidating inventories at a favorable price.

# Challenges in Intraday Trading

Most intraday trading requires careful parameter optimization and extensive backtesting. It faces challenges, however, related to optimization bias and overfitting. While backtesting provides insights, real-world performance can significantly differ. High-frequency strategies require a delicate balance between algorithmic complexity and robustness, especially factoring in returns, transaction fees and taxes.

High-frequency algorithms, while powerful, can exacerbate volatility and impact market dynamics. Backtesting often fails to capture these nuances and potential price slippage, where the executed price differs from the expected price. Increased volatility and rapid price fluctuations can be a double-edged sword. It creates opportunities, and also increases risks. Prices can swing wildly within seconds. Without discipline, traders can be caught off guard.

In trading, there’s also the chance of whipsaws. They are sudden reversals in price direction after a brief move in the expected direction. Traders receive these false signals, leading to losses without robust analysis and risk management. The fast pace of intraday trading can bring intense emotions. Greed and fear of loss often cloud judgements. Successful traders need to detach emotionally from trades, sticking to their strategies especially during adrenaline-fueled moments.

Position sizing and risk management are top priorities in high-frequency trading. Intraday traders must define risk tolerance and set stop-loss orders. Position sizing ensures that no single trade jeopardizes their capital significantly. Ignoring risk management can lead to fatal losses. Traders must protect their capital by setting realistic profit targets and adhering to risk limits. Capital preservation ensures long-term success in the market.

Lastly, ensuring technological reliability is critical. A single malfunction or downtime can lead to missed opportunities or financial losses. Moreover, accurate and timely data inputs are crucial for trading strategies, especially for micro-second scalping strategies. Flawed data often lead to poor trade decisions. Ensuring data integrity and quality is essential for reliable algorithmic performance.

---


## Head and Shoulders Pattern

*Fonte: https://hub.algotrade.vn/knowledge-hub/head-and-shoulders-pattern/*

The head and shoulders pattern is one of the popular technical analysis patterns in stock trading. This pattern helps to identify price trend reversals and is often used to predict the end of an uptrend or downtrend. In algorithmic trading, the head and shoulders is a typical foundational pattern, making it a suitable starting point for new algorithmic traders exploring pattern-based trading strategies.

# Typical Head and Shoulders Pattern

Figure 01 below depicts a typical head and shoulders pattern - a reversal of an uptrend.

Before forming the head and shoulders pattern, the previous trend was an uptrend, defined by the trendline. Then, the head and shoulders pattern is formed as follows:

  * **Left Shoulder:** The price experiences a strong rally, with the slope of the rally steeper than the trendline, and often accompanied by high trading volume. After forming a peak at price level E1, the price falls back to price level E2, forming the Left Shoulder. Trading volume during the decline is typically lower than during the rally.

  * **Head:** An advance follows after the decline of Left Shoulder and establishes a new peak at price level E3. Typically, the trading volume during this rally is lower than that of the Left Shoulder rally, indicating less buying enthusiasm. After that, similar to the development of the Left Shoulder, the price declines back to price level E4, which is almost equal to the previous price level E2, forming the Head.


The line connecting the two lows, E2 and E4, is called the Neckline.

The price falling below the trendline is the first signal that the trend may be coming to an end and that a reversal may be starting.

  * **Right Shoulder:** The price continues with a second rally up to price level E5, roughly equal to price level E1 (Left Shoulder peak), but fails to surpass price level E3 (Head peak). When the price breaks the Neckline, completing the head and shoulder pattern, it is a signal confirming a trend reversal and the start of a downtrend.


Trading volume plays an important role in analyzing the head and shoulders pattern. When the price increases to form the Head without high trading volume, it indicates weakening buying power and signals the presence of fewer bullish investors. In technical analysis, a divergence occurs when one indicator shows a new peak (or trough) while another indicator shows the opposite. In such cases, the Right Shoulder will have an even lower trading volume than the Head, indicating that the buying demand is exhausted and selling pressure is about to dominate. Additionally, a large trading volume when the price crosses below the Neckline confirms the strength of the downtrend, increasing the reliability of the pattern.

In reality, the perfect head and shoulders pattern as described above is very rare. Common variations include two peaks in the Shoulders or Head, or two Shoulders that are not equal in height. These imperfect variations make quantifying the head and shoulders pattern challenging for algorithmic traders. However, despite the variation, the head and shoulders pattern retains its main characteristics such as the Head peak should be higher than the two Shoulder peaks (E3>E1 and E3>E5), and the two Shoulder peaks should be relatively equal in height (E1≈E5). Additionally, the Neckline does not have to be a perfect horizontal but should not be too steep.

The head and shoulders pattern can also form in the opposite direction and serves as a reversal pattern for the previous downtrend - See figure 02.

Figure 03 below is an example of a head and shoulders pattern identified in the VN-Index chart for the period from 11/2017 to 07/2018.

# Trading Strategy Using Head and Shoulders Pattern

****

A popular trading strategy with the head and shoulders pattern is to open a short position when the price crosses below the Neckline and close it at the target price calculated as follows:

Target price = E4 - (E3 - E4)

Price signals that cross below the Neckline can sometimes be noise. Therefore, to ensure a clear break of the Neckline, investors can adopt a strategy of waiting for the price to drop to a significant level below the Neckline (usually 3% or 5%) and/or a specified time limit during which the price stays below the Neckline before opening a position; when using the daily price chart, the time limit rule can range from a few days to a few weeks.

Depending on the investor's risk tolerance, the position opening point can be earlier or later than the popular strategy mentioned above:

  * Open a position when the price retraces the Neckline: After breaking the Neckline, the price usually experiences a pullback but does not surpass the Neckline before continuing to decline. This presents a second opportunity to open a position with lower risk.

  * Open a position when the Right shoulder is forming: when the Right Shoulder has formed the E5 peak and starts to decline, investors can open a position before the price crosses below the Neckline.

  * Open a position when the price declines from the Head peak: when the price declines from the E3 peak and crosses below the trendline, investors can open a position with the expectation that the head and shoulders pattern will be created.


Regardless of the position opening point, investors should have a stop-loss strategy to limit risk in case the pattern does not form as expected. Moveover, investors should not rely solely on the head and shoulders pattern to make the trading decisions. It is essential to combine this pattern with other technical analysis indicators and fundamental analysis to gain a more comprehensive view of the market.

---


## Algorithmic Trading, Quant Trading and High Frequency Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/algorithmic-trading-quant-trading-and-high-frequency-trading/*

In Vietnam, Quantitative trading has become increasingly popular, particularly due to WorldQuant’s influence. Many consider all traders who apply data analytics and computational power in trading different from manual trading as quant trading. However, there are distinct differences between quantitative trading, algorithmic trading and high-frequency trading. Understanding these disciplines can help traders choose the right career path. This article aims to clarify these distinctions.

# One Term to Rule Them All: Applied Computational Finance

Currently, there is still significant overlap among these related disciplines. However, “applied computational finance” serves as the overarching term for all these fields.

Computational finance, a branch of applied computer science, deals with problems with practical interest in finance. It emphasizes approximations of the target rather than exact solutions.

Three main applications within computational finance are quantitative trading, algorithmic trading and high-frequency trading, each with distinct approaches.

Quantitative trading focuses on developing models that predict target instrument values. It requires statistical methods, mathematical modeling, and complex mathematical skills. Artificial intelligence and machine learning also play a significant role in this field. To be qualified as a quant, a complex quantitative model is the criterion.

Algorithmic trading aims to fully automate trading processes, including data input, signal generation, executing, reporting, and risk management. Advanced algorithmic trading involves automating capital allocation, beta optimization, and multi-algorithm utilization. An algorithmic trader aims to automate all required processes to minimize human intervention. 

High-frequency trading (HFT) prioritizes speed in the target market as its core competitive advantage. A vivid example of high-frequency trading is front running a sent order. When a retail client sends an order, HFT may catch this information, analyzes whether this order can generate profits or not. In case of positive return possibility, a HFT will send its order to monetize this information. And, the order of HFT will surely arrive much sooner that the original order of the retail client. In developed markets, a retail client order may take milliseconds to transfer but HFT will only need around 700 nanoseconds. So if one order is half way through the destination, a HFT even takes a lot of time to process data and sending another order will arrive much sooner than the original order. Another simple use case is latency arbitrage that exploits price differences across trading platforms. This strategy is ultra simple and the faster will be the winner.

****

# An Intuitive Way of Trader Development

An experienced discretionary trader eventually becomes weary of time-consuming tasks like monitoring the market, placing orders, and managing their portfolio. Consequently, there’s a growing demand for automating these processes. When a trader is able to minimize human intervention in the process and relies on algorithms, they officially become an algorithmic trader. 

Another trader believes in the utilization of modern technology and mathematical skills to discover superior alpha that can beat the market. He starts to focus on statistical arbitrage or applying machine learning and artificial intelligence aiming for great performance models. Achieving this goal brings them to the status of a quant trader.

After fully automating the process, the algorithmic trader tries to find other complex models that may enhance performance. After discovering working models, the quant trader comes to solve the problem of fully automation. When one achieves the target, they become a so-called “quantomation”.

A “quantomation” if ever thinking about investing in speed will invest intensively on hardware such as Field-programmable gate arrays (FPGAs). Successfully achieving this target will ultimately elevate them to a final title “Iron Trader”. This term draws inspiration from the well-known “Iron Man'' who utilizes all technological power to achieve superiority.

As it gets extremely hard for any individual to achieve “quantomation” or “Iron Trader” status, a collaboration between talent members is encouraged as a well known standard in the globe. 

# Final Thought

Despite the distinct names and differences among Quantitative trading, Algorithmic trading, and High-frequency trading, they actually share many similarities during their development. Traders need not worry about finding the absolute best approach; instead they should explore any viable path. The more expertise was gained, the closer all these fields will seem to be. And, best of luck!

---


## Equity Segmentation

*Fonte: https://hub.algotrade.vn/knowledge-hub/equity-segmentation/*

Equities play a significant role in global investments and are essential components of investment portfolios. Reasons for investment in equities include the opportunities to benefit from growth and earnings, as well as ownership stakes in diverse business entities across different sizes, economic activities, and regions. Publicly traded equities in the stock market offer higher liquidity, facilitating low-cost transactions compared to other asset classes.

Equities provide certain benefits to an investment portfolio for an organization or an individual. These benefits include capital appreciation, diversification with other asset classes, and the potential to act as a hedge against inflation. In addition, specific investment considerations help segment an equity portfolio.

# Benefits of Equities

**Capital appreciation.** Portfolios consist of shares in publicly traded companies. As these companies grow and expand their operations, their profits increase. When investors own a stake in a successful company, they benefit from its financial success. Also stock prices are influenced by market demand and market sentiment. Positive news about a company or a strong overall economy can attract more investors, leading to higher stock prices. Conversely, negative news can cause price declines. Understanding market dynamics is essential for capital appreciation. Historically, equities have delivered some of the highest long-term returns among various asset classes worldwide.

**Dividend income.** Every year some companies distribute dividends to their shareholders. These dividends represent a portion of their annual profits. Owning dividend-paying stocks can provide a reliable source of income. Some companies choose to distribute cash flows as dividends instead of reinvesting them in projects, particularly when suitable investment opportunities are scarce. However, while large corporations often increase their dividend payments over time, there are no guarantees that these payments will continue to grow or even be maintained.

**Diversification.** Equities tend to behave differently from other asset classes, such as bonds or real estate. When bonds face challenges for example, an equity portfolio may thrive. By investing in stocks, capital is allocated to different sectors and companies. While equities often exhibit high correlation in returns, combining them with other assets creates a risk-adjusted portfolio. Although diversification doesn’t guarantee against losses, it enhances the likelihood of preserving capital.

**Hedge against inflation.** Some companies or sectors with inelastic demand from their goods and services can raise sale prices in line with inflation, such as sectors in raw materials, energy, industrial metals. As a result, their revenues and earnings may also increase. Holding these equities allows investors to participate in this growth, preserving purchasing power. Also equities tend to grow in value over a long period of time. Diversifying a stock portfolio helps safeguard against the erosion of purchasing power caused by inflation. Empirical studies show a positive correlation between real equity returns and inflation, though this relationship depends on the assessed time period. Notably, equity prices often serve as a leading indicator of the business cycle, while inflation is typically a lagging indicator.

# **Segmentation of Equities**

In the realm of publicly traded equities, there are multiple methods for building equity portfolios, mutual funds, or open-ended funds. An important task for portfolio managers is to segment equities or sectors according to similar characteristics. This segmentation enables better evaluation and construction of equity portfolios, as well as targeted capital allocation based on the portfolio or fund’s objectives. The following are the most commonly used approaches to segmentation.

**Segmentation by investment size and style.** The most popular approach is to consider market capitalization (size) and investment style of stocks. For size, an equity is often categorized by large-cap, mid-cap, and small-cap. For style, it can be growth, value, or a core, which maintains a neutral stance, not favoring either growth or value. The following tables highlight key characteristics of size and style segmentation.

Portfolio managers enhance client investment strategies by categorizing equities according to size and style. This approach enables better decision-making and portfolio construction by considering the risk-return tradeoff across different segments. Additionally this segmentation facilitates diversification across economic sectors and industries, reducing concentration risks associated with investing in various sizes and styles.

Through this segmentation, managers can analyze how company characteristics change over time (e.g. moving from small-cap to mid-cap, or from growth to value stocks). They can then adjust capital allocation based on changing market conditions, client preferences, and comparative benchmarks. For example, a small investment firm may specialize in mid-cap and small-cap companies, seeking to outperform a benchmark index or comparable peer group of mutual funds. However, the key disadvantage of this approach is that the categories may be defined differently across investment firms.

**Segmentation by economic activities.** Equities can be grouped into sectors and industries based on their economic activities. Some examples include technology, healthcare, and finance sectors.

There are two main approaches in this segmentation: the market-oriented approach and the production-oriented approach. In the first approach, companies are categorized based on the markets they serve, consumer usage of their products, cash flow generation. This sheds light on consumer behavior, market dynamics, and revenue streams, helping investors in understanding growth opportunities. On the other hand, the production-oriented approach groups companies by the products they manufacture and necessary production inputs. For example, companies producing automobiles and companies producing semiconductors belong to two different segments. This approach has an advantage of comparing similarities in production methods and the firm cost structures. It’s also useful for assessing supply chain risks.

There are 4 main global classification systems. The global industry classification standard (GICS) uses a market-oriented approach, while the Industry Classification Benchmark (ICB), the Thompson Reuters Business Classification (TRBC), and the Russell Global Sectors Classification (RGS) use a production-oriented approach. Each classification system drills down to 3-4 levels as in the table below.

Overall, economic activity segmentation provides considerable advantages. First, by investing across different sectors, investors diversify their portfolios and spread the respective risks. Second, investors can choose to focus on specific industries they forecast will outperform due to trends or growth prospects. Third, sector rotation allows portfolio adjustments based on economic cycles (e.g. defensive sectors during economic downturns and recessions). However, this segmentation requires accurate market timing, which can be difficult at certain market conditions. Another limitation is that this can lead to sector bubbles as investors chase hot sectors and inadvertently lead them to inflated valuations (e.g. dot-com bubble during the late 1990s).

Segmentation by geography. Geographic segmentation is of consideration for global, international investment funds such as iShares MSCI Frontier and Select EM ETF. It involves dividing stocks based on the regions or countries the funds operate. The following table illustrates 3 different types of geo markets.

Geographic segmentation offers significant benefits in emerging and frontier markets due to their rapid economic growth and demographic trends. It also opens access to specific sectors across different regions, enhancing portfolio diversification. However, key limitations include higher volatility in emerging and frontier markets. These markets often have limited liquidity as well, making it challenging to buy or sell large positions without impacting prices. Currency risk from exchange rate fluctuations can impact returns for international investments for performance evaluation purposes.

Each segmentation approach has its own benefits and risks, from exploiting opportunities in different markets to managing volatility and liquidity. Applying the appropriate segmentation approach will help optimize investment performance and build a sustainable portfolio.

---


## Weighting Methods Used in Smart-Beta Strategy

*Fonte: https://hub.algotrade.vn/knowledge-hub/weighting-methods-used-in-smart-beta-strategy/*

In smart-beta strategies, defining the set of rules to filter a list of potential stocks is just the first step. To optimize portfolio performance, selecting an appropriate weighting method also plays a crucial role.

# Algotrade’s Common Weighting Methods

Below are 03 weighting methods commonly used by Algotrade in smart-beta strategies:

  * Equal weighting;

  * Market-capitalization weighting;

  * Industry market-capitalization weighting.


## 1\. Equal Weighting

With the equal weighting method, capital is evenly allocated among the constituent stocks, with the weight calculated as follows:

where:

\- wi is the weight of the capital allocated to stock i;

\- N is the number of stocks in the portfolio.

This method is simple, easy to understand, and easy to implement, providing good diversification while avoiding excessive concentration in a few stocks. However, it may potentially allocate too much capital to small-cap and less liquid stocks, leading to increased transaction execution costs.

## 2\. Market-Capitalization Weighting

In the market-capitalization weighting method, the weight of each constituent stock is determined by dividing its market capitalization by the total market capitalization of all the stocks in the portfolio. Market capitalization is calculated by multiplying the number of shares outstanding by the market price per share.

The formula for market-capitalization weighting is as follows:

where:

\- wi is the weight of the capital allocated to stock i;

\- Qi is the number of outstanding shares of stock i;

\- Pi is the price of stock i at the time of calculation;

\- N is the number of stocks in the portfolio.

The market-capitalization weighting method allocates investment capital proportionally to the market capitalization of the stocks, prioritizing large-cap and high liquid stocks. This method helps minimize trading execution costs and facilitates easy scaling for large portfolios, which is common in index funds. However, this method might lead to excessive concentration in a few large-cap stocks, reducing portfolio diversification. It may also overlook the growth potential of smaller-cap stocks.

## 3\. Industry Market-Capitalization Weighting

This method combines market-capitalization weighting and equal weighting while considering industry classification factors, helps to optimize capital allocation and reduce concentration risk. The weight of each constituent stock is calculated as follows:

  * After identifying potential stocks, classify them into industry groups based on the ICB or GICS (level 1).

  * Apply the market-capitalization weighting method to allocate capital to industry groups with constituent stocks. Industry groups without any stocks meeting the selection criteria will have a weight of 0.

  * Within each industry group, allocate capital evenly to the constituent stocks using the equally weighting method.


This method utilizes the advantages of both equal weighting and market-capitalization weighting. It reflects the market value of each industry group while ensuring diversification within each group.

# Overweight or Underweight

Depending on the stock screening criteria and market conditions, there is a possibility that in some portfolio rebalancing periods, very few stocks will meet the criteria. This can result in overweighting a few stocks. Additionally, when using the market-capitalization weighting method, capital may be disproportionately allocated to some stocks compared to others. To mitigate this situation, algorithmic traders can establish a maximum capital weight limit for each stock.

For instance, a smart-beta trading strategy employing market-capitalization weighting with a maximum individual stock weight limit of 0.25. Assuming an investment portfolio with 05 stocks that meet the screening criteria, the calculated market-capitalization weights of these 05 stocks might be as follows:****

The weights of stocks A and B under the market-capitalization weighting method are wACap=0.35 and wBCap=0.30, respectively. Since both weights exceed 0.25, applying a weight limit condition sets the portfolio weights for stocks A and B at wA=0.25 and wB=0.25. 

The excess weight portion for both stocks A and B (0.15=0.35-0.25+0.3-0.25) will be allocated to other stocks or cash.

If the algorithmic trader chooses to allocate the excess portion to other stocks in the portfolio, the weights of the remaining 03 stocks can be increased as follows:

The table below shows the adjusted weights following the implementation of a weight limit condition of 25%:

In addition to setting a maximum weight limit to avoid overweighting capital in a few stocks, the algorithmic trader also needs to consider a minimum weight limit to prevent underweighting capital in a stock. To address this issue, the algorithmic trader can set a minimum weight limit for stocks in the portfolio. For example, if the minimum limit is 0.5%, any stock with a weight less than 0.5% will either be removed from the portfolio or its weight will be increased to this minimum level.

# Weighting With Stocks on the Priority List

Stocks on the priority list in the context of smart-beta trading strategies are stocks actively selected by the investor to increase their capital allocation in the portfolio, based on information or in-depth analysis beyond the stock screening rules.

At Algotrade, the weighting of priority stocks in smart-beta strategies is determined based on the parameter set ****[f i; ki] provided by investors for each stock.

Where:

\- fi is the fixed capital allocation priority for stock i, regardless of whether it meets the stock screening criteria;

\- ki is a multiplier coefficient used to adjust the allocation weight for stock i according to 1 of the 3 allocation methods mentioned above.

For example, an investor designates stock A as a priority stock with the parameter A[fA;kA] = A[10%;1.5]. If the investment portfolio includes 03 stocks that meet the screening criteria: A, B and C, the calculated market-capitalization weights before considering the priority stock as follows:

When applying the priority stock condition, the capital weight of stock A is calculated as follows:

The capital allocation weight for stocks B and C is calculated as follows:

Therefore, to implement the smart-beta strategy, algorithmic traders can apply the simplest weighting strategy using equal weighting or opt for more complex strategies such as market-capitalization weighting or industry market capitalization-weighting. In practice, combining these weighting methods with minor adjustments can generate numerous different weighting strategies. The general principle is to select the appropriate weighting strategy according to the context, achieve investment objectives, and ensure alignment with the ability to execute the strategy.

---


## Key Insights From Career Development of Quant King Jim Simons

*Fonte: https://hub.algotrade.vn/knowledge-hub/key-insights-from-career-development-of-quant-king-jim-simons/*

James Harris Simons (April 25, 1938 – May 10, 2024) was an American hedge fund manager, investor, mathematician, and philanthropist. He was the founder of Renaissance Technologies and the Medallion Fund and also known as the “Quant King”. He was very well known for his fund performance and stability as well as early adoption of quantitative approaches on trading. His approach on quantitative trading that had been wildly successful internally should be carefully reviewed by any traders who want to make a career in applied computational finance known as quantitative trading, algorithmic trading and high frequency trading.

Collected from Simon direct interview as well as credible source of information, this article aims to provide key insights of the “quant king” ’s career development. 

# Key Insight 1: Basic Science Is the Core

Perhaps, with a top-tier background in science, who developed the Chern–Simons form (with Shiing-Shen Chern), and contributed to the development of string theory, Jim Simons prefers to work with the brightest scientist in natural science. This approach differentiates Jim Simon with the ordinary approach of focusing on top players in financial or technological markets. As a quant fund operates in the financial market utilizing the power of computing systems, people often classify themselves as fin-tech corporations which directly imply key players as either fin or tech experts. 

Jim Simons didn’t move along with the traditional thoughts. He believed in the ability of discovering new patterns in finance as a similar skill set in natural science. Thus, a great scientist in natural science should be a great candidate for his firm. That is the reason why he is looking for physicists, mathematicians, astronomers and computer scientists while finance knowledge is not even a requirement.

# Key Insight 2: Give Smart People Freedom and an Environment for Interaction

"My algorithm has always been: you get smart people together and you give them a lot of freedom. Create an atmosphere where everyone talks to everyone else. Provide the best infrastructure. And make everyone partners. That was the model that we used in Renaissance." This may be the fuel behind the secret of RenTech long term growth. 

Simons also elaborated further with the concept of “smart” in his view as having a PhDs in natural science with at least 5 years of experience and a couple of good papers. This belief was that if one can do well in discovering patterns in nature then one can replicate that concept in the financial market.

Simons also gives a clear example of some projects that he funds enough for some members for a 5-year period without knowing clearly what they are going to do in the coming future. 

# Key Insight 3: Huge Data Set, Best Infrastructure, Life-Long NDA and 100% Automation

Any good algorithm will deplete after a 5 years period so what is the long-term competitive advantage of RenTech?

First, it is a huge data set which contains basic data such as financial information and market data. Alternative data such as weather, temperature, humidity, wind speed is also collected. In fact, any data set that happens in the real time is collected if collectable. One may not know the reason why a data set is valuable until a connection is found. 

Second, infrastructure is a must. Without the best infrastructure, no algorithm, model or pattern can be utilized to its fullest. Continuous investing in the best infrastructure in the trading industry is one of key competitive advantages of RenTech. In the modern time, infrastructure is the most difficult barrier for new players to come into the field. 

Third, a life-long NDA is a requirement for all members of RenTech. This is due to the nature of unpatentable of any finding. Simons said as long as one algorithm is patent then there will be many people finding a way to go around the algorithm. So this is the nature of this industry for having no patent on algorithms at all.

Lastly, fully automation in any circumstances so no emotion and no interference may happen at any time. This approach increases the credibility of the system that all members know that no one can make trading decisions but the system only.

# Controversial 

The Medallion Fund, which is exclusively available to internal members of RenTech, had been performing greatly. According to Gregory Zuckerman's book, its annual return was 62% before fees from 1988-2021. Though, the fund that was available to external investors was not even beating the SPY. Until 2020, the annualized return of the Renaissance Institutional Equities Fund (RIEF) was only 8.05 percent in comparison to 9.6 percent of SPY. The same pattern happened similarly in other external funds that were managed by RenTech.

Also, "Renaissance Technologies was able to avoid paying more than $6 billion in taxes by disguising its day-to-day stock trades as long term investments," said Sen. John McCain, the committee's ranking Republican, condemned Simons in the use of complex financial structure to shield short-term capital gains as long-term capital gains. In September 2021, it was announced that Simons and his colleagues would pay billions of dollars in back taxes, interest and penalties to resolve the dispute.

****

For many elite traders, Jim Simons is the one who did quant when there is no quant in the world. His lifelong career which lasts until now after his life comes to an end may be a message for those who want to pursue a career in applied computational finance. Whether you believe in it or not, a smart scientific team with freedom and a supportive environment for interaction with the best tool is the best algorithm by Jim Simons.

---


## Passive, Active, and Quantitative Investment

*Fonte: https://hub.algotrade.vn/knowledge-hub/passive-active-and-quantitative-investment/*

Equities represent a substantial part of global investments. It offers various advantages to both organizational and individual portfolios. These advantages include capital growth, diversification with other asset types, dividend income, and potential protection against inflation. Equity portfolios tend to exist across a passive-active spectrum, ranging from those that closely follow a market benchmark to those that are not tied to any specific index. The latter are often managed by professional portfolio managers or investment firms, and their performance is often compared to a general broad market index to gauge their excess returns. Portfolios can take many forms, such as open-ended mutual funds, ETFs, smart-beta portfolios, or long-short portfolios. There are several reasons why an investor may select a portfolio along the passive-active spectrum.

# Passive-Active Spectrum

Investing in equities is often guided by a client’s specific goals. Asset managers typically take into account important investment objectives and constraints, such as risk tolerance, desired returns, liquidity needs, investment time frame, tax considerations, and any unique circumstances. Equities are frequently categorized by size, style, geography, and economic sector. Consequently, there are relevant benchmarks for equities in the same category. These benchmark indices usually weight equities based on their market capitalization.

In certain groups, like large-cap companies from developed markets, firms are well-established and receive extensive coverage from financial analysts. Due to their significant market capitalization, all publicly available information is thoroughly analyzed and typically reflected in their stock prices. This reduces the chances of achieving excess alpha, diminishing the need for an active portfolio manager in these groups. Consequently, these portfolios are mostly managed passively with infrequent rebalancing throughout the year.

On the other hand, for equity groups such as mid-cap and growth stocks, or equities from emerging markets, having a professional portfolio manager is crucial. These managers actively analyze the equity mix and may rebalance the portfolio more frequently, like monthly or even weekly. This rebalancing process involves adjusting capital allocation and often includes adding new stocks or removing existing stocks to meet the risk and return objectives.

The table below illustrates various investment themes within the passive-active spectrum of equity portfolios. In certain categories, equities are entirely managed actively, whereas in others, there are mainly managed passively.

# Active Investment

Several ETFs are available to track standard indices, serving as straightforward forms of passive investment. An index fund that mirrors its benchmark requires minimal rebalancing. Client preference plays a crucial role in choosing between passive and active investing. Additionally, investors’ beliefs about the potential of active strategies to generate significant excess returns are important, given that active management is generally more costly than passive management. Investors must weigh the benefits of achieving excess return against the additional costs. The table below highlights various cost components linked to active funds.

An active investment manager must be confident in their ability to outperform their benchmarks. This involves understanding their investment universe, and conducting a competitive analysis of other managers with similar investment universes. The choice of benchmark is crucial for attracting new investors. Active managers must have benchmarks consisting of sufficiently liquid securities to keep trading costs reasonable.

# Quantitative Investment

Quantitative strategies refer to investment methods that leverage mathematical, statistical, and data-driven techniques. These strategies systematically exploit market inefficiencies, anomalies, and patterns. Instead of relying solely on human judgment, they follow predefined rules to generate returns. Quantitative funds enhance efficiency and risk management, relying on accurate statistical models and robust trading data. They serve as a bridge between passive and active investment, combining rule-based investing with factor-driven insights. Below are some examples of quantitative investing.

**Smart-beta portfolio.** Unlike traditional market-cap weighted indices, smart-beta strategies emphasize specific factors such as size, quality and momentum. Factor-based investing seeks to enhance returns or mitigate risks by quantifying investment decisions based on predefined rules. These rules, for example, select financially stable companies, identify undervalued stocks, and capitalize on price momentum. Smart-beta strategies execute these rules using computer algorithms for stock selection and capital allocation. The ultimate goal is to achieve excess returns or improve diversification while maintaining lower costs compared to active investment strategies. 

Smart-beta strategies often benefit from algorithmic trading. Algorithms employ mathematical equations to rank, select, and allocate assets. Robust historical data plays a crucial role in backtesting the chosen factors for a smart-beta strategy. During execution, algorithmic trading ensures timely implementation of smart-beta factors, optimizing efficiency and minimizing transaction costs, especially during rebalancing.

In portfolio management, algorithms monitor risk factors such as volatility and correlation. As a result, smart-beta strategies can dynamically adapt to changing market conditions. By eliminating emotion-driven investment decisions, algorithms maintain transparency in portfolio management and uphold disciplined execution aligned with smart-beta objectives.

**Long-short portfolio.** This is an investment strategy involving holding both long and short positions within a portfolio. Hedge funds often incorporate this strategy into their offerings. Long positions benefit from price appreciation, while short ones profit when the asset value decreases. A long-short portfolio offers the following benefits.

  * Hedge risk: combining both positions, investors can reduce exposure to big market trends and effectively manage their assets.

  * Profit from relative performance: once the long positions outperform the short positions or vice versa, the portfolio makes profits.

  * Market-neutral: the portfolio aims to be less affected by overall market trends, even in bearish or volatile periods.


In a long-short portfolio, timely execution plays a critical role in maintaining the desired balance between long and short positions. Algorithmic trading is particularly beneficial for this strategy. It executes trades swiftly, reducing transaction costs. This efficiency is essential for maintaining the desired position ratios. Algorithms also continuously monitor risk factors such as volatility in real time. This helps maintain risk exposure within acceptable limits. Stop-loss and take-profit rules can be automated, ensuring disciplined risk management. Algorithms execute these rules without behavioral bias and algorithms incorporate factors for stock selection and timing, similar to smart-beta portfolios. They optimize for liquidity, especially in large portfolios, to ensure efficient execution.

# Conclusion

Investment portfolios span a spectrum from passive to active strategies. Investors may select based on their confidence in outperforming the market, personal preferences, risk tolerance, and management costs. Passive portfolios require minimal monitoring, tracking market indices to replicate performance. Active portfolios involve more frequent reviews and active decision-making. With algorithmic trading, quantitative portfolios serve as a bridge between the two. It brings more options to investment and ensures smooth, data-driven executions. In certain market conditions, quantitative portfolios can become more effective than other portfolios thanks to algorithms targeting specific market factors. They help investors achieve precision, discipline, and responsiveness in managing portfolios.

---


## Action Bias in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/action-bias-in-algorithmic-trading/*

Millions of years ago, humans recognized that taking action is essential for survival. This instinct had been deeply hardwired and ingrained in human evolutionary development. In modern worlds, some things have changed that we may have to adapt accordingly. This is very true with the nature of investing and especially algorithmic trading.

Let’s start with some real life example:

You are the goalkeeper in the World Cup Tournament. You are facing an important penalty in which you have to choose 3 options: jump left, jump right or stay still in the center. It’s very common that you will either jump left or right and not stay still in the center. However, remaining centered statistically helps increase the chance of successfully catching the ball. Why did it happen? 

Let’s see it from the audience view of point:

The decision of jumping regardless of the outcomes in both cases often leads to better results than staying still. This motivation compels goalkeepers to dive, even though statistically, remaining stationary would increase the chance of success. This scenario serves as a classic example of action bias.

Action bias is the psychological phenomenon where individuals prefer taking action over inaction, even when no evidence suggests that doing so would lead to a better outcome.

# Action Bias in Investing

In the realm of investing, if an investor examines the news, charts, or price movements, then soon enough, a question would follow: what action should I take next? Various scenarios play out in the investor’s mind, though the fear of missing out on a new opportunity or seeing profits turn into losses or anything else ultimately will drive them to make a decision: DO SOMETHING.

What investors will do may include rebalancing their current portfolio, acquiring new stocks, changing margin proportion. Little did they know, without real strong evidence, many of these actions are a waste of time, energy and money due to transaction cost and opportunity costs.

Let's make it short, naive investors would have more than 95% chance of underperforming the market index over time because of the attempt to “maximize profits”. Perhaps, that’s why the popularity of passive investing strategies has gained much traction lately.

# Action Bias in Algorithmic Trading

Algorithmic trader is the one who needs to guard themselves most from action bias. Let’s start with four reasons why algorithmic traders are particularly motivated to take actions.

First, as an algorithmic trader, one must have very high awareness of the market. Being an expert in this field may lead to a high level of confidence in trading decisions. Sooner or later, the trader will have some trading ideas. Some may make new trading ideas on a daily basis. This should make a lot of sense to do something in light of so many perceived good trading ideas. 

Second, a high-level algorithmic trading approach will minimize manual intervention. Zero interference policy is a must to stabilize the trading system. A trading expert in financial markets with zero trading activity allowed seems very counter intuitive. This will make executing some action or changing some configuration in the system very tempting. 

Third, financial markets can offer substantial rewards to traders who make the right decisions within a short time frame. The allure of becoming “rich” or “successful” in just one or two actions is absolutely captivating for an individual, even for a high-level intellectual person.

Lastly, algorithmic traders have access to powerful trading tools that enable them to execute strategies beyond what discretionary traders can achieve. This advantage may lead to excessive utilization of these tools, driving lots of actions.

These underlying reasons may drive the psychological state of an individual to take some actions even though it is going against the carefully designed system for optimal results. The results for some interference are hard to evaluate though in many cases it will be counterproductive by reducing performance, compromising data integrity and incurring higher costs.

At Algotrade, we believe guarding yourself against action bias is very important as an algorithmic trader.

# How to Reduce Action Bias

Be rational and opt for the long-term best option for the priority target. In case of the goalkeeper, one’s psychology can determine the action of “not jump” if his thinking model as of follow:

Also, keep in mind that inaction is a real valid option in the modern world. When uncertain, taking action without understanding can lead to excessive costs without results. Inaction by choice is a very high intellectual choice that can be made by experts and totally different from inaction by default which is labeled frozen or lazy. The later will undoubtedly only bring bad results in the long term while the former may bring you to the next level of expertise. A small note that one individual always needs a way to release energy by some specific actions, thus choosing inaction in some areas may need some actions in other areas. The optimal choice will make the better outcomes in both fields.

Ultimately, don’t be tamed by irrational behavior without root cause. You have the power to learn and adapt to guard yourself from your instinct of “doing something”. This process takes time but it is very well worth it if you ever choose a career path in investing or algorithmic trading specifically.

---


## Quantitative Hedge Funds and Algorithms

*Fonte: https://hub.algotrade.vn/knowledge-hub/quantitative-hedge-funds-and-algorithms/*

The stock market has undergone significant evolution over the centuries. The first official stock exchange was established in Amsterdam in 1602. In 1688, Joseph Penso de la Vega, a stock operator and writer, published “Confusion of Confusions,” a treatise on economic philosophy that outlined valuation principles to predict the stock market. These principles were foundational for the development of complex derivatives and speculative techniques on the Amsterdam Stock Exchange, marking an early attempt to develop forecasting algorithms.

Two centuries later, the New York Stock Exchange was officially founded in 1817. In the late 1800s, Charles Dow, co-founder of the Wall Street Journal and creator of the Dow Jones Industrial Average index, largely developed technical analysis. His work was one of the earliest systematic approaches to market forecasting.

Until the 1960s, nearly all back-office tasks and stock settlements were handled manually. Between 1965 and the 1970s, the daily trading volume on the New York Stock Exchange surged by 240%. To manage this increased volume, computers and programmable devices became essential for digitizing back-office operations. The introduction of computing machines revolutionized the trading floor and led to the emergence of a new investment industry focusing on computer-based investment methods. Quantitative hedge funds and quantitative investing strategies have become scalable and dependable in a relatively short time frame since the 1980s, following the establishment of Renaissance Technology and D.E. Shaw & Co.

# Trading Signals in Computer Age

Before the computer era, trading signals were derived from manual analysis, which included simple technical indicators and fundamental analysis. Simple technical indicators involved methods like chart patterns, moving averages, and trend lines to spot potential buy or sell opportunities. Fundamental analysis encompassed value investing metrics like dividend yield, P/E and P/B ratios, and growth investing metrics like revenue and earnings growth, forward P/E ratio, and Price/Earnings-to-Growth analysis. These methods were often constrained by human limitations and subjectivity. 

The advent of computers revolutionized trading signals. Computational power allowed traders to develop unique signals through quantitative models that use historical data to predict market movements. Computers also enabled algorithmic trading, which analyzes market data in real-time and executes orders within milliseconds. Algorithms can exploit market inefficiencies and arbitrage opportunities that would be impossible without an automated system.

In addition to generating new trading signals, computers facilitate the verification of potential signals through backtesting. This rigorous process allows traders to simulate their strategies using historical data to access performance, helping to filter out ineffective strategies.

# Quantitative Hedge Funds and Mutual Funds

While mutual funds have been around for over a century, hedge funds are relatively new to the financial market. In 1949, Alfred Jones pioneered the first hedge fund strategy by combining long-term stock positions with short-selling to reduce risk. This innovation, known as the classic long/short equities model, also utilized leverage to boost returns. Quantitative hedge funds started to grow in the 1980s with the advent of computers that allowed for more complex strategies. By the 1990s, quantitative hedge funds gained prominence as notable asset managers transitioned from mutual funds to hedge funds. As of 2023, the largest hedge fund globally is Field Street Capital Management, managing $298 billion in assets.

Unlike hedge funds, mutual funds consist of portfolios of stocks, bonds, or other securities purchased with pooled capital from investors. This setup provides individual investors with access to diversified, professionally managed portfolios. Leading mutual fund managers include Vanguard ($5.1 trillion AUM), Fidelity ($2.6 trillion AUM), and BlackRock ($307 billion AUM). The concept of mutual funds has a long history in the stock market. In 1774, a Dutch merchant created an investment trust to attract investors with limited capital. In 1907, the Alexander Fund was a significant step towards modern mutual funds, allowing investors to withdraw funds on demand. The MFS Massachusetts Investors’ Trust, founded in 1924, marked the first mutual fund with open-ended capitalization.

Born in different ages, quantitative hedge funds and mutual funds have characteristic differences in the financial industry as follows.

# Algorithms for Quantitative Hedge Funds

While mutual funds focus on stability and transparency, hedge funds frequently use leverage and margin to boost returns. They also employ investment vehicles like derivatives and can take short positions in the market. Hedge funds typically borrow capital to invest beyond their initial assets. This structure often relies on computer algorithms to manage portfolios and conduct necessary risk management during market fluctuations. Below are some common algorithms often used by hedge funds.

**Statistical arbitrage.** Stab arb is used to describe a trading algorithm based on the monetization of systematic price forecasts. While pure arbitrage is the risk-free profit from simultaneous buying and selling a basket of assets, a stat arb algorithm aims to exploit relationships between asset prices. Examples include a long/short equity strategy, and a market-neutral strategy. Note that the relationship among assets are mainly estimated from historical data, but the estimation methods are imperfect, making stat arb profits uncertain. It’s prone to overfitting, estimation errors, and it requires careful data analysis and statistical hypothesis testing to identify valid price relationships.

**Convertible arbitrage.** Hedge funds exploit the price difference between a convertible bond and its underlying stock. This strategy involves taking a long position in the convertible bonds while shorting the stock of the same company. They often aim to maintain a delta-neutral position, where the bond and stock positions balance each other as the market fluctuates.

**Quantitative analysis.** Hedge funds use quantitative analysis to inform their investment decisions. This technique involves identifying patterns through mathematical and statistical modeling, measurement, and research of large data sets. The strategy analyzes extensive data, including information from trading floors, news sentiment, social media trends, and macroeconomic indicators. This helps determine hedging factors in a downtrend market or leverage factors with pairing stocks with derivatives trading. Advanced computer algorithms, such as those from reinforcement learning and machine learning, can optimize trading strategies over the course of stock market interaction.

# Conclusion

Algorithms are crucial for quantitative hedge funds as they enable real-time data-driven decision making. As hedge funds target absolute return regardless of market movements, they can utilize algorithmic trading to identify patterns, trends, and market anomalies. This allows hedge funds to implement sophisticated trading strategies that can adapt to market conditions, minimizing human error and emotional bias. Additionally, algorithms facilitate risk management, ensuring trades are executed swiftly and accurately. Overall, the use of algorithms enhances the precision, consistency, and profitability of quantitative hedge funds.

---


## 04 Strategies for Closing Positions in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/04-strategies-for-closing-positions-in-algorithmic-trading/*

Position-closing strategies, or exit strategies, are an essential component in the development of trading algorithms. These are pre-defined plans by investors to exit a trading position with the aim of protecting achieved profits or limiting losses. The position-closing strategy is crucial because it determines the timing and method of closing a position, directly impacting the effectiveness of the algorithm. Below are 04 commonly used position-closing strategies in algorithmic trading.

# 1\. Fixed Threshold Position-Closing Strategy

To limit losses, investors predefine a stop-loss threshold, which is set below the purchase price (for long positions) or above the selling price (for short positions). When the price reaches the stop-loss threshold, the order is triggered to close the position.

To protect profits, investors set a take-profit threshold, which is above the purchase price (for buy orders) or below the selling price (for sell orders). When price hits the take-profit threshold, the order is triggered to close the position and realize the achieved profit.

In the fixed threshold position-closing strategy, the take-profit or stop-loss thresholds do not change with market price fluctuations. Investors can flexibly combine both fixed take-profit and stop-loss thresholds within the same trading algorithm, or use only one of the two, depending on their objectives and risk appetite.

_Example 01: An investor buys FPT stock at 150.000 VND, sets a stop-loss at 10% (135.000 VND) and a take-profit threshold at 20% (180.000 VND). If the price falls to 135.000 VND, a sell order will be triggered to stop the loss. If the price rises to 180.000 VND, a sell order will be triggered to take the profit._

The fixed threshold position-closing strategy is a simple and easy-to-implement method, however, it has some limitations. Since it does not account for market volatility, fixed thresholds (both stop-loss and take-profit) can be easily triggered during strong, albeit temporary, market fluctuations. For stop-loss orders, this means investors might be forced to sell at a low price, missing the chance to hold the position if the price recovers strongly. Similarly, with take-profit orders, closing the position too early may prevent investors from benefiting from further market gains, thus missing out on potentially larger profits. Therefore, investors need to balance between capital protection and profit maximization to determine suitable position-closing thresholds.

# 2\. Trailing Stop Position-Closing Strategy

In the trailing stop position-closing strategy, the initial closing threshold is set similarly to the fixed threshold strategy, based on a percentage or a fixed price distance from the entry price. However, the key difference is that this threshold automatically adjusts according to market price fluctuations, maintaining a certain distance from the highest price reached (for long positions) or lowest price reached (for short positions).

Specifically, for long positions, as the price rises, the closing threshold is adjusted upward accordingly. When the price falls, the closing threshold remains unchanged. If the price drops below the closing threshold, a sell order is triggered to close the position.

Conversely, for short positions, as the price falls, the closing threshold is adjusted downward accordingly. When the price rises, the closing threshold remains unchanged. If the price rises above the closing threshold, a buy order is triggered to close the position.

_Example 02: A trader opens a long position in FPT stock at 150.000 VND and uses a trailing stop strategy with an initial closing threshold of 135.000 VND (a fixed price distance of 15.000 VND). As the price of FPT stock changes, the closing threshold is adjusted as follows:_

  *     * _Price rises to 160.000 VND (+10.000 VND), the stop-loss threshold is adjusted upward to 145.000 VND (+10.000 VND);_

    * _Price continues to rise to 165.000 VND (+5.000 VND), the stop-loss threshold is further adjusted upward to 150.000 (+5.000 VND);_

    * _Price then drops from 165.000 VND to 160.000 VND (-5.000 VND), the stop-loss threshold remains unchanged at 150.000 VND (-0.000 VND);_

    * _Price con_ tinues to decrease to 150.000 VND, the sell order is triggered to close the position).


By using the trailing stop position-closing strategy, investors can simultaneously achieve two goals: limit losses and protect profits. As the price moves favorably, the closing threshold automatically adjusts, helping to “lock in" the achieved profit and minimize the risk of missing out on profit realization. In the event of a price reversal, the closing position (stop-loss) order is triggered, allowing investors to exit the position in a timely manner and minimize losses to an acceptable level.

# 3\. Signal-Based Position Closing Strategy

The signal-based position-closing strategy is a systematic trading approach that utilizes a flexible combination of technical indicators such as RSI, MACD and fundamental analysis factors like financial statement metrics to determine closing criteria (signals). When these indicators meet the predetermined conditions, the position-closing order is triggered.

_Example 03: An investor uses the signal-based closing strategy as follows: “When the stock price drops below the 200-day moving average and the RSI falls below 30, sell to close the position.”_

When using a signal-based closing strategy, investors need to be aware that not all signals guarantee profitability. The effectiveness of each signal depends on various factors and requires the investor to have in-depth market knowledge.

# 4\. Time-Based Position Closing Strategy

The time-based position-closing strategy involves setting a maximum holding period for a position in advance. When this time period expires, the position is closed, regardless of the market price at that time.

_Example 04: An investor buys a VN30F1M futures contract with the goal of intraday trading and wants to avoid holding positions overnight to mitigate off-hours risks. The investor may set the closing time to 14:00 PM on the same day, regardless of whether the trade is profitable or not._

Determining the optimal closing time can be challenging and requires experience and market understanding, as well as the investor’s ability to analyze and manage risk.

****

In addition to the 04 popular position-closing strategies mentioned above, there are many variations depending on the algorithmic trader's needs. These variations can include combinations of the 04 strategies. For instance, in a smart beta strategy, position closing combines time and signal factors. The investor periodically reviews the portfolio at specific intervals. However, instead of closing all positions, they only sell stocks that no longer meet the predefined criteria.

In summary, in algorithmic trading, determining the position-opening strategy is just the beginning. The success of an algorithm depends not only on the ability to predict market trends accurately but also on risk management and profit optimization after opening positions. Here, the position-closing strategy plays a crucial role, helping traders actively manage risk and maximize profits. The principle of _“cut losses quickly, let profits run”_ is often applied to minimize losses and maximize gains when possible, thus providing overall effectiveness and sustainability for the algorithm.

---


## Hedging in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/hedging-in-algorithmic-trading/*

# What Is Hedging?

Hedging is an act of risk management deployed to mitigate losses in some instruments by opening the opposite position in a related asset. Hedging is often involved in futures contracts in the context of the Vietnam stock market as the only instrument that allows investors to open short positions. Practically, hedging is a low-risk low-return strategy, in which the act of hedging will reduce the risk of losses but also limit potential gains. Hedging is vastly different from the concept of reversing position to get a huge pay off if the anticipation turns out to be right. 

Full hedging is the concept of neutralizing an entire investment portfolio in order to achieve a system beta close to zero. For example, if VN30F1M current price is 1300 and the equity portfolio of an investor is value at 10B then to full hedge the system, an investor needs to short the following number of contracts: 

10.000.000.000 / (1300*(100.000)) = 77 contracts

Partial hedging is the concept of neutralizing a part of a portfolio to reduce the overall system beta, but not necessarily all the way to zero. 

# Why Hedging?

Sometimes, the risk and reward skewness can become tricky, and the risk factor is looming bigger in the whole picture. In such moments, traders may find that risk management becomes a much higher priority than potential returns. This is when a decision to hedge can be made. Though it is very hard to predict the future, certain events, such as market crashes, shifts in the economic cycle, or significant geopolitical and macroeconomic events, may indicate the need to prioritize safety over profits. Hedging then emerges as a strategy to navigate through uncertainties. 

# Why Hedging Instead of Selling the Current Position?

First, the cost incurred in closing current positions outside of the pre-programming algorithm will be huge. It includes transaction cost, slippage cost, restarting cost. Restarting cost is the cost involved when traders decide to stop hedging.

Second, hedging using derivatives instruments will be much more reliable and faster. In the Vietnam derivatives market, liquidation is good and default leverage is usually very high, guaranteeing quick execution in any cases. For example, to liquidate a portfolio of 100 Billions in the Vietnam stock market at current price may need 9 trading days for a hedge fund manager. In the case of using derivatives, this can be done in 2 minutes to achieve the same effect with much less slippage cost. 

Third, hedging can be automated while selling current position is interfering with the current live running system and much harder to automate. A short position in an independent algorithm is very easy to deploy and maintain in the long run while selling a part of the current portfolio outside of a pre-programming system is a very troublesome task with the same reward. Also, data integrity will hold in the former case but not the latter case.

# Recommend Approach to Apply Hedging

Algorithmic traders may need to recall that risk factors will never disappear. In fact, risk may be the origin of exceeding profits in comparison with non-risk financial instruments. Thus, in some perceptions, risk is not necessarily bad but vice versa. The concept here is which risk an algorithmic trader should take and which to avoid. Following is the recommended systematic approach to apply hedging in an algorithmic trading system.

First, algorithmic traders need to assess what type of risk there is in the current market. Is there a possibility that the market may drive the entire system toward a crash? For a positive beta system, there are many risks that algorithmic traders need to consider including geopolitical risk, foreign exchange risk, inflation risk, global recession risk, major war risk, margin call risk, and critical bankruptcy risk. In normal time, these risks are neglectable but when the risk is no longer small, protective measures, such as hedging, may be necessary. 

In case when hedging is necessary, algorithmic traders need to quantify system beta in each market scenario in normal cases. Then, the desired system beta in each market scenario needs to be formed. The difference in beta in both cases is the amount of hedging that needed. 

Opening short positions to hedge a full system beta is a critical step. And, closing those short positions strategy is also vital. When will traders need to close these hedging positions to operate normally? When will the hedging stop in the case of guessing right, wrong or nothing really happens? Traders must have a clear plan for the end of hedging before starting. 

Finally, it’s advisable to use a semi-automated hedging algorithm. In other cases, manual intervention with the system has to occur. At that point, once again, the system cannot operate smoothly and also the effect of hedging will be very difficult to evaluate afterwards.

In summary, hedging presents significant challenges due to the difficulty in accurately quantifying risks in a dynamic market with limited critical data. However, the potential reward lies in achieving a sustainable, long-term system - one that may be worth mastering.

---


## Variations of Statistical Arbitrage

*Fonte: https://hub.algotrade.vn/knowledge-hub/variations-of-statistical-arbitrage/*

Statistical arbitrage is a powerful trading strategy. It capitalizes on temporary price discrepancies in financial markets. Traders and investors employ historical data and sophisticated statistical models to identify pairs of securities exhibiting mean-reverting relationships. This data-driven approach enhances liquidity but requires careful risk management. In practice, statistical arbitrage plays a pivotal role in large hedge funds, particularly those focusing on quantitative strategies. Many of these funds develop strategies that rely on statistical analysis and algorithmic trading. Statistical arbitrage is indeed a core component with many different variations, allowing them to exploit short-term inefficiencies in a variety of markets.

# Arbitrage Concept in Finance

Pure arbitrage exploits price differences for the exact same asset across different markets to capture risk-free profits. In essence, arbitrage entails capitalizing on price variations for the same asset, security, or commodity across multiple financial markets or locations. The following criteria are its basic elements.

**Simultaneous transactions.** An arbitrageur buys an asset in one market and simultaneously sells it in another market at a higher price. The objective is to profit from these temporary price disparities.

**Market inefficiencies.** Arbitrage arises from market inefficiencies, resulting in price disparities. When arbitrageurs exploit these discrepancies, they make a profit while helping bring markets closer to efficiency.

**Asset types.** Arbitrage, though applicable to various asset types, is most prevalent in liquid markets. These include commodity futures, large-cap stocks, and major currencies in forex markets. Notably, these assets can often be traded across multiple markets at the same time.

**Risk-free profit.** Arbitrage theoretically offers a risk-free profit opportunity for traders. However, in today’s markets, hidden costs and price slippage can complicate profiting from pricing errors, making it more challenging for the pure algorithm to work.

# Quantitative Trading and Statistical Arbitrage

Advanced technology and the use of computers in trading have made it increasingly difficult to find pure arbitrage opportunities. It’s because automated trading systems can swiftly exploit inefficient pricing setups, often within seconds. However, in the computer age, a new form of arbitrage has emerged: statistical arbitrage. This advanced approach leverages statistical models, historical data, and quantitative analysis to make profits.

In the mid-1980s, Nunzio Tartaglia, a Wall Street quant, led a team of physicists, mathematicians, and computer scientists at Morgan Stanley. Their mission was to explore arbitrage opportunities in equity markets using advanced statistical techniques. The team developed high-tech trading programs, executable through automated systems, to replace intuition and guesswork with disciplined and consistent trading rules. This effort marked the beginning of a new form of arbitrage.

**Early days.** Pairs trading was one of their groundbreaking strategies. They identified securities with correlation and cointegration to exploit price movements between them. This approach remains an important technique used by hedge funds today. In pairs trading, the system monitors two historically correlated securities. When the correlation weakens temporarily (one security rises while the other falls), the strategy includes shorting the outperforming security (betting it will decline) and going long on the underperforming one (betting it will rise). The objective is to profit from the eventual convergence of the spread between the two stocks.

To predict the spread time series (which represents price disparities), traders utilize various techniques like Ornstein-Uhlenbeck models, autoregressive moving average (ARIMA) models, and error correction models. The ability to forecast the spread series assists in estimating potential returns and evaluating the risks associated with the pairs.

**Prominence.** Statistical arbitrage started to gain attention in the 1990s due to Long-Term Capital Management (LTCM), a hedge fund founded in 1994 by Nobel laureates Myron Scholes and Robert C. Merton. LTCM used mathematical models to detect arbitrage opportunities, including pairs trading, convergence trades, and relative value arbitrage, which were central to their portfolio construction.

At first, LTCM achieved impressive profits, attracting significant capital investment. However, in 1998, a sequence of market shocks, such as the Russian debt default and the East Asian market collapse, led to LTCM’s downfall. The hedge fund’s positions incurred severe losses, prompting the Federal Reserve to intervene with a bailout to prevent a broader financial crisis.

**Modern days.** LTCM’s failure emphasized the critical role of risk management in statistical arbitrage, particularly in leveraged positions. It highlighted the need to consider extreme black swan events. While LTCM’s story had a dramatic ending, its impact on quantitative finance endured. Despite its downfall, statistical arbitrage continued to evolve and thrive in other hedge funds, expanding to more asset classes. It has also become a prominent investment strategy within investment banks. Technological advancements in computational modeling facilitated the application of statistical arbitrage in high-frequency trading. Recently, renewed interest in statistical arbitrage has emerged in areas such as cryptocurrencies and factor investing.

# Variations of Statistical Arbitrage

The Morgan Stanley team pioneered statistical arbitrage in the 1980s partly out of hedging demands. When the trading desk purchased a large block of shares in one company, they would short a closely-correlated stock from another company to hedge against major market downturns in the short term.

In later years, traders began to think of these pairs further than a hedging tool. They developed pair trading into more sophisticated strategies. These strategies aimed to capitalize on statistical disparities in asset prices, influenced by factors such as liquidity, volatility, and other fundamental and technical considerations. Pair trading involves betting that price disparities will eventually revert back to their mean.

Over time, quantitative traders started to expand statistical arbitrage into different markets and different variations. These adaptations below can extend beyond underlying stocks to other asset classes like bonds, derivatives, and commodities.

**Basket trading.** This variation involves creating a portfolio of multiple securities (a basket), and trading it against another basket or a benchmark index. These assets can be stocks, ETFs, or other financial instruments. The basket typically includes securities from the same sector, or with some common theme (e.g. technology, consumer products, or export-related). This strategy aims to capture small price discrepancies across a diversified set of assets.

**Index arbitrage.** This variation aims to profit from price differences between two or more market indices, or between a market index and its components. For example, index arbitrage exploits discrepancies between the market price of a product that tracks an index (e.g. a stock market index future or an ETF), and the market prices of the underlying index components (typically individual stocks). Traders buy the relatively lower-priced securities, and sell the higher-priced securities, expecting the two prices to eventually become equal again. Index arbitrage is at the heart of algorithmic trading, where computers monitor millisecond changes between securities and automatically execute buy/sell orders to exploit market inefficiencies. Large financial institutions often employ this arbitrage because opportunities are razor-thin and short-lived. Its role is to keep markets synchronized and closer to price efficiency.

**Cross-asset arbitrage.** This variation capitalizes on price discrepancies between related assets across asset classes. It involves comparing prices across different types of assets, such as stocks, bonds, commodities, currencies, and derivatives. For example, if a stock and a bond issued by the same company show inconsistent pricing, a quantitative trader might exploit this discrepancy. Another example is if gold futures are overpriced relative to gold mining stocks, a trader might short the futures and go long on the mining stocks. In practice, large funds often look out for different asset classes, including foreign currency, commodities (e.g. crude oil and gasoline), even equity/option arbitrage. Cross-asset arbitrage is often complex. It requires domain expertise, real-time monitoring, and quick execution.

# Conclusion

In summary, statistical arbitrage continues to evolve, integrating algorithmic trading, data science, and market insights to capture short-lived profits. Originating 40 years ago from hedging requirements, statistical arbitrage now finds its reach into more asset classes and broader financial markets. However, this form of arbitrage can be intricate and risky due to varying market conditions and correlations. Quantitative traders must carefully manage risk, leverage, and timing factors to enter their positions. Recent advancements in artificial intelligence likely give more variations of statistical arbitrage, as computers can process large amounts of trading data within milliseconds to identify potential profit opportunities.

---


## Optimal Position Sizing Strategy in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/optimal-position-sizing-strategy-in-algorithmic-trading/*

Position sizing refers to the number of shares, contracts, or units of an asset that an investor decides to buy or sell in a specific trade when a position opening signal is triggered. In other words, it is the amount of capital that an investor is willing to risk on a trade based on their strategy and risk tolerance level.

An optimal position sizing strategy is a crucial component of algorithmic trading, addressing questions such as:

  * When a position opening signal is triggered, how much capital should be allocated? More specifically, should the entire capital be invested in a single trade, or should it be divided into several portions to participate in multiple trades at different times when position opening signals occur?

  * If the capital is divided into several portions, what percentage of capital should be allocated to each trading signal?


When developing a trading algorithm, determining the optimal position sizing strategy and the asset allocation strategy are two inseparable components, both related to the management and utilization of capital. These strategies differ in terms of timing. The optimal position sizing strategy specifies how much capital is allocated to each trade at different times when position opening signals occur, while the asset allocation strategy determines the percentage of capital allocated to each type of security at a given position opening. 

The following is an example that distinguishes the optimal position sizing strategy and the asset allocation strategy.

An algorithmic trader has developed a set of criteria to evaluate the strength of stocks. With a capital of 100 million VND, the trader applies a strategy of gradually opening buy positions over 4 consecutive days, rather than investing the entire capital at once. Specifically, each day, 25 million VND (¼ of the total capital) is used to buy the 2 stocks rated strongest based on the established criteria, with each stock allocated 12.5 million VND.

The optimal position sizing strategy is clearly demonstrated by dividing the capital to open positions at four different points in time. The asset allocation strategy is reflected in how, at each position opening signal, the capital is equally allocated to two different stocks, following an equal weighting method.

# Why Divide Position Sizing?

Instead of investing 100% of the capital in a single trade, dividing position sizing offers the following benefits:

  * **Risk reduction.** Rather than committing all capital in a single trade, dividing the position size helps minimize potential losses if the trade is unsuccessful. This is especially important in highly volatile stock markets with many unpredictable factors. A series of consecutive losses could lead to “blowing up" the account if the position size is too large. Splitting the position helps to protect the investor’s capital and ensures that the investor can continue participating in the market.

  * **Leveraging the law of large numbers.** Dividing the position size indirectly increases the number of trades, thereby leveraging the law of large numbers. According to this principle, as the number of trades increases sufficiently, the actual average result will converge toward the theoretical average (expected) value. In other words, if a trading strategy has a higher probability of winning than losing, executing more trades increases the likelihood of achieving overall positive and more stable profits in the long term.

  * **Adapting to market liquidity conditions.** In practice, there aren't always numerous opportunities to open positions at ideal prices. In markets with relatively low trading liquidity compared to the capital size, the trading algorithm needs to adapt flexibly by using a small portion of the capital to open a position and then continue to wait for the next position opening signals.


In summary, the strategy of dividing position size not only helps minimize risk and optimize profits but also provides flexibility in capital management for trading algorithms, especially in volatile markets or when there are fewer attractive trading opportunities.

# Optimal Position Sizing Strategies

Below are some popular optimal position sizing strategies:

  * **Fixed-volume position sizing.** Buy or sell a fixed number of shares or contracts for each position opening signal, regardless of price or market conditions.

  * **Percentage-of-capital position sizing.** Allocate a fixed percentage of total capital for each position opening signal.

  * **Signal confidence-based position sizing.** Adjust the position size based on the confidence level or probability of success of each trading signal. The idea behind this strategy is to invest more in trades with a higher likelihood of profitability and less in trades with higher risk. An example of this approach is the Kelly Criterion. This mathematical formula calculates the optimal position size based on the probability of winning and the ratio between the average profits when winning and the average loss when losing. For more information on the Kelly Criterion, refer to the article: [Kelly Criterion - Definition and Application](../../../../../../knowledge-hub/kelly-criterion-definition-and-application/).


There is no single optimal position sizing strategy that is perfect and suitable for everyone. Traders need to experiment, evaluate, and continuously adjust to find the optimal position sizing strategy. Combining theoretical knowledge, practical experience, and flexibility in application will help traders achieve success in the highly volatile financial markets.

# Conclusion

Position sizing plays a crucial role in algorithmic trading. Choosing the appropriate optimal position sizing strategy requires not only an understanding of fundamental principles like the law of large numbers but also careful consideration of trading style, risk tolerance, and the unique characteristics of each investment strategy.

Finally, it is important to note that position sizing is just one component of a complete trading algorithm. To achieve success in algorithmic trading, traders need to develop a comprehensive process that includes other key elements such as stock selection strategy, determination of entry/exit points, and execution strategy.

---


## What Algorithmic Trading Can and Cannot Offer for a Typical Hedge Fund

*Fonte: https://hub.algotrade.vn/knowledge-hub/what-algorithmic-trading-can-and-cant-offer-for-a-typical-hedge-fund/*

It had always been a misconception, especially for hedge funds in Vietnam, to equate algorithmic trading with superior return. In fact, this is not true. In finance, if it is not about return then what is it about? This article aims to make it clear what benefits algorithmic trading offers to institutional investors in their own perspective as well as the domain that algorithmic trading can’t offer.

# What Algorithmic Trading Can Offer

  1. **Cost optimization.** This should be the first sure thing after one firm successfully transitions to algorithmic trading. With a fully automated system, any task that is repetitive will be automated. Some standard tasks such as order execution, portfolio management, reporting and account management can be fully automated in any firm. Also, by deploying [execution algorithms](../../../../knowledge-hub/transaction-cost-reduction-execution-strategy/), hedge funds may reduce the cost when trading in large volumes. In some special cases such as passive funds, a full system can be automated with [execution algorithms](../../../../knowledge-hub/transaction-cost-reduction-execution-strategy/) to optimize the management cost at an average of 0.12% in the US in comparison to more than 1% in the Vietnam market. That is a ten-fold difference. Hence, there is a vast opportunity for hedge funds to optimize cost to increase competency in the financial market. 

  2. **Improve Stability.** Without emotion, a computerized system will not misbehave in 99.99% of cases that will absolutely enhance system stability. It is common sense that the more people involved, the more complex the system, the easier it is to have some problems elsewhere. To some extent, especially in the finance industry, where information is vital, it will be very costly to control internal risk. Thus, an automated system will reduce those risks and improve stability. 

  3. **Access To New Research Domain.** There are some approaches that only automated systems can explore based on their speed and consistency such as:


  * [Market-Making](../../../../knowledge-hub/market-making-strategy/): Require thousands of orders daily with heavy calculation. That should exceed the capacity of any individual.

  * [Scalping](../../../../knowledge-hub/scalping-strategy/): Calculate the chance of winning every new tick which means approximately 30 complex calculations in each minute.

  * [Market Neutral](../../../../knowledge-hub/market-neutral-strategy/): Calculate every new tick and simultaneously open positions in different financial instructions when receiving signals. 


Thus, algorithmic trading does offer access to new research domains that a merely “talented” human can’t do. 

# What Algorithmic Trading Can’t Offer

  1. **Guarantee superior return.** Algorithmic trading can provide certain advantages, but it does not guarantee superior returns. Algorithmic trading is in essence an automated system with predefined rules after a very thoroughly backtesting process. Algorithmic traders always try to improve the confidence level of an algorithm before going to production. Even working in such an attitude, the financial landscape will always change and many of the factors which have high impact will never be under control of an algorithm. Such factors can be named such as: geopolitical, war, pandemic, natural disaster. Thus, a guaranteed superior return may not hold true, especially for large firms. 

  2. **Macro trend.** This task is highly sensitive within the industry and requires in-depth knowledge of macroeconomic structures in relation to geopolitical developments. Analyzing macro numbers is possible for algorithmic trading although combining this information with the movement of geopolitics is not in the scope of algorithmic trading. 

  3. **Collect unique information.** Collecting non-standard and non-public data that will likely have a strong impact on the market is a domain beyond the reach of algorithmic trading. This unique competitive edge depends on industry experts with a lot of close connections. In the Vietnam stock market, which is a frontier market as of 2024, the more unique information one hedge fund manager has, the better chance of staying competitive in the market. 


**  
**In conclusion, algorithmic trading does offer some important advantages for a typical hedge fund but it is not a magical tool for superior return. Also, it is not capable of accomplishing some important tasks that only humans can achieve. To adopt algorithmic trading, the one strategy that aligns the most between the two domains is high latency predefined rules algorithms such as[smart beta strategy](../../../../knowledge-hub/smart-beta-strategies/).

---


## Implementation Challenges of Market Neutral Strategies

*Fonte: https://hub.algotrade.vn/knowledge-hub/implementation-challenges-of-market-neutral-strategies/*

Market neutral strategies have emerged as an advanced method in the investment world, driven by quantitative investing and algorithmic trading systems. These strategies aim to deliver returns regardless of market direction. However, they are quite intricate, involving a variety of complex techniques and considerations for managers. This article explores the risks, rewards, and layers of implementation complexity that defines the world of market neutral investing.

# Understanding Market Neutral Strategies

Market neutral strategies seek to generate returns by taking advantage of pricing inefficiencies between related securities while maintaining zero net-market exposure. This is usually accomplished through a combination of long and short positions, aiming to profit regardless of whether the overall market moves up or down.

With traditional investing such as smart-beta strategies, the main concern is whether the securities are going up or down in absolute terms. Market neutral portfolios on the other hand are designed to perform independently of broad market trends.

Hedge funds often use market neutral strategies because they prioritize absolute returns over relative returns (i.e., returns compared to an index benchmark). They make focused bets on pricing discrepancies to achieve a zero beta relative to a broad market index, thereby hedging out systematic risks.

In practice, there are two main types of market neutral strategies: fundamental arbitrage and statistical arbitrage. Fundamental market-neutral investors rely on fundamental analysis, rather than algorithms, to forecast a company’s future and execute trades. In contrast, statistical arbitrage primarily uses algorithms and quantitative methods to identify price discrepancies based on historical data and make trades.

# Potential Rewards

Market neutral strategies offer key potential rewards compared to traditional investing like long-only approaches as follows.

**Reduced market risk.** By balancing long and short positions, the strategies aim to maintain zero net market exposure, minimizing market risk. This approach ensures that the portfolio’s performance is less affected by market fluctuations, offering a degree of protection against market volatility.

**Consistent returns.** Market neutral strategies can provide the potential for more consistent returns, as they are driven by the performance differentials between long and short positions. This means investors can potentially achieve positive returns even in bearish or sideways markets, making these strategies particularly attractive during times of market uncertainty.

**Capitalizing on market inefficiencies.** These strategies are designed to capitalize on price inefficiencies and asset mispricings that may exist only in milliseconds. By carefully selecting securities to go long and short, investors can take advantage of valuation discrepancies, allowing for the potential to generate alpha independent of overall market movements.

**Diversification benefits.** Market neutral strategies offer diversification benefits due to their low correlation with broad market indices, providing a unique return stream. This diversification enhances the overall risk and return profile of an algorithmic trading system, resulting in a smoother investment experience.

**Adaptability.** These strategies are highly adaptable, allowing flexibility in asset selection, asset weights, and algorithmic implementation. Investors can apply market neutral strategies across various asset classes, such as equities, bonds, and derivatives. Systematic processes further improve the effectiveness of these strategies by enabling detailed investment analysis.

**Alpha generation.** This is the key benefit of market neutral strategies, which focus on security selection and relative performance to potentially achieve excess return. This is highly valuable in periods where traditional sources of return with high market exposure may be less reliable. Skilled managers can use their expertise to identify and exploit opportunities that may not be available in a long-only investment context.

# Potential Risks

Although market neutral strategies are attractive for the ability to exploit pricing inefficiencies, they carry several potential risks that investors should be aware of.

**Model risk.** Market neutral strategies often depend on intricate quantitative models and algorithmic backtesting. If these models are inaccurate or based on faulty historical data and assumptions, they can result in significant losses. This risk is particularly high in volatile markets where historical patterns may no longer hold.

**Execution risk.** The effectiveness of market neutral strategies relies on precise execution of trades by an automated trading system. Delays, slippage, and errors in trade execution can reduce the anticipated profits. This risk is especially prevalent in high-frequency trading environments, where market neutral strategies are commonly used.

**Liquidity risk.** Market neutral strategies may involve trading in less liquid assets. During periods of market stress, liquidity can dry up, making it challenging to exit positions without significantly affecting prices. This can result in larger-than-expected losses.

**Limited upside potential.** While these strategies aim to reduce downside risk, they also typically offer limited upside potential. Returns are generally lower compared to strategies that take on more market exposure, which can be a drawback in strong bull markets where traditional strategies might outperform.

**Performance issues.** The performance of market neutral strategies can be inconsistent. Factors such as changes in market conditions and regulations can affect their effectiveness. Investors may experience periods of underperformance, which can be frustrating.

# Implementation Challenges

Since market neutral strategies generate returns by iteratively balancing long and short positions, their implementation often presents considerable challenges for an algorithmic trading system.

**Data management.** Successfully implementing market neutral strategies requires access to extensive, high-quality data, often at a granular or even at tick level. This data includes price information, financial statements, and real-time bid-ask information of many assets. Managing and processing this big data to extract actionable insights and identify asset correlations is a key challenge.

**Precision.** The effectiveness of market neutral strategies relies on the accurate execution of automated trading systems. This approach reduces slippage, controls transaction costs, and ensures prompt order execution. High-frequency trading environments, where these strategies are frequently applied, require advanced computer infrastructure and algorithms.

**Risk management.** Managing risks in market neutral strategies is complex due to the need to balance long and short positions. This process involves continuous monitoring, configuration, and adjustment to achieve zero beta. Many hedge funds employ leverage in these strategies, requiring careful leverage management. Additionally, maintaining sufficient liquidity to enter or exit positions is essential to prevent substantial losses.

**Regulatory compliance.** Market neutral strategies must comply with various regulatory requirements, which differ by jurisdiction. This encompasses reporting duties, limitations on derivatives trading, and other regulatory constraints. Staying compliant requires a deep understanding of the regulatory landscape.

**Technology and infrastructure.** Implementing market neutral strategies demands significant investment in technology and infrastructure. This includes high-speed algorithmic trading systems, data analytics platforms, and risk management tools. Continuously maintaining and upgrading this infrastructure to keep up with technology advancements of the stock market is an ongoing challenge.

**Human expertise.** Despite the reliance on quantitative models and technology, human expertise remains critical. Skilled quantitative analysts and quantitative traders are crucial to design, implement, monitor, and configure market neutral strategies.

# Conclusion

Hedge funds and quantitative firms often use market neutral strategies with advanced automated trading systems. These strategies provide an alternative to traditional long-only approaches for generating profits in the stock market. Despite their potential benefits and risks, implementing these strategies is highly complex, necessitating sophisticated models, robust data management, precise execution, and effective risk management. The challenges involved in developing, executing, and overseeing these strategies demand significant human expertise and resources.

---


## After The 9 Steps

*Fonte: https://hub.algotrade.vn/knowledge-hub/after-the-9-steps/*

[The 9 Steps to Develop Algorithms](../../../../knowledge-hub/steps-to-develop-a-trading-algorithm/) is mandatory to achieve the first live algorithm. Soon after, there will be a need to improve a system with multiple live algorithms. The following are the next 6 advanced steps that algorithmic traders may consider to develop after “The 9 Steps”, making a total of 15 Steps to elevate the trading system to a new level.

# 1\. Monitoring System 

System monitoring may not be vital for a single algorithm system with minimal daily orders like smart beta strategy. Though, in the context of complex portfolios and high frequency trading, algorithmic traders will absolutely lose track of the current status of the portfolio without an internal monitoring system. For instance, a pair trading strategy that opens and closes hundreds of positions every day is surely cannot be monitored by common sense. 

In addition to tracking portfolios and orders, a monitoring system can assist algorithmic traders monitoring in other important aspects including:

  * Live_run bugs 

  * Price hub

  * Network latency

  * System speed


Thus, a monitoring system may be the very next step after an algorithmic trader had successfully achieved the first live run algorithm.

# 2\. Live Configuration 

It is quite common that an algorithm may need to be improvised some key parameters through time or allowing experts to interfere at some point in time especially with semi-automated trading algorithms. Without an upgrade, any change of parameter may need to stop the live running code, change the parameter then start it all over again. 

This method does work though it brings along a lot of downside effects. First, the system had to be stopped for any change of parameter. This will reduce the efficiency of the system. Also, it affects data integrity if the stop frequency is high enough. Second, errors in the adjustment process will become much more likely since it is direct code adjusting which is counter-productive in terms of system development. Not to mention, critical errors will likely happen sooner or later because to be human is to err. Third, it will make the system extremely hard to collaborate since the code is not a stable version and any adjustment will always need someone who is familiar with the code base. 

To solve this issue, a live configuration feature such as a website needs to be deployed. This feature will not only solve all the downside risks but also enhance flexibility of the system. 

# 3\. Multi-Algo Optimization 

This topic had been describe thoroughly in 3 following topics:

  * [Capital Optimization](../../../../knowledge-hub/capital-optimization-on-multi-algorithms-system/)

  * [Beta Optimization](../../../../knowledge-hub/beta-optimization-on-multi-algorithms-system/)

  * [Leverage Transaction Data](../../../../knowledge-hub/leverage-transaction-data/)


# 4\. Speed Optimization

For some algorithms, the better the speed, the better the efficiency. There are many part to optimize speed of an algorithm including:

  * [Choice of data source](../../../../knowledge-hub/procedure-to-seek-the-fastest-data-source-in-the-vietnam-stock-market/)

  * Choice of network

  * Choice of data storage

  * Choice of data processing

  * Choice of brokerage’s API


For an algorithmic trading firm, any choice should be made carefully based on data because measuring speed in milliseconds is not a technical challenge anymore. In the Vietnam stock market, an optimal choice may not hold for long, thus regular evaluation is a good practice. 

# 5\. Risk Control

In the development process, there will always be errors. This should be aware as a must not a probability. Errors may come in many forms such as: internal system errors, third party errors, data errors, or human errors. Many errors may happen only in extreme conditions that pass all the test cases. Thus, identifying these errors to minimize risk may be the first thought though it is almost impossible to prevent all of them as the system architecture may never prevent some things that have never happened before.   
  
A risk control system is a recommended approach to identify potential error signals then actively freeze the system until the issue is verified and resolved. At Algotrade, there are 3 layers of risk control: semi-auto risk control, automatic algorithmic risk control and full system risk control. 

# 6\. Disaster Recovery

No matter how robust a system is, a black swan event will eventually occur at the most unexpected moment. Without a disaster recovery system, everything will become so fragile at the point of crisis. Operations may shut down completely, code may be lost, data might be encryted. Resolving such issues could take months. Therefore, implementing a disaster recovery system with following key features is highly recommended:

  * At a different location with the current operation server.

  * Automation update data from the code base.

  * Prevent overwriting on core system code base (anti ransomware).

  * Fast deployment time (less than 24 hours) for production after disaster.


Disaster recovery systems should be invested for sustainable growth of the algorithmic trading system. The ideal scenario is, of course, it will never need to be used.

****

At Algotrade, we believe that after implementing all 15 steps in live operations, we have achieved our first stable system. We hope that our tacit knowledge may be beneficial for others pursuing a similar path.

---


## Risk Management in Algorithmic Trading

*Fonte: https://hub.algotrade.vn/knowledge-hub/risk-management-in-algorithmic-trading/*

Algorithmic trading leverages computer algorithms to execute trades at high speed and in large volumes. It also carries out various trading strategies, including high-frequency trading and other approaches derived from backtesting historical data. Widely adopted by quantitative hedge funds, algorithmic trading provides significant advantages, such as enhanced efficiency and lower transaction costs. However, it also presents distinct risks for traders and quantitative investors. Recognizing these risks and implementing effective risk management are crucial to mitigate them and maintain the stability and profitability of trading strategies.

# Risk Management Strategies

Effective risk management is fundamental to the success of algorithmic trading. By implementing robust risk management strategies, algorithmic traders can safeguard their investments, reduce potential losses, and improve the overall performance of their trading algorithms. Below are some essential risk management strategies for algorithmic traders.

**Diversification.** Diversifying both trading strategies and assets is a key risk management approach. It’s important not to allocate the majority of your capital into a single algorithm. Likewise, diversifying across different asset classes is essential. By distributing investments among various instruments and strategies, you can mitigate the impact of losses in one area with gains in another, thereby reducing overall risk.

**Risk limits.** Setting stringent risk limits of each algorithm and the total capital is essential. This involves determining maximum allowable losses, position sizes, and leverage levels. By establishing these boundaries, traders can avoid excessive risk-taking that might result in significant, unrecoverable losses.

**Advanced monitoring.** Continuous real-time monitoring of all algorithms is crucial for identifying and addressing any anomalies or unforeseen market conditions. This requires the use of sophisticated monitoring tools and dashboards to keep track of performance metrics like returns and drawdowns. The primary goal is to ensure that all algorithms operate as expected.

**Stress testing.** Conducting regular stress tests on live-run trading algorithms helps identify potential weaknesses under extreme market conditions. By simulating different market scenarios, traders can evaluate the performance of their algorithms and make necessary adjustments to enhance their resilience.

**Position sizing.** Utilizing dynamic position sizing techniques enables traders to modify their positions according to market conditions and their risk tolerance. This approach helps optimize the risk-reward ratio and ensures that no single trade can disproportionately affect the entire portfolio.

**Stop-loss orders.** Employing stop-loss orders is a widely used risk management technique to limit potential losses. These orders automatically liquidate a position once it hits a predetermined loss threshold, thereby preventing additional losses during volatile market conditions.

**Technical risk management.** Technical risks, including system failure, data inaccuracies, and programming errors, can result in substantial trading mistakes. To mitigate these risks, traders should conduct regular maintenance, checks, and updates on their trading systems. Additionally, having contingency plans and a backup system in place is crucial.

**Market risk management.** Market risks arise from unforeseen events, price fluctuations, and volatility. Traders can mitigate these risks by employing account hedging and using dynamic stop-loss and take-profit levels. Additionally, AI-powered modules that track fundamental developments can assist in swiftly responding to market changes.

**Operational risk management.** Operational risks encompass regulatory compliance and market liquidity challenges. To mitigate these risks, it’s essential to establish robust governance frameworks, conduct regular audits, and perform compliance checks. Furthermore, implementing stringent cybersecurity measures is crucial for safeguarding trading systems.

# Risk Management Practices

In organizations such as hedge funds, the use of algorithmic trading introduces significant scale and complexity in risk management, necessitating robust practices. These practices are essential to protect against losses and ensure adherence to regulatory requirements. Here are some risk management strategies commonly employed by quantitative funds utilizing algorithmic trading.

**Establish a risk management framework.** A comprehensive risk management framework should be developed, detailing the policies, procedures, and tools for managing risks. Given that quantitative hedge funds rely on mathematical models and algorithms for investment decisions, this framework needs to be frequently reviewed and updated to adapt to evolving market conditions and incorporate new quantitative risk measurements.

**Implement robust governance structures.** Effective governance structures, such as risk committees and independent risk officers, can significantly improve risk oversight and ensure accountability within the fund. Strong governance practices are essential to maintain confidence and upholding the integrity of the fund’s operations.

**Leverage technology.** Investing in robust technology and infrastructure is essential for effective risk management in hedge funds. This involves deploying advanced data management systems to guarantee the accuracy and timeliness of data used in risk analysis. Moreover, utilizing automation and artificial intelligence can greatly improve risk modeling and predictive analytics, enabling more precise and proactive risk management.

**Integration with investment strategy.** Ensures that risk considerations are not an afterthought but a core component of decision-making. This alignment helps in setting clear objectives where both risk managers and portfolio managers work collaboratively to balance potential returns with acceptable risk levels. By promoting a culture of open communication and shared goals, hedge funds can make more informed investment decisions that consider both opportunities and risks, ultimately resulting in more stable and sustainable performance.

# Conclusion

Effective risk management is crucial for the sustainability of algorithmic trading. By applying strategies to control the risks associated with trading algorithms, traders can reduce potential losses and improve their overall trading performance. As the market rapidly evolves, staying updated and continuously refining risk management practices will be vital for achieving sustained success in algorithmic trading.

---


## Basic Assumptions and Market Evolution

*Fonte: https://hub.algotrade.vn/knowledge-hub/basic-assumptions-and-market-evolution/*

Many of the algorithm being used to predict future price of a financial instrument such as: simple statistics, linear regression, time series, reinforcement learning, sentiment, machine learning and artificial intelligence contain four basic assumptions: 

# The Four Basic Assumptions

  1. I**ndependent and identically distributed data (IID) data.** This essentially means that you assume that there is some true but unknown data distribution from which each of your training and test points are drawn independently.

  2. **The true function mapping inputs to outputs is smooth almost everywhere.** Essentially, you assume that there is some true but unknown function that maps the inputs to the outputs. The goal is to approximate this true function, so that when given a new input, you can use this function to predict the output. You expect the predicted output to be reasonable because hopefully the model has seen similar inputs in training data, and the function can approximate the output by combining the information from those training data points. If the true function is smooth, this works. If not, then looking at similar inputs in training data tell you very little about this new data point.

  3. **Signal to noise ratio is large.** The noise in input features and labels is assumed to be low.

  4. **Unmodelled features have negligible effects.** You represent any input as a set of features, e.g., a price and volume as past performance metrics. Now, of course, there are other variables in the environment that you ignore in the process. If the other parameters accounted for more than 80% of the effect, then there will be no true model.


# Do These Assumptions Hold True in Algorithmic Trading?

  1. **Independent and identically distributed data (IID) data.** This is the same as past performance indicates future performance which should not be true in the financial market. Perhaps, there are some traits in the data set that are identical but for the whole data set in the financial market to be identical distributed in the past as well as the future seems very unlikely. 

  2. **The true function mapping inputs to outputs is smooth almost everywhere.** This is the same way to say there is a true holy grail in the financial market which can predict the outcomes in the future with 100% accuracy. If this assumption holds true then there will be an absolute winner. By empirical evidence of no huge successful big firm with more than 1000% return annually and Warren Buffet with 23% annually return still the most admired investor, we may think that there is no such true function. 

  3. **Signal to noise ratio is large.** It may be the opposite in financial data, in which the majority of data is noise or randomness. 

  4. **Unmodelled features have negligible effects.** It is very well known that stock market is the leading indicator of the social economy, and the social is under effect of a lot of unknown and unexpected features such as natural disaster, pandemic, war. 


This discussion, even not yet sophisticated proven, may give a hunch that the approach in the algorithmic trading industry should not be identical as some clear rules game like chess. 

Applying these thought models, one may come up with the current status of the algorithmic industry, using statistics for finding features that long lasting in the future to achieve superior return after utilizing the law of large numbers. In case of alpha decay, with or without reasoning, the solution is to find another alpha to maintain the trading system performance. 

This approach, which has been applied by many well known quantitative trading firms, signals it is good enough to survive the test of time. To further improve our thought model, we may take a look at the idea of market evolution. 

# Market Evolution

Market, as an entity, combines many factors. Some have a huge impact on market movement, while others have minimal impact. By quantifying any amount of impactful factors, algorithmic traders may find a good model such as smart beta strategy. Or, by naturalizing a lot of factors to reduce noise, also help enhance model accuracy even with weak prediction factors such as market neutral strategy. Or, focusing on a time frame that most factors cannot affect the market to reduce noise and increase accuracy such as scalping trading strategy.

Regardless of the approach, the market will change as its core pillar changes overtime. Some core pillars in each market may be named as: cooperation aggregation, regulation, environment and human nature. 

Once a significant change is made or a combination of small changes is too impactful, a market may reach a tipping point and transform itself into a new state. We may call it market evolution.  
  
Market evolution is an event that shifts the market nature permanently from state A to state B and redefines a set of impactful factors in the process.  
  
When market evolution happens, factors that impact the market will change accordingly. Some that are very impactful may no longer hold prediction value. 

The dilemma is, in light of simplicity, regardless of what change in the nature of the market, it represents no changes in terms of price and volume as hundreds of years. To cut it straight, the market has evolved to a completely new state and without notice, algorithmic traders will leverage obsolete models. This should not result in anything but randomness. 

So the point here, the market does evolve. And once it does, there is no way back just like the nature of evolution. 

# Question Regarding Market Evolution?

At Algotrade, we are trying to embrace and nurture the ideas though the result is still very vague. Following is a list of questions we are trying to solve.

  * Which factor will mark the market evolution? Is it a new law, a pandemic or any tech disruption can make it happen?

  * How long does it take to transition completely from the old state to the new one?

  * Does previous data have less value after market evolution?

  * After the market evolution, there is little to no data in the new state, how can we build models with very minimal data? 

  * Can social prediction models be employed in the financial market? 


We are still at the very beginning of discovering this track. We found the topic of complex systems may aid. Here is the resource if you want to tag along: https://www.santafe.edu/

---


# GLOSSARY


## Glossary of Terms

*Fonte: https://hub.algotrade.vn/glossary/*

#### A

##### Algorithm hypothesis (for a trading system)

An assumption with a solid financial foundation that may yield long-term profits. Algorithm hypotheses require a thorough analysis of historical data.

##### Algorithm trading

The practice of using a computer system to carry out fully automated trades according to pre-programmed algorithms.

##### Algorithmic trader

An investor or trader that uses an algorithmic trading system.

##### Algorithmic trading system

An automated system with data collection processes and data queries. The system uses computer algorithms to make trading decisions and reports, to manage real-time financial portfolios without any human intervention.

##### API (application programming interface)

A set of definitions and protocols that allow communication between two software applications.

##### Arbitrage trading strategy

A strategy to take advantage of temporary price differences for the same asset in two different markets. This trading strategy makes profits without much risk.

#### B

##### Backtesting

The use of past data to evaluate an algorithm’s performance.

#### E

##### Event-driven trading strategy

A trading strategy that takes advantage of market inefficiencies from corporate events like mergers and acquisitions, corporate restructures, share buybacks, extraordinary dividends, etc. to trade in the short term.

#### F

##### Forward testing

The use of future data from the present to a certain point in the future to evaluate an algorithm’s performance.

##### Front-running ETF strategy

Investors anticipate the action of exchange-traded funds (ETFs) according to the public prospectus and simulate part of the action prior to the fund’s rebalancing.

##### Future data

Unseen data from the market used for testing.

#### G

##### Grid trading strategy

A strategy that sets up a price grid around a predefined value to make profits from market fluctuations independent of market trends.

#### H

##### High-frequency trading

An algorithmic trading strategy with an extremely large number of transactions at high speed. It opens and closes positions in a very short period of time.

#### I

##### Implementation shortfall

A discrepancy between paper profits and actual profits. Paper profit is a theoretical profit under the assumption all orders are executed at the desired price and volume without any fees.

##### In-sample historical data

The past historical data used to train and optimize trading algorithms.

##### Indicator

A signal to determine the ticker symbol and the appropriate time to trade. Indicators are divided into technical indicators such as MA, and RSI, and base indicators such as PE, and ROE. Depending on the algorithms, an indicator can be custom defined based on its intended use.

#### K

##### Kelly criterion

Determines the optimal capital per trade to maximize the long-term performance of a trading algorithm.

#### M

##### Market neutral strategy

A group of strategies when investors open both long and short positions to minimize the effects of market risk on portfolio profitability.

##### Market-making strategy

A strategy of simultaneously placing orders at the best bid price and the best ask price. This strategy makes profits from the bid-ask spread.

##### Maximum drawdown (MDD)

The maximum loss from the peak to the bottom for an asset or portfolio.

##### Mean reversion strategy

A strategy to buy stocks when the price is lower than their intrinsic or average value; and vice versa sell when the price is higher.

##### Momentum trading strategy

Investors buy rising stocks in terms of price (or short-sell falling stocks) with the reasoning that stocks will follow their momentum trends in price.

#### O

##### Optimization

A process of finding the values of parameters for a trading algorithm to produce the best performance in the target market.

##### Out-of-sample historical data

The past historical data used to validate trading algorithms after the training phase. It is to assess the profitability of an algorithm in the future. In-sample and out-of-sample historical data do not have any overlap.

##### Overfitting

The phenomenon that the post-optimization algorithm gives good results on in-sample historical data but performs poorly on unseen out-of-sample data.

#### P

##### Pair trading

A strategy that finds two stocks with high correlation to match a long position with a short position. When their correlation deviates above the long-term average, investors match a long position on the underperforming stock, and a short position on the outperforming stock, expecting the deviation to be temporary. When the price correlation converges to the average, the investor closes the position to realize the profit.

##### Paper testing

A stage in testing future data. It uses real-time data in a simulated trading environment to evaluate an algorithm’s performance.

##### Parameter (algorithm)

A predefined arithmetic value like price, volume, or parametric constants of mathematical models.

##### POV algorithm

Breaks down the order with volume based on the percentage of volume according to the market liquidity. As the market trading volume increases, it will trade more stocks and vice versa.

#### S

##### Scalping strategy

A special strategy that focuses on an ultra-short time frame to open and close positions in order to make very small profits.

##### Semi-automated trading

A system that uses computers combined with human intervention to optimize the decision-making process.

##### Sharpe ratio

The rate of expected return minus the risk-free rate, divided by the standard deviation of the rate of return. It measures the expected performance per unit of risk.

##### Smart-beta strategy

Also known as a factor-based strategy, a strategy to build portfolios according to rule-based processes. It uses business factors like liquidity, value, and quality as criteria for making trading decisions.

##### Statistical arbitrage strategy

A group of market-neutral strategies developed from the pair trading strategy. It uses statistical mathematical models with computer systems to identify trading opportunities. They are mostly from unusual relative price changes from one stock compared to another.

#### T

##### Trading algorithm

A set of statements and trading logic to execute trading decisions, including but not limited to buy or sell orders and price, volume, and order types. Within the scope of our book, “algorithms” without further explanation can be understood as “trading algorithms”.

##### Trading logic

A rule-based system used to make trading decisions based on indicators and parameters.

##### TWAP (time-weighted average price)

**** The equally weighted average price of all orders made during the execution period.

##### TWAP algorithm

Breaks down the order into equal parts and consistently places orders, separated by an equal amount of time.

#### V

##### VWAP (volume-weighted average price)

The weighted average price by the volume of all orders made during the execution period.

##### VWAP algorithm

Breaks down and places orders at different times and different volumes based on historical data of trading volume.

---
