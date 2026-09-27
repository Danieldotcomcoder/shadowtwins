import * as Dialog from "@radix-ui/react-dialog";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { getOperatorToken, setOperatorToken } from "../../api/client";
import { useMeta } from "../../api/hooks";

function OperatorDialog() {
  const meta = useMeta();
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [open, setOpen] = useState(false);
  const operator = meta.data?.auth?.operator === true;
  const mode = meta.data?.auth?.mode as string | undefined;
  const hasToken = !!getOperatorToken();
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button type="button" className={`badge ${operator ? "ok" : ""}`} style={{ cursor: "pointer" }}
          aria-label={operator ? "Operator access active" : "Viewer (read-only). Open operator access"}>
          {operator ? "● Operator" : "○ Viewer"}
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="overlay" />
        <Dialog.Content className="dialog">
          <Dialog.Title asChild><h2>Operator access</h2></Dialog.Title>
          <Dialog.Description className="small dim" style={{ marginTop: 6 }}>
            Anyone can browse results. Starting and controlling runs needs operator access. The server's
            OpenRouter key never reaches the browser. The operator token is a run-control password; once
            entered (or opened through a login link) it is remembered in this browser until you forget it.
          </Dialog.Description>
          <dl className="kv" style={{ marginTop: 14 }}>
            <dt>Server auth mode</dt><dd className="mono">{mode ?? "…"}</dd>
            <dt>This browser</dt><dd>{operator ? "Operator" : "Viewer"} — {String(meta.data?.auth?.reason ?? "")}</dd>
          </dl>
          {mode === "token" && (
            <form className="stack-s" style={{ marginTop: 16 }} onSubmit={(e) => {
              e.preventDefault();
              setOperatorToken(token.trim() || null);
              setToken("");
              qc.invalidateQueries({ queryKey: ["meta"] });
              setOpen(false);
            }}>
              <div className="field">
                <label htmlFor="op-token">Operator token</label>
                <input id="op-token" className="input" type="password" autoComplete="off" value={token}
                  onChange={(e) => setToken(e.target.value)} placeholder="ST_OPERATOR_TOKEN" />
              </div>
              <div className="row">
                <button className="btn primary" type="submit" disabled={!token.trim()}>Use token</button>
                {hasToken && (
                  <button className="btn ghost" type="button" onClick={() => {
                    setOperatorToken(null);
                    qc.invalidateQueries({ queryKey: ["meta"] });
                  }}>Forget token</button>
                )}
              </div>
            </form>
          )}
          {mode === "local" && !operator && (
            <p className="small dim" style={{ marginTop: 14 }}>
              This server only accepts run controls from its own machine. Open the app on the host, or restart the
              server with <code>ST_OPERATOR_TOKEN</code> set.
            </p>
          )}
          <div className="row" style={{ marginTop: 18, justifyContent: "flex-end" }}>
            <Dialog.Close asChild><button className="btn" type="button">Close</button></Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Logo() {
  return (
    <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden>
      <path d="M16 4 27 10v12L16 28 5 22V10z" fill="none" stroke="#7dd3c0" strokeWidth="1.8" />
      <path d="M16 16 27 10M16 16v12M16 16 5 10" stroke="#7dd3c0" strokeWidth="1.8" opacity=".5" />
      <path d="M16 4v6" stroke="#7dd3c0" strokeWidth="1.8" opacity=".3" />
    </svg>
  );
}

export function Shell() {
  const meta = useMeta();
  const mock = meta.data?.providers?.mock as { enabled?: boolean } | undefined;
  return (
    <div className="shell">
      <a href="#main" className="skip-link">Skip to content</a>
      <header className="topbar">
        <div className="topbar-inner">
          <NavLink to="/" className="brand" aria-label="Shadow Twins home">
            <Logo />
            <span>Shadow Twins <small>suite 1</small></span>
          </NavLink>
          <nav className="nav" aria-label="Main">
            <NavLink to="/" end>Evaluate</NavLink>
            <NavLink to="/runs">Runs</NavLink>
            <NavLink to="/leaderboard">Leaderboard</NavLink>
            <NavLink to="/practice">Practice</NavLink>
            <NavLink to="/about">Method</NavLink>
          </nav>
          <div className="topbar-right">
            {mock?.enabled && <span className="badge mock hide-sm" title="Mock provider enabled on this server">mock provider on</span>}
            <OperatorDialog />
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        <Outlet />
      </main>
      <footer className="footer">
        <div className="footer-inner">
          <span>Exact scoring · no LLM judges · certified optima</span>
          <span>{meta.data ? `${meta.data.api_version} · ${String(meta.data.suite.version)}` : ""}</span>
        </div>
      </footer>
    </div>
  );
}
