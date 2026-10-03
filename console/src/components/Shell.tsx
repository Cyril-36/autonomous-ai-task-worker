import type { Budget, Principal } from "../api/types";
import { formatInr, initials } from "../format";

function Mark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
        <path d="M3 5h12M3 9h12M3 13h7" stroke="#EAF3EC" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </span>
  );
}

export function Brand() {
  return (
    <a className="brand" href="#/">
      <Mark />
      <span>
        <div className="brand-name">Task Worker</div>
        <div className="brand-sub">Halden Traders sandbox</div>
      </span>
    </a>
  );
}

function BudgetMeter({ budget }: { budget: Budget }) {
  const spent = Number(budget.global_spent_inr);
  const limit = Number(budget.global_limit_inr) || 1;
  const pct = Math.min(100, Math.round((spent / limit) * 100));
  return (
    <div className="meter" title="Estimated from token counts; the provider's bill is the final figure.">
      <div className="meter-row">
        <span>Estimated model spend</span>
        <strong>
          {formatInr(budget.global_spent_inr)} of {formatInr(budget.global_limit_inr)}
        </strong>
      </div>
      <div className="meter-track" role="meter" aria-valuemin={0} aria-valuemax={limit} aria-valuenow={spent} aria-label="Estimated model spend">
        <div className={`meter-fill${pct >= 80 ? " near" : ""}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

interface TopBarProps {
  user: Principal;
  scope: string;
  budget: Budget | null;
  onSignOut: () => void;
}

export function TopBar({ user, scope, budget, onSignOut }: TopBarProps) {
  return (
    <header className="topbar">
      <Brand />
      <div className="topbar-right">
        {budget && <BudgetMeter budget={budget} />}
        <div className="who">
          <span className={`avatar${user.role === "admin" ? " admin" : ""}`} aria-hidden="true">{initials(user.display_name)}</span>
          <span>
            <div className="who-name">{user.display_name}</div>
            <div className="who-scope">{scope}</div>
          </span>
          <button type="button" className="btn btn-quiet" onClick={onSignOut}>Sign out</button>
        </div>
      </div>
    </header>
  );
}
