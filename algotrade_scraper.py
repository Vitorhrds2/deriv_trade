#!/usr/bin/env python3
"""
Algotrade Knowledge Hub – Full Scraper
======================================
Scrapes todos os artigos do hub e compila num único arquivo Markdown.
Opcionalmente converte para PDF.

Instalação:
    pip install requests beautifulsoup4 html2text
    pip install markdown weasyprint   # somente se quiser PDF

Uso:
    python algotrade_scraper.py                  # gera só o .md
    python algotrade_scraper.py --pdf            # gera .md e .pdf
    python algotrade_scraper.py --delay 2.0      # delay maior entre requests
    python algotrade_scraper.py --resume         # pula páginas já salvas em cache
"""

import requests
from bs4 import BeautifulSoup, NavigableString
import html2text
import time
import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# CONFIGURAÇÃO
# ─────────────────────────────────────────────

BASE_URL = "https://hub.algotrade.vn"
CACHE_DIR = Path(".algotrade_cache")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ─────────────────────────────────────────────
# MAPA COMPLETO DE CONTEÚDO (64 artigos + outros + glossário)
# Extraído da navegação HTML do site
# ─────────────────────────────────────────────

SECTIONS = [
    {
        "title": "I. OVERVIEW",
        "articles": [
            ("/knowledge-hub/algorithmic-trading-overview/",
             "01. Introduction to Algorithmic Trading"),
            ("/knowledge-hub/advantages-of-algorithmic-trading/",
             "02. Advantages of Algorithmic Trading"),
            ("/knowledge-hub/critical-risks-on-algorithmic-trading-system/",
             "03. Algorithmic Trading Risks"),
            ("/knowledge-hub/what-you-need-to-build-an-algorithmic-trading-system/",
             "04. Core Components to Build an Algorithmic Trading System"),
            ("/knowledge-hub/semi-automated-trading/",
             "05. Semi-Automated Trading"),
            ("/knowledge-hub/steps-to-develop-a-trading-algorithm/",
             "06. 09 Steps to Develop Algorithms"),
        ],
    },
    {
        "title": "II. PROPOSE AN ALGORITHM HYPOTHESIS",
        "articles": [
            ("/knowledge-hub/distinguish-two-algorithmic-trading-categories/",
             "07. Distinction between Two Types of Algorithms"),
            ("/knowledge-hub/transaction-cost-reduction-execution-strategy/",
             "08. Execution Algorithms to Optimize Trading Fees"),
            ("/knowledge-hub/elements-of-a-complete-algorithmic-trading-strategy/",
             "09. 06 Components to Build a Complete Trading Algorithm"),
            ("/knowledge-hub/key-differences-between-algorithmic-trading-in-equity-market-and-derivatives-market-in-vietnam/",
             "10. Differences Between Equity and Derivative Trading"),
            ("/knowledge-hub/guide-to-formulate-an-algorithm-hypothesis/",
             "11. How to Construct an Algorithm Hypothesis"),
            ("/knowledge-hub/algorithmic-trading-strategies/",
             "12. Trading Strategy Overview"),
            ("/knowledge-hub/market-neutral-strategy/",
             "13. Market-Neutral Strategy"),
            ("/knowledge-hub/momentum-strategy/",
             "14. Price Momentum Strategy"),
            ("/knowledge-hub/mean-reversion-strategy/",
             "15. Mean-Reversion Strategy"),
            ("/knowledge-hub/event-driven-strategy/",
             "16. Event-Driven Strategy"),
            ("/knowledge-hub/market-making-strategy/",
             "17. Market-Making Strategy"),
            ("/knowledge-hub/scalping-strategy/",
             "18. Scalping Strategy"),
            ("/knowledge-hub/front-running-etf-strategy/",
             "19. ETF Front-Runner Strategy"),
            ("/knowledge-hub/arbitrage-strategy/",
             "20. Arbitrage Strategy"),
            ("/knowledge-hub/grid-strategy/",
             "21. Grid Strategy"),
            ("/knowledge-hub/smart-beta-strategies/",
             "22. Smart-Beta Strategy"),
            ("/knowledge-hub/sniffing-strategy/",
             "23. Sniffing Strategy"),
            ("/knowledge-hub/advanced-algorithmic-trading-strategies/",
             "24. High-Tech Algorithmic Trading"),
            ("/knowledge-hub/behavioral-finance-and-its-application-in-algorithmic-hypothesis-formation/",
             "25. Behavioral Finance in Algorithmic Hypothesis Formation"),
        ],
    },
    {
        "title": "III. DATA",
        "articles": [
            ("/knowledge-hub/standard-data-in-algorithmic-trading/",
             "26. Standard Data in Algorithmic Trading"),
            ("/knowledge-hub/data-cleaning-tutorial/",
             "27. Data Cleaning Tutorial"),
            ("/knowledge-hub/data-management-in-algorithmic-trading/",
             "28. Data Management in Algorithmic Trading"),
            ("/knowledge-hub/api-in-vietnam-stock-market/",
             "29. Stock Trading API in Vietnam Market"),
            ("/knowledge-hub/procedure-to-seek-the-fastest-data-source-in-the-vietnam-stock-market/",
             "30. Search Process for Fastest Data Source"),
        ],
    },
    {
        "title": "IV. BACKTESTING",
        "articles": [
            ("/knowledge-hub/philosophical-background-on-algorithm-backtesting/",
             "31. Philosophical Foundations of Backtesting"),
            ("/knowledge-hub/critical-errors-on-backtesting-stage/",
             "32. Critical Mistakes in Backtesting"),
            ("/knowledge-hub/specialized-backtesting-module-benefits-and-development/",
             "33. Backtesting Module"),
        ],
    },
    {
        "title": "V. OPTIMIZATION",
        "articles": [
            ("/knowledge-hub/optimizing-trading-algorithms/",
             "34. Optimizing Trading Algorithms"),
            ("/knowledge-hub/techniques-to-avoid-overfitting/",
             "35. Techniques to Avoid Overfitting"),
            ("/knowledge-hub/post-optimization-assessment/",
             "36. Post-optimization Assessment"),
        ],
    },
    {
        "title": "VI. FORWARD TESTING",
        "articles": [
            ("/knowledge-hub/significance-of-forward-testing/",
             "37. Meaning of Forward Testing"),
            ("/knowledge-hub/paper-trading/",
             "38. Paper Trading"),
            ("/knowledge-hub/small-account-test/",
             "39. Small Account Test"),
        ],
    },
    {
        "title": "VII. REAL TRADING",
        "articles": [
            ("/knowledge-hub/algorithm-in-real-environment/",
             "40. Algorithm in Real Environment"),
            ("/knowledge-hub/use-twap-and-wwap-benchmarks-to-evaluate-trade-execution/",
             "41. Evaluation of Execution Algorithms With TWAP and VWAP"),
            ("/knowledge-hub/measuring-implementation-shortfall/",
             "42. Measuring Implementation Shortfall"),
        ],
    },
    {
        "title": "VIII. EVALUATION CRITERIA FOR ALGORITHMS",
        "articles": [
            ("/knowledge-hub/evaluation-of-algorithmic-performance/",
             "43. Return Rate"),
            ("/knowledge-hub/maximum-drawdown-in-algorithmic-trading/",
             "44. Maximum Drawdown in Algorithmic Trading"),
            ("/knowledge-hub/kelly-criterion-definition-and-application/",
             "45. Kelly Criterion – Definition and Application"),
        ],
    },
    {
        "title": "IX. OPTIMIZATION IN MULTI-ALGORITHM TRADING",
        "articles": [
            ("/knowledge-hub/capital-optimization-on-multi-algorithms-system/",
             "46. Capital Optimization on Multi-Algorithms System"),
            ("/knowledge-hub/beta-optimization-on-multi-algorithms-system/",
             "47. Beta Optimization"),
            ("/knowledge-hub/leverage-transaction-data/",
             "48. Leverage Transaction Data"),
        ],
    },
    {
        "title": "X. ALGORITHMIC TRADING PRACTICE",
        "articles": [
            ("/knowledge-hub/models-or-randomness/",
             "49. Models or Randomness"),
            ("/knowledge-hub/is-algorithmic-trading-a-zero-sum-game/",
             "50. Is Algorithmic Trading a Zero-Sum Game"),
            ("/knowledge-hub/what-to-do-when-second-guessing-your-algorithm/",
             "51. What to Do When in Doubt of Your Trading Algorithm"),
            ("/knowledge-hub/scams-in-algorithmic-trading-07-major-characteristics/",
             "52. Scams in Algorithmic Trading: 07 Major Characteristics"),
            ("/knowledge-hub/third-party-software-in-algorithmic-trading/",
             "53. Third-Party Software in Algorithmic Trading"),
            ("/knowledge-hub/is-algorithmic-trading-appropriate-for-all-investors/",
             "54. Is Algorithmic Trading Preferable for All Traders"),
            ("/knowledge-hub/how-to-become-an-algorithmic-trader/",
             "55. How to Become an Algorithmic Trader"),
            ("/knowledge-hub/how-to-learn-programming-skills-to-do-algorithmic-trading/",
             "56. How to Learn Programming Skills for Algorithmic Trading"),
        ],
    },
    {
        "title": "XI. INTEL CENTER – SUPPORT CHANNEL",
        "articles": [
            ("/knowledge-hub/intel-center-overview/",
             "57. Intel Center Overview"),
            ("/knowledge-hub/foreign-trading-data/",
             "58. Foreign Trading Data"),
            ("/knowledge-hub/daily-accumulative-foreign-trading-in-vn30/",
             "59. Daily Accumulative Foreign Trading Value in VN30"),
        ],
    },
    {
        "title": "XII. ALGOTRADE LAB – FIRST STEP TO ALGORITHMIC TRADING",
        "articles": [
            ("/knowledge-hub/algotrade-lab-overview/",
             "60. Algotrade Lab Overview"),
            ("/knowledge-hub/introduction-to-sma-algorithm/",
             "61. Introduction to SMA Algorithm"),
            ("/knowledge-hub/how-to-register-for-api-at-ssi-securities-jsc/",
             "62. How to Register for API at SSI Securities JSC"),
            ("/knowledge-hub/experience-algotrade-lab/",
             "63. Experience Algotrade Lab"),
            ("/knowledge-hub/configuration-experience-and-sma-algorithm-monitoring/",
             "64. SMA Algorithm Configuration and Monitoring Experience"),
        ],
    },
    {
        "title": "OTHER ARTICLES",
        "articles": [
            ("/knowledge-hub/sortino-ratio/", "Sortino Ratio"),
            ("/knowledge-hub/information-ratio/", "Information Ratio"),
            ("/knowledge-hub/fundamental-analysis-and-technical-analysis/",
             "Fundamental Analysis and Technical Analysis"),
            ("/knowledge-hub/smart-beta-backtesting-procedure/",
             "Smart Beta Backtesting Procedure"),
            ("/knowledge-hub/biases-in-algorithmic-trading/",
             "Biases in Algorithmic Trading"),
            ("/knowledge-hub/popular-technical-analysis-indicators/",
             "Popular Technical Analysis Indicators"),
            ("/knowledge-hub/stock-price-prediction-a-discipline-branch-within-social-science/",
             "Stock Price Prediction – A Discipline Branch Within Social Science"),
            ("/knowledge-hub/challenges-in-economic-forecasting/",
             "Challenges in Economic Forecasting"),
            ("/knowledge-hub/five-personal-factors-influencing-investment-strategy/",
             "Five Personal Factors Influencing Investment Strategy"),
            ("/knowledge-hub/feature-improvement-procedure-for-live-algorithms/",
             "Feature Improvement Procedure for Live Algorithms"),
            ("/knowledge-hub/overfitting-and-how-to-mitigate-it/",
             "Overfitting and How to Mitigate It"),
            ("/knowledge-hub/moving-average/", "Moving Average"),
            ("/knowledge-hub/expert-input-how-to-handle/",
             "How to Integrate Expert Input"),
            ("/knowledge-hub/intraday-algorithmic-trading/",
             "Intraday Algorithmic Trading"),
            ("/knowledge-hub/head-and-shoulders-pattern/",
             "Head and Shoulders Pattern"),
            ("/knowledge-hub/algorithmic-trading-quant-trading-and-high-frequency-trading/",
             "Algorithmic Trading, Quant Trading and High Frequency Trading"),
            ("/knowledge-hub/equity-segmentation/", "Equity Segmentation"),
            ("/knowledge-hub/weighting-methods-used-in-smart-beta-strategy/",
             "Weighting Methods Used in Smart-Beta Strategy"),
            ("/knowledge-hub/key-insights-from-career-development-of-quant-king-jim-simons/",
             "Key Insights From Career Development of Quant King Jim Simons"),
            ("/knowledge-hub/passive-active-and-quantitative-investment/",
             "Passive, Active, and Quantitative Investment"),
            ("/knowledge-hub/action-bias-in-algorithmic-trading/",
             "Action Bias in Algorithmic Trading"),
            ("/knowledge-hub/quantitative-hedge-funds-and-algorithms/",
             "Quantitative Hedge Funds and Algorithms"),
            ("/knowledge-hub/04-strategies-for-closing-positions-in-algorithmic-trading/",
             "04 Strategies for Closing Positions in Algorithmic Trading"),
            ("/knowledge-hub/hedging-in-algorithmic-trading/",
             "Hedging in Algorithmic Trading"),
            ("/knowledge-hub/variations-of-statistical-arbitrage/",
             "Variations of Statistical Arbitrage"),
            ("/knowledge-hub/optimal-position-sizing-strategy-in-algorithmic-trading/",
             "Optimal Position Sizing Strategy in Algorithmic Trading"),
            ("/knowledge-hub/what-algorithmic-trading-can-and-cant-offer-for-a-typical-hedge-fund/",
             "What Algorithmic Trading Can and Cannot Offer for a Typical Hedge Fund"),
            ("/knowledge-hub/implementation-challenges-of-market-neutral-strategies/",
             "Implementation Challenges of Market Neutral Strategies"),
            ("/knowledge-hub/after-the-9-steps/", "After The 9 Steps"),
            ("/knowledge-hub/risk-management-in-algorithmic-trading/",
             "Risk Management in Algorithmic Trading"),
            ("/knowledge-hub/basic-assumptions-and-market-evolution/",
             "Basic Assumptions and Market Evolution"),
        ],
    },
    {
        "title": "GLOSSARY",
        "articles": [
            ("/glossary/", "Glossary of Terms"),
        ],
    },
]

