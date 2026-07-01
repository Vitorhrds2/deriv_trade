import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [MEGA_BRAIN] %(levelname)s: %(message)s',
    handlers=[logging.FileHandler('mega_brain_orchestrator.log', mode='a', encoding='utf-8'),
              logging.StreamHandler()]
)
logger = logging.getLogger("MEGA_BRAIN")

CONFIG_FILE = "hypothesis_configs.json"

async def read_stream(stream, prefix):
    """Lê a saída do subprocesso e repassa para o logger principal com um prefixo."""
    while True:
        line = await stream.readline()
        if not line:
            break
        text = line.decode().strip()
        if text:
            # Simplificando a exibição no logger central
            print(f"{prefix} | {text}", flush=True)

async def run_hypothesis(hypo_id, script_name):
    """Inicia um subprocesso para o script da hipótese."""
    logger.info(f"🚀 Iniciando hipótese: {hypo_id} ({script_name})")
    
    script_path = Path(script_name)
    if not script_path.exists():
        logger.error(f"❌ Script não encontrado: {script_name} para {hypo_id}")
        return

    process = await asyncio.create_subprocess_exec(
        sys.executable, script_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    # Monitora stdout e stderr
    await asyncio.gather(
        read_stream(process.stdout, f"[{hypo_id}] INFO"),
        read_stream(process.stderr, f"[{hypo_id}] ERR")
    )
    
    await process.wait()
    logger.warning(f"🛑 Hipótese finalizada: {hypo_id} (Exit Code: {process.returncode})")

async def main():
    logger.info("🧠 Mega Brain Orchestrator Iniciado!")
    
    if not Path(CONFIG_FILE).exists():
        logger.error(f"Arquivo {CONFIG_FILE} não encontrado!")
        return

    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)

    global_settings = config.get("global_settings", {})
    demo_mode = global_settings.get("demo_mode", True)
    logger.info(f"⚙️ Modo Global: {'DEMO' if demo_mode else 'REAL'}")

    hypotheses = config.get("hypotheses", [])
    tasks = []

    for hypo in hypotheses:
        if hypo.get("enabled"):
            h_id = hypo["id"]
            script = hypo["script"]
            # Set environment variables for the subprocess to know it's managed
            os.environ[f"{h_id}_PARAMS"] = json.dumps(hypo.get("params", {}))
            os.environ["MEGA_BRAIN_DEMO"] = "1" if demo_mode else "0"
            
            task = asyncio.create_task(run_hypothesis(h_id, script))
            tasks.append(task)
        else:
            logger.info(f"⏸️ Hipótese ignorada (Desabilitada): {hypo.get('id')}")

    if not tasks:
        logger.info("Nenhuma hipótese habilitada para execução.")
        return

    # Mantém o orquestrador rodando enquanto os subprocessos estiverem ativos
    await asyncio.gather(*tasks)
    logger.info("🏁 Todas as hipóteses foram concluídas.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupção manual. Encerrando Mega Brain...")
