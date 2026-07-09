import { useState } from 'react';
import type { NewLine, SaveState, Scenario, ScenarioSummary } from '../types';

export const COLOR_PRESETS = [
  '#FF3B30',
  '#FF9500',
  '#FFCC00',
  '#34C759',
  '#00A5BF',
  '#007AFF',
  '#5856D6',
  '#AF52DE',
  '#8E8E93',
];

interface EditPanelProps {
  scenarios: ScenarioSummary[];
  scenario: Scenario | null;
  editingLineIndex: number | null;
  saveState: SaveState;
  error: string | null;
  busy: boolean;
  onCreate: (name: string) => void;
  onSelect: (id: string) => void;
  onDuplicate: (id: string) => void;
  onDelete: (id: string) => void;
  onAddLine: () => void;
  onSelectLine: (index: number | null) => void;
  onDeleteLine: (index: number) => void;
  onLineChange: (index: number, patch: Partial<NewLine>) => void;
  onStationRename: (lineIndex: number, stationIndex: number, name: string) => void;
  onStationDelete: (lineIndex: number, stationIndex: number) => void;
  onUndoStation: (lineIndex: number) => void;
}

function SaveIndicator({ state }: { state: SaveState }) {
  switch (state) {
    case 'pending':
      return <span className="save-indicator pending">未保存の変更あり…</span>;
    case 'saving':
      return <span className="save-indicator saving">保存中…</span>;
    case 'saved':
      return <span className="save-indicator saved">保存済み</span>;
    case 'error':
      return <span className="save-indicator error">保存に失敗しました</span>;
    default:
      return null;
  }
}