# ─────────────────────────────────────────────
# FUNÇÕES DE SCRAPING
# ─────────────────────────────────────────────

def log(msg, level="INFO"):
    icons = {"INFO": "ℹ", "OK": "✓", "WARN": "⚠", "ERR": "✗", "HEAD": "═"}
    print(f"  {icons.get(level, ' ')} {msg}")


def fetch_page(url: str, retries: int = 3, delay: float = 2.0) -> str | None:
    """Faz o download de uma página com retry automático."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            log(f"Tentativa {attempt}/{retries} falhou: {exc}", "WARN")
            if attempt < retries:
                time.sleep(delay * attempt)
    return None


def cache_path(path: str) -> Path:
    safe = path.strip("/").replace("/", "_") or "root"
    return CACHE_DIR / f"{safe}.html"


def load_cache(path: str) -> str | None:
    p = cache_path(path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return None


def save_cache(path: str, html: str):
    CACHE_DIR.mkdir(exist_ok=True)
    cache_path(path).write_text(html, encoding="utf-8")


# Seletores candidatos para o conteúdo principal, do mais específico ao mais genérico
CONTENT_SELECTORS = [
    "div.hub-article-content",
    "div.article-content",
    "div.knowledge-content",
    "div.post-content",
    "div.entry-content",
    "article",
    "main",
    "div#content",
    "div.content",
]

# Tags/classes a remover do conteúdo antes de converter
REMOVE_SELECTORS = [
    "nav", "header", "footer", "aside",
    ".nav", ".navbar", ".sidebar", ".breadcrumb",
    ".hub-menu", ".hub-nav", ".nav-accordion",
    ".share", ".social", ".comments", ".related",
    ".widget", ".ad", ".ads", ".advertisement",
    "script", "style", "noscript",
    "[class*='menu']", "[class*='footer']",
    "[class*='header']", "[id*='menu']",
]


def extract_article(html: str) -> tuple[str, str]:
    """
    Extrai (título, conteúdo_html) da página.
    Retorna strings vazias em caso de falha.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Título da página
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    elif soup.title:
        title = soup.title.get_text(strip=True)

    # Encontra o container de conteúdo
    content = None
    for sel in CONTENT_SELECTORS:
        content = soup.select_one(sel)
        if content and len(content.get_text(strip=True)) > 200:
            break

    if not content:
        content = soup.find("body")

    if not content:
        return title, ""

    # Remove elementos indesejados
    for sel in REMOVE_SELECTORS:
        for el in content.select(sel):
            el.decompose()

    # Remove elementos de nav por classe parcial
    for el in content.find_all(True):
        classes = " ".join(el.get("class", []))
        if any(kw in classes.lower() for kw in ("nav", "menu", "sidebar", "breadcrumb")):
            el.decompose()

    return title, str(content)


