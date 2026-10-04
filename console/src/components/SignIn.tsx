import { useEffect, useState } from "react";
import { ApiError, api } from "../api/client";
import type { DemoUser, Principal } from "../api/types";
import { initials } from "../format";
import { Brand } from "./Shell";

interface SignInProps {
  onSignedIn: (user: Principal, demo: DemoUser[]) => void;
}

export function SignIn({ onSignedIn }: SignInProps) {
  const [users, setUsers] = useState<DemoUser[]>([]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    // The worker may still be starting when the page opens; keep trying for a while before giving up.
    const load = (tries: number) => {
      api
        .demoUsers()
        .then((list) => {
          if (cancelled) return;
          setUsers(list);
          setError(list.length ? null : "The sandbox has no accounts. Run make reset-demo, then reload.");
          if (list[0]) setEmail(list[0].email);
          setLoading(false);
        })
        .catch((e: unknown) => {
          if (cancelled) return;
          if (e instanceof ApiError && e.status === 0 && tries < 15) {
            timer = window.setTimeout(() => load(tries + 1), 2000);
            return;
          }
          setError(e instanceof ApiError ? e.message : "Can't load the sandbox accounts.");
          setLoading(false);
        });
    };
    setLoading(true);
    setError(null);
    load(0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [attempt]);

  const picked = users.find((u) => u.email === email);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await api.signIn(email, password);
      onSignedIn(user, users);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sign-in failed. Try again.");
      setBusy(false);
    }
  }

  return (
    <main className="signin">
      <div className="signin-wrap">
        <section className="signin-copy">
          <Brand />
          <div className="stack" style={{ gap: 14 }}>
            <h1>Ask for an outcome. It works in the browser, then proves it.</h1>
            <p>
              The worker reads the supplier portal, enters records in the internal register, and only says done after reading the
              result back.
            </p>
          </div>
          <ul className="promises">
            <li><strong>Acts as you.</strong> Your permissions in the register apply to every action it takes.</li>
            <li><strong>Asks first.</strong> Large amounts and changes to existing records wait for your approval.</li>
            <li><strong>Shows its work.</strong> Every result lists the checks it passed and where each value came from.</li>
          </ul>
        </section>

        <form className="sheet signin-card" onSubmit={submit} aria-labelledby="signin-h">
          <div className="stack" style={{ gap: 4 }}>
            <h2 id="signin-h" style={{ fontSize: 17 }}>Sign in</h2>
            <p className="muted" style={{ fontSize: 13 }}>Sandbox accounts. Each one is allowed to change different suppliers.</p>
          </div>
          {loading && <p className="muted" role="status" style={{ fontSize: 13 }}>Loading sandbox accounts… If the worker is still starting, this keeps trying.</p>}
          {!loading && users.length === 0 && (
            <button type="button" className="btn" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
          )}
          <fieldset className="accounts">
            <legend className="sr-only">Account</legend>
            {users.map((u) => (
              <label key={u.email} className="account">
                <input type="radio" name="account" value={u.email} checked={email === u.email} onChange={() => setEmail(u.email)} />
                <span className={`avatar${u.role === "admin" ? " admin" : ""}`} aria-hidden="true">{initials(u.display_name)}</span>
                <span>
                  <span className="account-name">{u.display_name}</span>{" "}
                  <span className="role-tag">{u.role === "admin" ? "Admin" : "Operator"}</span>
                  <div className="account-scope">
                    {u.role === "admin" ? "All suppliers, and can change policy" : u.assigned_suppliers.join(", ") || "No suppliers assigned"}
                  </div>
                </span>
              </label>
            ))}
          </fieldset>
          <input type="text" name="username" autoComplete="username" value={email} readOnly hidden />
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
            {picked && <span className="muted" style={{ fontSize: 12 }}>{picked.password_hint}</span>}
          </div>
          {error && <p className="error-text" role="alert">{error}</p>}
          <button type="submit" className="btn btn-primary btn-lg" disabled={busy || !email}>
            {busy ? "Signing in…" : `Sign in as ${picked?.display_name.split(" ")[0] ?? "…"}`}
          </button>
        </form>
      </div>
    </main>
  );
}