export default function EditPanel(props: EditPanelProps) {
  const {
    scenarios,
    scenario,
    editingLineIndex,
    saveState,
    error,
    busy,
    onCreate,
    onSelect,
    onDuplicate,
    onDelete,
    onAddLine,
    onSelectLine,
    onDeleteLine,
    onLineChange,
    onStationRename,
    onStationDelete,
    onUndoStation,
  } = props;

  const [newName, setNewName] = useState('');

  const editingLine =
    scenario && editingLineIndex != null ? scenario.lines[editingLineIndex] : null;

  const handleCreate = () => {
    const name = newName.trim();
    if (!name) return;
    onCreate(name);
    setNewName('');
  };

  return (
    <div className="panel">
      {error && <div className="error-text">{error}</div>}

      <h3 className="section-title">シナリオ</h3>
      <div className="row">
        <input
          type="text"
          value={newName}
          placeholder="新しいシナリオ名"
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleCreate();
          }}
        />
        <button onClick={handleCreate} disabled={busy || !newName.trim()}>
          作成
        </button>
      </div>

      {scenarios.length === 0 ? (
        <p className="muted">シナリオはまだありません。名前を入力して作成してください。</p>
      ) : (
        <ul className="scenario-list">
          {scenarios.map((s) => (
            <li
              key={s.id}
              className={`scenario-item ${scenario?.id === s.id ? 'selected' : ''}`}
            >
              <button
                className="scenario-name"
                onClick={() => onSelect(s.id)}
                title={s.name}
              >
                {s.name}
                <span className="muted"> ({s.line_count}路線)</span>
              </button>
              <span className="scenario-actions">
                <button className="mini" onClick={() => onDuplicate(s.id)} disabled={busy}>
                  複製
                </button>
                <button
                  className="mini danger"
                  disabled={busy}
                  onClick={() => {
                    if (window.confirm(`シナリオ「${s.name}」を削除しますか?`)) {
                      onDelete(s.id);
                    }
                  }}
                >
                  削除
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}

      {scenario && (
        <>
          <div className="section-header">
            <h3 className="section-title">
              新設路線 <span className="muted">— {scenario.name}</span>
            </h3>
            <SaveIndicator state={saveState} />
          </div>

          <ul className="line-list">
            {scenario.lines.map((line, i) => (
              <li
                key={i}
                className={`line-item ${i === editingLineIndex ? 'editing' : ''}`}
              >
                <button className="line-select" onClick={() => onSelectLine(i)}>
                  <span className="legend-swatch" style={{ backgroundColor: line.color }} />
                  {line.name}
                  <span className="muted"> ({line.stations.length}駅)</span>
                </button>
                <button
                  className="mini danger"
                  onClick={() => {
                    if (window.confirm(`路線「${line.name}」を削除しますか?`)) {
                      onDeleteLine(i);
                    }
                  }}
                >
                  削除
                </button>
              </li>
            ))}
          </ul>
          <button className="add-line" onClick={onAddLine}>
            + 路線を追加
          </button>

          {editingLine && editingLineIndex != null && (
            <div className="line-editor">
              <h3 className="section-title">路線の編集: {editingLine.name}</h3>
              <p className="hint">
                地図をクリックすると末尾に駅を追加します。既存駅の 300m
                以内をクリックするとその駅にスナップします(近くの駅はオレンジでハイライト)。
              </p>

              <label className="field">
                <span>路線名</span>
                <input
                  type="text"
                  value={editingLine.name}
                  onChange={(e) => onLineChange(editingLineIndex, { name: e.target.value })}
                />
              </label>
              <div className="field-row">
                <label className="field">
                  <span>表定速度 (km/h)</span>
                  <input
                    type="number"
                    min={5}
                    max={300}
                    step={1}
                    value={editingLine.speed_kmh}
                    onChange={(e) =>
                      onLineChange(editingLineIndex, {
                        speed_kmh: Number(e.target.value) || 0,
                      })
                    }
                  />
                </label>
                <label className="field">
                  <span>運行間隔 (分)</span>
                  <input
                    type="number"
                    min={1}
                    max={120}
                    step={0.5}
                    value={editingLine.headway_min}
                    onChange={(e) =>
                      onLineChange(editingLineIndex, {
                        headway_min: Number(e.target.value) || 0,
                      })
                    }
                  />
                </label>
              </div>
              <div className="field">
                <span>路線色</span>
                <div className="palette">
                  {COLOR_PRESETS.map((c) => (
                    <button
                      key={c}
                      className={`swatch ${editingLine.color === c ? 'selected' : ''}`}
                      style={{ backgroundColor: c }}
                      title={c}
                      onClick={() => onLineChange(editingLineIndex, { color: c })}
                    />
                  ))}
                </div>
              </div>

              <h4 className="subsection-title">駅リスト ({editingLine.stations.length})</h4>
              {editingLine.stations.length === 0 ? (
                <p className="muted">地図をクリックして駅を追加してください。</p>
              ) : (
                <ol className="station-list">
                  {editingLine.stations.map((st, si) => (
                    <li key={si} className="station-item">
                      <span className="station-index">{si + 1}</span>
                      <input
                        type="text"
                        value={st.name}
                        onChange={(e) =>
                          onStationRename(editingLineIndex, si, e.target.value)
                        }
                      />
                      {st.snap_station_id && (
                        <span className="snap-badge" title="既存駅にスナップ済み">
                          接
                        </span>
                      )}
                      <button
                        className="mini danger"
                        onClick={() => onStationDelete(editingLineIndex, si)}
                      >
                        ×
                      </button>
                    </li>
                  ))}
                </ol>
              )}
              {editingLine.stations.length > 0 && (
                <button className="mini" onClick={() => onUndoStation(editingLineIndex)}>
                  最後の駅を取消
                </button>
              )}
            </div>
          )}
          {!editingLine && scenario.lines.length > 0 && (
            <p className="muted">路線を選択すると編集できます。</p>
          )}
        </>
      )}
      {!scenario && scenarios.length > 0 && (
        <p className="muted">シナリオを選択すると路線を編集できます。</p>
      )}
    </div>
  );
}
