## 2026-11-10T02:02:19Z
You are teamwork_explorer_railway_survey_3.
Your working directory is /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_railway_survey_3/
You must read /Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
You have access to Railway tools and skills (`use-railway`).

Objective:
Investigate and design the production Railway deployment, latency comparison, and continuous operational setup for the Sui arbitrage bot.
Specifically:
1. Check existing Railway configuration, projects, or deployment setup in the repository (e.g. `railway.toml`, `Procfile`, `Dockerfile`, `requirements.txt`, etc.) and using Railway MCP tools (e.g. list-projects, whoami).
2. Compare latency and architecture between Frankfurt (`europe-west3`) and Oregon (`us-west1`) for Sui Mainnet RPC endpoints and nodes. Determine the optimal region recommendation.
3. Design the continuous deployment and execution model:
   - Service definition (Procfile / Dockerfile / nixpacks)
   - Auto-restart policies on crashes or network dropouts
   - Healthcheck endpoints / heartbeat logging
   - Structured JSON logging for spreads, opportunities, PTB dry-runs, and executed transactions
4. Design secure credentials injection:
   - Ensure private keys, mnemonics, and sensitive RPC URLs are ONLY supplied via Railway environment variables.
   - Zero credentials written to git, disk files, or debug logs.
5. Provide a step-by-step Railway provisioning and deployment plan.

Constraints:
- You are strictly READ-ONLY. DO NOT modify codebase files or provision resources yet (this is the survey phase).
- Deliver your detailed report in `analysis.md` and `handoff.md` in your working directory `/Users/vitorhrds/Documents/Github/hypothesis/.agents/teamwork/teamwork_explorer_railway_survey_3/`.
- Maintain heartbeat in `progress.md` with timestamps.
- When finished, send a brief completion message to your caller.
