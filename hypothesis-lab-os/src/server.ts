import "./lib/error-capture";

import { consumeLastCapturedError } from "./lib/error-capture";
import { renderErrorPage } from "./lib/error-page";
import * as fs from "node:fs/promises";
import * as path from "node:path";

type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

let serverEntryPromise: Promise<ServerEntry> | undefined;

async function getServerEntry(): Promise<ServerEntry> {
  if (!serverEntryPromise) {
    serverEntryPromise = import("@tanstack/react-start/server-entry").then(
      (m) => ((m as { default?: ServerEntry }).default ?? (m as unknown as ServerEntry)),
    );
  }
  return serverEntryPromise;
}

function brandedErrorResponse(): Response {
  return new Response(renderErrorPage(), {
    status: 500,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function isCatastrophicSsrErrorBody(body: string, responseStatus: number): boolean {
  let payload: unknown;
  try {
    payload = JSON.parse(body);
  } catch {
    return false;
  }

  if (!payload || Array.isArray(payload) || typeof payload !== "object") {
    return false;
  }

  const fields = payload as Record<string, unknown>;
  const expectedKeys = new Set(["message", "status", "unhandled"]);
  if (!Object.keys(fields).every((key) => expectedKeys.has(key))) {
    return false;
  }

  return (
    fields.unhandled === true &&
    fields.message === "HTTPError" &&
    (fields.status === undefined || fields.status === responseStatus)
  );
}

// h3 swallows in-handler throws into a normal 500 Response with body
// {"unhandled":true,"message":"HTTPError"} — try/catch alone never fires for those.
async function normalizeCatastrophicSsrResponse(response: Response): Promise<Response> {
  if (response.status < 500) return response;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return response;

  const body = await response.clone().text();
  if (!isCatastrophicSsrErrorBody(body, response.status)) {
    return response;
  }

  console.error(consumeLastCapturedError() ?? new Error(`h3 swallowed SSR error: ${body}`));
  return brandedErrorResponse();
}

const TRADING_ENGINE_DIR = path.resolve(process.cwd(), "../trading-engine");

const SCOPE_FILES: Record<string, string[]> = {
  live: [
    "d107_rate_limit_winner_holding_results.jsonl",
    "d107_rate_limit_winner_holding_state.json",
    "market_regime_policy.json",
  ],
  r100_all: [
    "d107_results_r100_trade1.jsonl",
    "d107_state_r100_trade1.json",
    "d107_results_r100_session2_16trades.jsonl",
    "d107_state_r100_session2_16trades.json",
    "d107_results_r100_session3.jsonl",
    "d107_state_r100_session3.json",
    "d107_results_r100_session4_preupgrade.jsonl",
    "d107_state_r100_session4_preupgrade.json",
    "d107_rate_limit_winner_holding_results.jsonl",
    "d107_rate_limit_winner_holding_state.json",
    "market_regime_policy.json",
  ],
  global_all: [
    "d107_results_1hz100v_archive.jsonl",
    "d107_state_1hz100v_archive.json",
    "d107_results_r100_trade1.jsonl",
    "d107_state_r100_trade1.json",
    "d107_results_r100_session2_16trades.jsonl",
    "d107_state_r100_session2_16trades.json",
    "d107_results_r100_session3.jsonl",
    "d107_state_r100_session3.json",
    "d107_results_r100_session4_preupgrade.jsonl",
    "d107_state_r100_session4_preupgrade.json",
    "d107_rate_limit_winner_holding_results.jsonl",
    "d107_rate_limit_winner_holding_state.json",
    "market_regime_policy.json",
  ],
  r100_session4: [
    "d107_results_r100_session4_preupgrade.jsonl",
    "d107_state_r100_session4_preupgrade.json",
    "market_regime_policy.json",
  ],
  archive_1hz100v: [
    "d107_results_1hz100v_archive.jsonl",
    "d107_state_1hz100v_archive.json",
    "market_regime_policy.json",
  ],
};

async function handleD107FolderApi(url: URL): Promise<Response> {
  try {
    const scope = url.searchParams.get("scope") || "global_all";
    const targetFileNames = SCOPE_FILES[scope] ?? SCOPE_FILES.global_all;

    const dirEntries = await fs.readdir(TRADING_ENGINE_DIR).catch(() => [] as string[]);
    const availableD107Files: Array<{ name: string; size: number; mtime: string }> = [];

    for (const entry of dirEntries) {
      if (
        entry === "market_regime_policy.json" ||
        /^d107_(rate_limit_winner_holding_results\.jsonl|rate_limit_winner_holding_state\.json|results_.*\.jsonl|state_.*\.json)$/i.test(
          entry,
        )
      ) {
        try {
          const st = await fs.stat(path.join(TRADING_ENGINE_DIR, entry));
          availableD107Files.push({
            name: entry,
            size: st.size,
            mtime: st.mtime.toISOString(),
          });
        } catch {
          // ignore
        }
      }
    }

    const loadedFiles: Array<{ name: string; content: string; size: number; mtime: string }> = [];
    for (const fname of targetFileNames) {
      const fpath = path.join(TRADING_ENGINE_DIR, fname);
      try {
        const [content, st] = await Promise.all([
          fs.readFile(fpath, "utf-8"),
          fs.stat(fpath),
        ]);
        loadedFiles.push({
          name: fname,
          content,
          size: st.size,
          mtime: st.mtime.toISOString(),
        });
      } catch {
        // Skip missing file gracefully
      }
    }

    return new Response(
      JSON.stringify({
        ok: true,
        folderPath: TRADING_ENGINE_DIR,
        scope,
        fetchedAt: new Date().toISOString(),
        availableD107Files,
        files: loadedFiles,
      }),
      {
        status: 200,
        headers: {
          "content-type": "application/json; charset=utf-8",
          "cache-control": "no-store",
        },
      },
    );
  } catch (err) {
    return new Response(
      JSON.stringify({
        ok: false,
        error: err instanceof Error ? err.message : String(err),
      }),
      { status: 500, headers: { "content-type": "application/json; charset=utf-8" } },
    );
  }
}

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    try {
      const url = new URL(request.url);
      if (url.pathname === "/api/d107/folder") {
        return await handleD107FolderApi(url);
      }

      const handler = await getServerEntry();
      const response = await handler.fetch(request, env, ctx);
      return await normalizeCatastrophicSsrResponse(response);
    } catch (error) {
      console.error(error);
      return brandedErrorResponse();
    }
  },
};