def html_to_md(html: str) -> str:
    """Converte HTML para Markdown limpo."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True       # omite imagens – foco no texto
    h.ignore_emphasis = False
    h.body_width = 0             # sem quebra de linha automática
    h.unicode_snob = True
    h.wrap_links = False
    h.protect_links = False
    md = h.handle(html)
    # Limpa linhas em branco excessivas
    import re
    md = re.sub(r"\n{4,}", "\n\n\n", md)
    return md.strip()


# ─────────────────────────────────────────────
# GERAÇÃO DE MARKDOWN
# ─────────────────────────────────────────────

def build_toc(sections: list) -> str:
    lines = ["# Sumário\n"]
    for sec in sections:
        lines.append(f"\n## {sec['title']}\n")
        for path, title in sec["articles"]:
            anchor = title.lower()
            for ch in " .–—-–'\",:;/()[]{}!?":
                anchor = anchor.replace(ch, "-")
            anchor = anchor.strip("-")
            import re
            anchor = re.sub(r"-+", "-", anchor)
            lines.append(f"- [{title}](#{anchor})")
    return "\n".join(lines)


def scrape_all(
    output_md: str = "algotrade_knowledge_hub.md",
    delay: float = 1.5,
    use_cache: bool = False,
) -> str:
    """Percorre todos os artigos, converte e grava no arquivo Markdown."""

    total = sum(len(s["articles"]) for s in SECTIONS)
    done = 0
    failed = []

    print(f"\n{'═'*60}")
    print(f"  Algotrade Knowledge Hub – Scraper")
    print(f"  Total de artigos: {total} | Destino: {output_md}")
    print(f"{'═'*60}\n")

    blocks = []

    # Cabeçalho do documento
    blocks.append(
        f"# Algotrade Knowledge Hub – Referência Completa\n\n"
        f"*Compilado em {datetime.now().strftime('%d/%m/%Y')} a partir de hub.algotrade.vn*\n\n"
        f"---\n"
    )
    blocks.append(build_toc(SECTIONS))
    blocks.append("\n---\n")

    for section in SECTIONS:
        sec_title = section["title"]
        print(f"\n{'─'*50}")
        print(f"  {sec_title}")
        print(f"{'─'*50}")
        blocks.append(f"\n# {sec_title}\n")

        for path, article_title in section["articles"]:
            done += 1
            url = BASE_URL + path
            print(f"\n[{done:>3}/{total}] {article_title}")
            log(url)

            # Tenta cache
            html = None
            if use_cache:
                html = load_cache(path)
                if html:
                    log("Carregado do cache", "OK")

            if not html:
                html = fetch_page(url, delay=delay)
                if html and use_cache:
                    save_cache(path, html)

            if not html:
                log("Falha – conteúdo não disponível", "ERR")
                failed.append((url, article_title))
                blocks.append(
                    f"\n## {article_title}\n\n"
                    f"*Fonte: {url}*\n\n"
                    f"> ⚠️ Não foi possível buscar este artigo.\n\n---\n"
                )
                continue

            _, content_html = extract_article(html)
            if not content_html:
                log("Conteúdo vazio após extração", "WARN")
                failed.append((url, article_title))

            md_body = html_to_md(content_html) if content_html else "*Sem conteúdo.*"
            char_count = len(md_body)
            log(f"{char_count:,} caracteres extraídos", "OK")

            blocks.append(
                f"\n## {article_title}\n\n"
                f"*Fonte: {url}*\n\n"
                f"{md_body}\n\n---\n"
            )

            time.sleep(delay)

    # Grava arquivo
    final_md = "\n".join(blocks)
    Path(output_md).write_text(final_md, encoding="utf-8")
    size_kb = Path(output_md).stat().st_size / 1024

    print(f"\n{'═'*60}")
    print(f"  CONCLUÍDO")
    print(f"  Artigos processados : {total}")
    print(f"  Com sucesso         : {total - len(failed)}")
    print(f"  Falhos              : {len(failed)}")
    print(f"  Arquivo             : {Path(output_md).resolve()}")
    print(f"  Tamanho             : {size_kb:.1f} KB")
    if failed:
        print(f"\n  Artigos com falha:")
        for url, t in failed:
            print(f"    ✗ {t}")
            print(f"      {url}")
    print(f"{'═'*60}\n")

    return output_md


# ─────────────────────────────────────────────
# CONVERSÃO PARA PDF
# ─────────────────────────────────────────────

PDF_CSS = """
@page {
    margin: 2.2cm 2cm;
    size: A4;
    @bottom-right {
        content: "Página " counter(page) " de " counter(pages);
        font-size: 8pt;
        color: #888;
    }
}

