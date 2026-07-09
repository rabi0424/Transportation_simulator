import type { IsochroneResponse, ScenarioSummary } from '../types';

const BAND_COLORS = ['#1d4ed8', '#3b82f6', '#93c5fd', '#dbeafe'];

interface IsochronePanelProps {
  origin: [number, number] | null;
  scenarios: ScenarioSummary[];
  scenarioId: string;
  onScenarioChange: (id: string) => void;
  onCalculate: () => void;
  loading: boolean;
  error: string | null;
  result: IsochroneResponse | null;
  view: 'before' | 'after';
  onViewChange: (view: 'before' | 'after') => void;
}

function fmtArea(v: number | null): string {
  return v == null ? '—' : v.toFixed(1);
}

function fmtDelta(before: number | null, after: number | null): string {
  if (before == null || after == null) return '—';
  const d = after - before;
  const s = Math.abs(d) >= 100 ? d.toFixed(0) : d.toFixed(1);
  return d > 0 ? `+${s}` : s;
}

function fmtPop(v: number | null): string {
  return v == null ? '—' : Math.round(v).toLocaleString('ja-JP');
}

export default function IsochronePanel(props: IsochronePanelProps) {
  const {
    origin,
    scenarios,
    scenarioId,
    onScenarioChange,
    onCalculate,
    loading,
    error,
    result,
    view,
    onViewChange,
  } = props;

  const hasAfter = result?.after != null;
  const hasPopulation =
    result != null && result.summary.some((r) => r.population_before != null);

  return (
    <div className="panel">
      <p className="panel-desc">
        地図をクリックして出発地を設定し、「計算」を押すと到達時間帯(等時圏)を表示します。
      </p>

      <div className="field">
        <span>出発地</span>
        {origin ? (
          <code className="coords">
            {origin[0].toFixed(4)}, {origin[1].toFixed(4)}
          </code>
        ) : (
          <span className="muted">未設定(地図をクリック)</span>
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

      <button
        className="primary"
        onClick={onCalculate}
        disabled={!origin || loading}
      >
        {loading ? '計算中…' : '計算'}
      </button>

      {loading && (
        <p className="loading-text">等時圏を計算しています(数秒かかることがあります)…</p>
      )}
      {error && <div className="error-text">{error}</div>}

      {result && !loading && (
        <>
          <div className="field radio-row">
            <span>表示</span>
            <label>
              <input
                type="radio"
                name="iso-view"
                checked={view === 'before'}
                onChange={() => onViewChange('before')}
              />
              整備前
            </label>
            <label className={hasAfter ? '' : 'disabled'}>
              <input
                type="radio"
                name="iso-view"
                checked={view === 'after'}
                disabled={!hasAfter}
                onChange={() => onViewChange('after')}
              />
              整備後
            </label>
          </div>

          <h3 className="section-title">サマリー(累積値)</h3>
          <div className="table-wrap">
            <table className="summary-table">
              <thead>
                <tr>
                  <th>到達時間</th>
                  <th colSpan={hasAfter ? 3 : 1}>面積 (km²)</th>
                  {hasPopulation && <th colSpan={hasAfter ? 3 : 1}>人口</th>}
                  <th colSpan={hasAfter ? 2 : 1}>到達駅数</th>
                </tr>
                <tr>
                  <th />
                  <th>前</th>
                  {hasAfter && (
                    <>
                      <th>後</th>
                      <th>Δ</th>
                    </>
                  )}
                  {hasPopulation && (
                    <>
                      <th>前</th>
                      {hasAfter && (
                        <>
                          <th>後</th>
                          <th>Δ</th>
                        </>
                      )}
                    </>
                  )}
                  <th>前</th>
                  {hasAfter && <th>後</th>}
                </tr>
              </thead>
              <tbody>
                {result.summary.map((row, i) => (
                  <tr key={row.max_min}>
                    <td>
                      <span
                        className="legend-swatch small"
                        style={{
                          backgroundColor:
                            BAND_COLORS[Math.min(i, BAND_COLORS.length - 1)],
                        }}
                      />
                      〜{row.max_min}分
                    </td>
                    <td className="num">{fmtArea(row.area_km2_before)}</td>
                    {hasAfter && (
                      <>
                        <td className="num">{fmtArea(row.area_km2_after)}</td>
                        <td className="num delta">
                          {fmtDelta(row.area_km2_before, row.area_km2_after)}
                        </td>
                      </>
                    )}
                    {hasPopulation && (
                      <>
                        <td className="num">{fmtPop(row.population_before)}</td>
                        {hasAfter && (
                          <>
                            <td className="num">{fmtPop(row.population_after)}</td>
                            <td className="num delta">
                              {fmtDelta(row.population_before, row.population_after)}
                            </td>
                          </>
                        )}
                      </>
                    )}
                    <td className="num">{row.stations_before}</td>
                    {hasAfter && (
                      <td className="num">{row.stations_after ?? '—'}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
