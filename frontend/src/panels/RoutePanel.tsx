import type { RouteLeg, RoutePlan, RouteResponse, ScenarioSummary } from '../types';

interface RoutePanelProps {
  origin: [number, number] | null;
  dest: [number, number] | null;
  scenarios: ScenarioSummary[];
  scenarioId: string;
  onScenarioChange: (id: string) => void;
  loading: boolean;
  error: string | null;
  result: RouteResponse | null;
  onReset: () => void;
}

function fmtMin(v: number): string {
  const rounded = Math.round(v * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function legLabel(leg: RouteLeg): string {
  switch (leg.type) {
    case 'walk':
      return `🚶 徒歩 ${leg.from_name}→${leg.to_name} ${fmtMin(leg.minutes)}分`;
    case 'ride':
      return `🚃 ${leg.line_name ?? ''} ${leg.from_name}→${leg.to_name} ${fmtMin(leg.minutes)}分`;
    case 'transfer':
      return `🔄 乗換 ${leg.from_name}${leg.line_name ? `(${leg.line_name})` : ''} ${fmtMin(leg.minutes)}分`;
  }
}

function PlanCard({
  title,
  plan,
  grey,
}: {
  title: string;
  plan: RoutePlan | null;
  grey?: boolean;
}) {
  return (
    <div className={`route-card ${grey ? 'grey' : ''}`}>
      <div className="route-card-title">{title}</div>
      {plan == null ? (
        <p className="muted">到達できません</p>
      ) : (
        <>
          <div className="route-total">
            {fmtMin(plan.total_min)}
            <span className="route-total-unit">分</span>
          </div>
          <ul className="leg-list">
            {plan.legs.map((leg, i) => (
              <li
                key={i}
                className={`leg-item leg-${leg.type}`}
                style={{
                  borderLeftColor:
                    leg.type === 'ride' ? (leg.line_color ?? '#4b5563') : '#9ca3af',
                }}
              >
                {legLabel(leg)}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

export default function RoutePanel(props: RoutePanelProps) {
  const {
    origin,
    dest,
    scenarios,
    scenarioId,
    onScenarioChange,
    loading,
    error,
    result,
    onReset,
  } = props;

  let diffNode = null;
  if (result?.before && result?.after) {
    const diff = result.after.total_min - result.before.total_min;
    const abs = fmtMin(Math.abs(diff));
    diffNode = (
      <div className={`route-diff ${diff < 0 ? 'faster' : diff > 0 ? 'slower' : ''}`}>
        {diff < 0 ? `整備後は −${abs}分 短縮` : diff > 0 ? `整備後は +${abs}分` : '所要時間は変わりません'}
      </div>
    );
  }

  return (
    <div className="panel">
      <p className="panel-desc">
        地図を1回クリックで出発地(緑)、2回目で目的地(赤)を設定すると自動で経路を検索します。3回目のクリックで出発地を置き直します。
      </p>

      <div className="field">
        <span>出発地</span>
        {origin ? (
          <code className="coords">
            {origin[0].toFixed(4)}, {origin[1].toFixed(4)}
          </code>
        ) : (
          <span className="muted">未設定</span>
        )}
      </div>
      <div className="field">
        <span>目的地</span>
        {dest ? (
          <code className="coords">
            {dest[0].toFixed(4)}, {dest[1].toFixed(4)}
          </code>
        ) : (
          <span className="muted">未設定</span>
        )}
      </div>

      <label className="field">
        <span>シナリオ</span>
        <select value={scenarioId} onChange={(e) => onScenarioChange(e.target.value)}>
          <option value="">なし(現況のみ)</option>
          {scenarios.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>

      {(origin || dest) && (
        <button onClick={onReset} disabled={loading}>
          クリア
        </button>
      )}

      {loading && <p className="loading-text">経路を検索しています…</p>}
      {error && <div className="error-text">{error}</div>}

      {result && !loading && (
        <>
          {diffNode}
          <div className="route-cards">
            <PlanCard title="整備前" plan={result.before} grey />
            {scenarioId !== '' && <PlanCard title="整備後" plan={result.after} />}
          </div>
        </>
      )}
    </div>
  );
}