body {
    font-family: "Georgia", "Times New Roman", serif;
    font-size: 10.5pt;
    line-height: 1.7;
    color: #1a1a1a;
    background: white;
}

h1 {
    font-size: 22pt;
    font-family: Arial, Helvetica, sans-serif;
    color: #0d1b2a;
    page-break-before: always;
    border-bottom: 3px solid #1565c0;
    padding-bottom: 6px;
    margin-top: 0;
}

h1:first-of-type { page-break-before: avoid; }

h2 {
    font-size: 15pt;
    font-family: Arial, Helvetica, sans-serif;
    color: #1565c0;
    page-break-before: always;
    margin-top: 20px;
    padding-bottom: 4px;
    border-bottom: 1px solid #bbdefb;
}

h3 {
    font-size: 12pt;
    font-family: Arial, Helvetica, sans-serif;
    color: #1976d2;
}

h4, h5, h6 {
    font-family: Arial, Helvetica, sans-serif;
    color: #333;
}

p {
    text-align: justify;
    margin-bottom: 8px;
    orphans: 3;
    widows: 3;
}

a { color: #1565c0; text-decoration: none; }

em {
    color: #555;
    font-size: 9pt;
}

code {
    background: #f5f5f5;
    padding: 2px 5px;
    font-family: "Courier New", monospace;
    font-size: 9pt;
    border-radius: 3px;
}

pre {
    background: #f5f5f5;
    padding: 12px;
    font-family: "Courier New", monospace;
    font-size: 9pt;
    line-height: 1.4;
    page-break-inside: avoid;
    border-left: 3px solid #1565c0;
}

blockquote {
    border-left: 4px solid #bbdefb;
    padding-left: 12px;
    margin-left: 0;
    color: #555;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 9.5pt;
}

th {
    background: #1565c0;
    color: white;
    padding: 6px 8px;
    text-align: left;
}

td {
    border: 1px solid #ddd;
    padding: 6px 8px;
}

tr:nth-child(even) td { background: #f9f9f9; }

hr {
    border: none;
    border-top: 1px solid #e0e0e0;
    margin: 16px 0;
}

ul, ol {
    margin-bottom: 10px;
    padding-left: 20px;
}

li { margin-bottom: 4px; }
"""


def convert_to_pdf(md_file: str, pdf_file: str | None = None) -> str | None:
    """Converte o arquivo Markdown gerado para PDF usando WeasyPrint."""
    if pdf_file is None:
        pdf_file = md_file.replace(".md", ".pdf")

    try:
        import markdown as mdlib
        from weasyprint import HTML, CSS
    except ImportError:
        print(
            "\n⚠️  Pacotes necessários para PDF não encontrados.\n"
            "   Execute: pip install markdown weasyprint\n"
            "   O arquivo .md já está disponível.\n"
        )
        return None

    print(f"\n📄 Convertendo para PDF: {pdf_file}")
    print("   (pode demorar alguns minutos para documentos grandes…)")

    md_text = Path(md_file).read_text(encoding="utf-8")

    html_body = mdlib.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "nl2br", "sane_lists"],
    )

    full_html = (
        '<!DOCTYPE html><html><head>'
        '<meta charset="utf-8">'
        '<title>Algotrade Knowledge Hub</title>'
        '</head><body>'
        f'{html_body}'
        '</body></html>'
    )

    try:
        HTML(string=full_html).write_pdf(
            pdf_file,
            stylesheets=[CSS(string=PDF_CSS)],
        )
        size_mb = Path(pdf_file).stat().st_size / 1024 / 1024
        print(f"✓ PDF gerado: {Path(pdf_file).resolve()}")
        print(f"  Tamanho: {size_mb:.1f} MB")
        return pdf_file
    except Exception as exc:
        print(f"✗ Erro ao gerar PDF: {exc}")
        return None


# ─────────────────────────────────────────────
# PONTO DE ENTRADA
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Algotrade Knowledge Hub – Scraper para Markdown/PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", "-o",
        default="algotrade_knowledge_hub.md",
        help="Nome do arquivo Markdown de saída (default: algotrade_knowledge_hub.md)",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Também gera PDF (requer: pip install markdown weasyprint)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="Intervalo entre requisições em segundos (default: 1.5)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Usa cache local para não rebuscar páginas já baixadas",
    )
    args = parser.parse_args()

    md_file = scrape_all(
        output_md=args.output,
        delay=args.delay,
        use_cache=args.resume,
    )

    if args.pdf:
        convert_to_pdf(md_file)


if __name__ == "__main__":
    main()
