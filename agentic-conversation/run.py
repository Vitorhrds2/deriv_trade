#!/usr/bin/env python3
"""Entry point da ponte Devin <-> Telegram. Veja README.md."""
import logging

from devin_telegram.bot import Bot
from devin_telegram.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

if __name__ == "__main__":
    Bot(Config.from_env()).run()
