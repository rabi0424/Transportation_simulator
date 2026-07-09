import { useCallback, useEffect, useRef, useState } from 'react';
import MapView from './MapView';
import ViewPanel from './panels/ViewPanel';
import EditPanel from './panels/EditPanel';
import IsochronePanel from './panels/IsochronePanel';
import RoutePanel from './panels/RoutePanel';
import { api } from './api';
import type {
  AppConfig,
  IsochroneResponse,
  Mode,
  NetworkGeoJSON,
  NewLine,
  RouteResponse,
  SaveState,
  Scenario,
  ScenarioSummary,
  SnapInfo,
} from './types';

const FALLBACK_CONFIG: AppConfig = {
  area: 'keihanshin',
  map_center: [135.5, 34.7],
  map_zoom: 10,
  bbox: [134.4, 34.15, 136.4, 35.4],
  breaks_min_default: [15, 30, 45, 60],
  population_available: false,
};

const MODE_TABS: { key: Mode; label: string }[] = [
  { key: 'view', label: '閲覧' },
  { key: 'edit', label: '路線編集' },
  { key: 'iso', label: '等時圏' },
  { key: 'route', label: '経路' },
];

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export default function App() {
  // ---- 基本データ ----
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [network, setNetwork] = useState<NetworkGeoJSON | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // ---- モード ----
  const [mode, setMode] = useState<Mode>('view');

  // ---- シナリオ ----
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [editScenario, setEditScenario] = useState<Scenario | null>(null);
  const [editingLineIndex, setEditingLineIndex] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [editError, setEditError] = useState<string | null>(null);
  const [scenarioBusy, setScenarioBusy] = useState(false);
  const dirtyRef = useRef(false);

  // ---- 分析用シナリオ(等時圏・経路で共有)----
  const [analysisScenarioId, setAnalysisScenarioId] = useState('');
  const [analysisScenario, setAnalysisScenario] = useState<Scenario | null>(null);

  // ---- 等時圏 ----
  const [isoOrigin, setIsoOrigin] = useState<[number, number] | null>(null);
  const [isoResult, setIsoResult] = useState<IsochroneResponse | null>(null);
  const [isoView, setIsoView] = useState<'before' | 'after'>('before');
  const [isoLoading, setIsoLoading] = useState(false);
  const [isoError, setIsoError] = useState<string | null>(null);

  // ---- 経路 ----
  const [routeOrigin, setRouteOrigin] = useState<[number, number] | null>(null);
  const [routeDest, setRouteDest] = useState<[number, number] | null>(null);
  const [routeResult, setRouteResult] = useState<RouteResponse | null>(null);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);

  const refreshScenarios = useCallback(async () => {
    try {
      setScenarios(await api.listScenarios());
    } catch (e) {
      setEditError(errMsg(e));
    }
  }, []);

  // ---- 起動時の読み込み ----
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const errors: string[] = [];
      try {
        const cfg = await api.getConfig();
        if (!cancelled) setConfig(cfg);
      } catch (e) {
        errors.push(`設定の取得に失敗: ${errMsg(e)}`);
        if (!cancelled) setConfig(FALLBACK_CONFIG);
      }
      try {
        const net = await api.getNetwork();
        if (!cancelled) setNetwork(net);
      } catch (e) {
        errors.push(`ネットワークの取得に失敗: ${errMsg(e)}`);
      }
      try {
        const list = await api.listScenarios();
        if (!cancelled) setScenarios(list);
      } catch {
        // 個別パネル側で再取得できるため、ここでは config/network のエラーのみ表示
      }
      if (!cancelled && errors.length > 0) setLoadError(errors.join(' / '));
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // ---- 編集内容のデバウンス保存(800ms)----
  useEffect(() => {
    if (!editScenario || !dirtyRef.current) return;
    const target = editScenario;
    const timer = setTimeout(async () => {
      dirtyRef.current = false;
      setSaveState('saving');
      try {
        await api.updateScenario(target.id, {
          name: target.name,
          description: target.description,
          lines: target.lines,
        });
        setSaveState((prev) => (dirtyRef.current ? prev : 'saved'));
        setEditError(null);
        void refreshScenarios();
      } catch (e) {
        setSaveState('error');
        setEditError(`保存エラー: ${errMsg(e)}`);
      }
    }, 800);
    return () => clearTimeout(timer);
  }, [editScenario, refreshScenarios]);

  /** ローカル編集(デバウンス保存対象)を適用する */
  const mutateScenario = useCallback((updater: (s: Scenario) => Scenario) => {
    setEditScenario((s) => {
      if (!s) return s;
      dirtyRef.current = true;
      return updater(s);
    });
    setSaveState('pending');
  }, []);

  // ---- シナリオ CRUD ----
  const handleCreateScenario = useCallback(
    async (name: string) => {
      setScenarioBusy(true);
      setEditError(null);
      try {
        const created = await api.createScenario(name);
        dirtyRef.current = false;
        setEditScenario(created);
        setEditingLineIndex(null);
        setSaveState('idle');
        await refreshScenarios();
      } catch (e) {
        setEditError(errMsg(e));
      } finally {
        setScenarioBusy(false);
      }
    },
    [refreshScenarios],
  );

  const handleSelectScenario = useCallback(async (id: string) => {
    setEditError(null);
    try {
      const full = await api.getScenario(id);
      dirtyRef.current = false;
      setEditScenario(full);
      setEditingLineIndex(full.lines.length > 0 ? full.lines.length - 1 : null);
      setSaveState('idle');
    } catch (e) {
      setEditError(errMsg(e));
    }
  }, []);

  const handleDuplicateScenario = useCallback(
    async (id: string) => {
      setScenarioBusy(true);
      setEditError(null);
      try {
        const dup = await api.duplicateScenario(id);
        dirtyRef.current = false;
        setEditScenario(dup);
        setEditingLineIndex(null);
        setSaveState('idle');
        await refreshScenarios();
      } catch (e) {
        setEditError(errMsg(e));
      } finally {
        setScenarioBusy(false);
      }
    },
    [refreshScenarios],
  );

  const handleDeleteScenario = useCallback(
    async (id: string) => {
      setScenarioBusy(true);
      setEditError(null);
      try {
        await api.deleteScenario(id);
        if (editScenario?.id === id) {
          dirtyRef.current = false;
          setEditScenario(null);
          setEditingLineIndex(null);
          setSaveState('idle');
        }
        if (analysisScenarioId === id) {
          setAnalysisScenarioId('');
          setAnalysisScenario(null);
        }
        await refreshScenarios();
      } catch (e) {
        setEditError(errMsg(e));
      } finally {
        setScenarioBusy(false);
      }
    },
    [editScenario, analysisScenarioId, refreshScenarios],
  );

  // ---- 路線編集 ----
  const handleAddLine = useCallback(() => {
    let newIndex = 0;
    mutateScenario((s) => {
      newIndex = s.lines.length;
      const line: NewLine = {
        name: `新線${s.lines.length + 1}`,
        color: '#FF3B30',
        speed_kmh: 35,
        headway_min: 6,
        stations: [],
      };
      return { ...s, lines: [...s.lines, line] };
    });
    setEditingLineIndex(newIndex);
  }, [mutateScenario]);

  const handleDeleteLine = useCallback(
    (index: number) => {
      mutateScenario((s) => ({
        ...s,
        lines: s.lines.filter((_, i) => i !== index),
      }));
      setEditingLineIndex((cur) => {
        if (cur == null) return cur;
        if (cur === index) return null;
        return cur > index ? cur - 1 : cur;
      });
    },
    [mutateScenario],
  );

  const handleLineChange = useCallback(
    (index: number, patch: Partial<NewLine>) => {
      mutateScenario((s) => ({
        ...s,
        lines: s.lines.map((l, i) => (i === index ? { ...l, ...patch } : l)),
      }));
    },
    [mutateScenario],
  );

  const handleStationRename = useCallback(
    (lineIndex: number, stationIndex: number, name: string) => {
      mutateScenario((s) => ({
        ...s,
        lines: s.lines.map((l, i) =>
          i === lineIndex
            ? {
                ...l,
                stations: l.stations.map((st, si) =>
                  si === stationIndex ? { ...st, name } : st,
                ),
              }
            : l,
        ),
      }));
    },
    [mutateScenario],
  );

  const handleStationDelete = useCallback(
    (lineIndex: number, stationIndex: number) => {
      mutateScenario((s) => ({
        ...s,
        lines: s.lines.map((l, i) =>
          i === lineIndex
            ? { ...l, stations: l.stations.filter((_, si) => si !== stationIndex) }
            : l,
        ),
      }));
    },
    [mutateScenario],
  );

  const handleUndoStation = useCallback(
    (lineIndex: number) => {
      mutateScenario((s) => ({
        ...s,
        lines: s.lines.map((l, i) =>
          i === lineIndex ? { ...l, stations: l.stations.slice(0, -1) } : l,
        ),
      }));
    },
    [mutateScenario],
  );

  // ---- 地図クリック ----
  const handleMapClick = useCallback(
    (lngLat: [number, number], snap: SnapInfo | null) => {
      if (mode === 'edit') {
        if (!editScenario || editingLineIndex == null) return;
        mutateScenario((s) => ({
          ...s,
          lines: s.lines.map((l, i) => {
            if (i !== editingLineIndex) return l;
            const station = snap
              ? {
                  name: snap.name,
                  lon: snap.lon,
                  lat: snap.lat,
                  snap_station_id: snap.id,
                }
              : {
                  name: `新駅${l.stations.length + 1}`,
                  lon: lngLat[0],
                  lat: lngLat[1],
                  snap_station_id: null,
                };
            return { ...l, stations: [...l.stations, station] };
          }),
        }));
      } else if (mode === 'iso') {
        setIsoOrigin(lngLat);
        setIsoResult(null);
        setIsoError(null);
      } else if (mode === 'route') {
        if (!routeOrigin || (routeOrigin && routeDest)) {
          // 1回目 or 3回目: 出発地の(置き)設定
          setRouteOrigin(lngLat);
          setRouteDest(null);
          setRouteResult(null);
          setRouteError(null);
        } else {
          setRouteDest(lngLat);
        }
      }
    },
    [mode, editScenario, editingLineIndex, mutateScenario, routeOrigin, routeDest],
  );

  // ---- 分析用シナリオの取得(地図に新設路線を表示するため)----
  useEffect(() => {
    if (!analysisScenarioId) {
      setAnalysisScenario(null);
      return;
    }
    let cancelled = false;
    api
      .getScenario(analysisScenarioId)
      .then((s) => {
        if (!cancelled) setAnalysisScenario(s);
      })
      .catch(() => {
        if (!cancelled) setAnalysisScenario(null);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisScenarioId]);

  // ---- 等時圏計算 ----
  const handleIsochrone = useCallback(async () => {
    if (!isoOrigin) return;
    setIsoLoading(true);
    setIsoError(null);
    try {
      const res = await api.isochrone({
        origin: isoOrigin,
        scenario_id: analysisScenarioId || null,
        breaks_min: (config ?? FALLBACK_CONFIG).breaks_min_default,
      });
      setIsoResult(res);
      setIsoView(res.after != null ? 'after' : 'before');
    } catch (e) {
      setIsoError(errMsg(e));
      setIsoResult(null);
    } finally {
      setIsoLoading(false);
    }
  }, [isoOrigin, analysisScenarioId, config]);

  // ---- 経路検索(出発地・目的地が揃ったら自動実行)----
  useEffect(() => {
    if (mode !== 'route' || !routeOrigin || !routeDest) return;
    let stale = false;
    setRouteLoading(true);
    setRouteError(null);
    api
      .route({
        origin: routeOrigin,
        destination: routeDest,
        scenario_id: analysisScenarioId || null,
      })
      .then((res) => {
        if (!stale) setRouteResult(res);
      })
      .catch((e) => {
        if (!stale) {
          setRouteError(errMsg(e));
          setRouteResult(null);
        }
      })
      .finally(() => {
        if (!stale) setRouteLoading(false);
      });
    return () => {
      stale = true;
    };
  }, [mode, routeOrigin, routeDest, analysisScenarioId]);

  const handleRouteReset = useCallback(() => {
    setRouteOrigin(null);
    setRouteDest(null);
    setRouteResult(null);
    setRouteError(null);
  }, []);

  // ---- 地図に表示する新設路線 ----
  const displayLines: NewLine[] =
    mode === 'edit'
      ? (editScenario?.lines ?? [])
      : mode === 'iso' || mode === 'route'
        ? (analysisScenario?.lines ?? [])
        : [];

  const snapEnabled = mode === 'edit' && editScenario != null && editingLineIndex != null;

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="app-title">新設路線シミュレーター</h1>
        <nav className="mode-tabs">
          {MODE_TABS.map((t) => (
            <button
              key={t.key}
              className={`mode-tab ${mode === t.key ? 'active' : ''}`}
              onClick={() => setMode(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>

        {loadError && <div className="error-text global">{loadError}</div>}

        {mode === 'view' && <ViewPanel network={network} />}
        {mode === 'edit' && (
          <EditPanel
            scenarios={scenarios}
            scenario={editScenario}
            editingLineIndex={editingLineIndex}
            saveState={saveState}
            error={editError}
            busy={scenarioBusy}
            onCreate={handleCreateScenario}
            onSelect={handleSelectScenario}
            onDuplicate={handleDuplicateScenario}
            onDelete={handleDeleteScenario}
            onAddLine={handleAddLine}
            onSelectLine={setEditingLineIndex}
            onDeleteLine={handleDeleteLine}
            onLineChange={handleLineChange}
            onStationRename={handleStationRename}
            onStationDelete={handleStationDelete}
            onUndoStation={handleUndoStation}
          />
        )}
        {mode === 'iso' && (
          <IsochronePanel
            origin={isoOrigin}
            scenarios={scenarios}
            scenarioId={analysisScenarioId}
            onScenarioChange={setAnalysisScenarioId}
            onCalculate={handleIsochrone}
            loading={isoLoading}
            error={isoError}
            result={isoResult}
            view={isoView}
            onViewChange={setIsoView}
          />
        )}
        {mode === 'route' && (
          <RoutePanel
            origin={routeOrigin}
            dest={routeDest}
            scenarios={scenarios}
            scenarioId={analysisScenarioId}
            onScenarioChange={setAnalysisScenarioId}
            loading={routeLoading}
            error={routeError}
            result={routeResult}
            onReset={handleRouteReset}
          />
        )}
      </aside>
      <main className="map-area">
        {config ? (
          <MapView
            config={config}
            network={network}
            mode={mode}
            displayLines={displayLines}
            editingLineIndex={editingLineIndex}
            snapEnabled={snapEnabled}
            isoOrigin={isoOrigin}
            isoResult={isoResult}
            isoView={isoView}
            routeOrigin={routeOrigin}
            routeDest={routeDest}
            routeResult={routeResult}
            onMapClick={handleMapClick}
          />
        ) : (
          <div className="map-placeholder">地図を読み込んでいます…</div>
        )}
      </main>
    </div>
  );
}
