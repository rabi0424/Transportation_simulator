import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import type { Feature, FeatureCollection } from 'geojson';
import type {
  AppConfig,
  IsochroneResponse,
  Mode,
  NetworkGeoJSON,
  NewLine,
  RouteResponse,
  SnapInfo,
} from './types';

const EMPTY_FC: FeatureCollection = { type: 'FeatureCollection', features: [] };
const SNAP_RADIUS_M = 300;
const BAND_COLORS = ['#1d4ed8', '#3b82f6', '#93c5fd', '#dbeafe'];
const JP_FONT = ['Noto Sans Regular'];

const ISO_LAYERS = ['iso-fill', 'iso-outline'];
const ROUTE_LAYERS = ['route-before', 'route-after-ride', 'route-after-walk'];

interface MapViewProps {
  config: AppConfig;
  network: NetworkGeoJSON | null;
  mode: Mode;
  displayLines: NewLine[];
  editingLineIndex: number | null;
  snapEnabled: boolean;
  isoOrigin: [number, number] | null;
  isoResult: IsochroneResponse | null;
  isoView: 'before' | 'after';
  routeOrigin: [number, number] | null;
  routeDest: [number, number] | null;
  routeResult: RouteResponse | null;
  onMapClick: (lngLat: [number, number], snap: SnapInfo | null) => void;
}

function haversineM(a: [number, number], b: [number, number]): number {
  const R = 6371000;
  const toRad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toRad;
  const dLon = (b[0] - a[0]) * toRad;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[1] * toRad) * Math.cos(b[1] * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** 既存駅から lngLat の 300m 以内で最寄りの駅を探す */
function findSnap(network: NetworkGeoJSON | null, lngLat: [number, number]): SnapInfo | null {
  if (!network) return null;
  let best: SnapInfo | null = null;
  let bestDist = SNAP_RADIUS_M;
  for (const f of network.stations.features) {
    if (!f.geometry || f.geometry.type !== 'Point') continue;
    const coords = f.geometry.coordinates as [number, number];
    const d = haversineM(lngLat, coords);
    if (d <= bestDist) {
      bestDist = d;
      best = {
        id: String(f.properties?.id ?? ''),
        name: String(f.properties?.name ?? ''),
        lon: coords[0],
        lat: coords[1],
      };
    }
  }
  return best;
}

function newLinesToFC(lines: NewLine[], editingIndex: number | null) {
  const lineFeatures: Feature[] = [];
  const stationFeatures: Feature[] = [];
  lines.forEach((line, i) => {
    const editing = i === editingIndex;
    if (line.stations.length >= 2) {
      lineFeatures.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: line.stations.map((s) => [s.lon, s.lat]),
        },
        properties: { color: line.color, editing },
      });
    }
    line.stations.forEach((s) => {
      stationFeatures.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [s.lon, s.lat] },
        properties: { name: s.name, color: line.color, editing },
      });
    });
  });
  return {
    lines: { type: 'FeatureCollection', features: lineFeatures } as FeatureCollection,
    stations: { type: 'FeatureCollection', features: stationFeatures } as FeatureCollection,
  };
}

function isoToFC(result: IsochroneResponse, view: 'before' | 'after'): FeatureCollection {
  const fc = view === 'before' ? result.before : result.after;
  if (!fc) return EMPTY_FC;
  const features = fc.features.map((f) => {
    const maxMin = Number(f.properties?.max_min);
    let idx = result.breaks_min.indexOf(maxMin);
    if (idx < 0) idx = BAND_COLORS.length - 1;
    const color = BAND_COLORS[Math.min(idx, BAND_COLORS.length - 1)];
    return {
      ...f,
      properties: { ...f.properties, fill_color: color },
    } as Feature;
  });
  return { type: 'FeatureCollection', features };
}

function getGeoJSONSource(
  map: maplibregl.Map,
  id: string,
): maplibregl.GeoJSONSource | undefined {
  return map.getSource(id) as maplibregl.GeoJSONSource | undefined;
}

function setLayersVisible(map: maplibregl.Map, ids: string[], visible: boolean) {
  for (const id of ids) {
    if (map.getLayer(id)) {
      map.setLayoutProperty(id, 'visibility', visible ? 'visible' : 'none');
    }
  }
}

function routeToFCs(result: RouteResponse | null) {
  const before: Feature[] = [];
  const after: Feature[] = [];
  if (result?.before) {
    for (const leg of result.before.legs) {
      if (!leg.coords || leg.coords.length < 2) continue;
      before.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: leg.coords },
        properties: { kind: leg.type },
      });
    }
  }
  if (result?.after) {
    for (const leg of result.after.legs) {
      if (!leg.coords || leg.coords.length < 2) continue;
      after.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: leg.coords },
        properties: {
          kind: leg.type,
          color: leg.line_color ?? '#4b5563',
        },
      });
    }
  }
  return {
    before: { type: 'FeatureCollection', features: before } as FeatureCollection,
    after: { type: 'FeatureCollection', features: after } as FeatureCollection,
  };
}

export default function MapView(props: MapViewProps) {
  const {
    config,
    network,
    mode,
    displayLines,
    editingLineIndex,
    snapEnabled,
    isoOrigin,
    isoResult,
    isoView,
    routeOrigin,
    routeDest,
    routeResult,
    onMapClick,
  } = props;

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);

  // ハンドラは map 初期化時に一度だけ登録するため、ref で常に最新を参照する
  const onClickRef = useRef(onMapClick);
  onClickRef.current = onMapClick;
  const networkRef = useRef(network);
  networkRef.current = network;
  const snapEnabledRef = useRef(snapEnabled);
  snapEnabledRef.current = snapEnabled;

  const highlightIdRef = useRef<string | null>(null);
  const isoMarkerRef = useRef<maplibregl.Marker | null>(null);
  const routeOriginMarkerRef = useRef<maplibregl.Marker | null>(null);
  const routeDestMarkerRef = useRef<maplibregl.Marker | null>(null);

  // 地図初期化(1回のみ)
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        glyphs: 'https://glyphs.geolonia.com/{fontstack}/{range}.pbf',
        sources: {
          gsi: {
            type: 'raster',
            tiles: ['https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '国土地理院',
          },
        },
        layers: [{ id: 'gsi', type: 'raster', source: 'gsi' }],
      },
      center: config.map_center,
      zoom: config.map_zoom,
    });
    mapRef.current = map;
    if (import.meta.env.DEV) {
      (window as unknown as { __map?: maplibregl.Map }).__map = map;
    }

    // タイル・グリフ取得失敗でクラッシュしないように握りつぶす
    map.on('error', (e) => {
      console.warn('maplibre error:', e.error?.message ?? e);
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');

    // 既存駅ホバー用ポップアップ
    const popup = new maplibregl.Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 8,
    });

    map.on('load', () => {
      // ---- sources ----
      const sources = [
        'network-lines',
        'network-stations',
        'iso',
        'route-before',
        'route-after',
        'new-lines',
        'new-stations',
        'snap-highlight',
      ];
      for (const id of sources) {
        map.addSource(id, { type: 'geojson', data: EMPTY_FC });
      }

      // ---- 等時圏(最下層) ----
      map.addLayer({
        id: 'iso-fill',
        type: 'fill',
        source: 'iso',
        layout: { visibility: 'none' },
        paint: { 'fill-color': ['get', 'fill_color'], 'fill-opacity': 0.45 },
      });
      map.addLayer({
        id: 'iso-outline',
        type: 'line',
        source: 'iso',
        layout: { visibility: 'none' },
        paint: { 'line-color': '#ffffff', 'line-width': 1.2 },
      });

      // ---- 既存ネットワーク ----
      map.addLayer({
        id: 'network-lines',
        type: 'line',
        source: 'network-lines',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['match', ['get', 'category'], 'jr', 2.5, 'metro', 2.5, 2],
          'line-opacity': 0.8,
        },
      });
      map.addLayer({
        id: 'network-stations',
        type: 'circle',
        source: 'network-stations',
        paint: {
          'circle-radius': 3,
          'circle-color': '#ffffff',
          'circle-stroke-color': ['get', 'color'],
          'circle-stroke-width': 1.5,
        },
      });
      map.addLayer({
        id: 'network-station-labels',
        type: 'symbol',
        source: 'network-stations',
        minzoom: 12,
        layout: {
          'text-field': ['get', 'name'],
          'text-font': JP_FONT,
          'text-size': 11,
          'text-offset': [0, 0.8],
          'text-anchor': 'top',
        },
        paint: {
          'text-color': '#333333',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.2,
        },
      });

      // ---- 経路 ----
      map.addLayer({
        id: 'route-before',
        type: 'line',
        source: 'route-before',
        layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' },
        paint: { 'line-color': '#888888', 'line-width': 5, 'line-opacity': 0.7 },
      });
      map.addLayer({
        id: 'route-after-ride',
        type: 'line',
        source: 'route-after',
        filter: ['==', ['get', 'kind'], 'ride'],
        layout: { 'line-cap': 'round', 'line-join': 'round', visibility: 'none' },
        paint: { 'line-color': ['get', 'color'], 'line-width': 5 },
      });
      map.addLayer({
        id: 'route-after-walk',
        type: 'line',
        source: 'route-after',
        filter: ['!=', ['get', 'kind'], 'ride'],
        layout: { 'line-join': 'round', visibility: 'none' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 4,
          'line-dasharray': [0.8, 1.6],
        },
      });

      // ---- スナップ対象ハイライト ----
      map.addLayer({
        id: 'snap-highlight',
        type: 'circle',
        source: 'snap-highlight',
        paint: {
          'circle-radius': 10,
          'circle-color': 'rgba(255, 149, 0, 0.25)',
          'circle-stroke-color': '#ff9500',
          'circle-stroke-width': 2.5,
        },
      });

      // ---- 新設路線 ----
      map.addLayer({
        id: 'new-lines',
        type: 'line',
        source: 'new-lines',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: {
          'line-color': ['get', 'color'],
          'line-width': ['case', ['==', ['get', 'editing'], true], 5.5, 4],
          'line-dasharray': [2, 1.5],
        },
      });
      map.addLayer({
        id: 'new-stations',
        type: 'circle',
        source: 'new-stations',
        paint: {
          'circle-radius': ['case', ['==', ['get', 'editing'], true], 7, 6],
          'circle-color': '#ffffff',
          'circle-stroke-color': ['get', 'color'],
          'circle-stroke-width': ['case', ['==', ['get', 'editing'], true], 3, 2.5],
        },
      });
      map.addLayer({
        id: 'new-station-labels',
        type: 'symbol',
        source: 'new-stations',
        layout: {
          'text-field': ['get', 'name'],
          'text-font': JP_FONT,
          'text-size': 12,
          'text-offset': [0, 1],
          'text-anchor': 'top',
          'text-allow-overlap': true,
        },
        paint: {
          'text-color': '#111111',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.5,
        },
      });

      // 既存駅ホバーでポップアップ(レイヤー追加後に登録)
      map.on('mousemove', 'network-stations', (e) => {
        const f = e.features && e.features[0];
        if (!f || f.geometry.type !== 'Point') return;
        const [lon, lat] = f.geometry.coordinates as [number, number];
        const name = escapeHtml(String(f.properties?.name ?? ''));
        const lineName = escapeHtml(String(f.properties?.line_name ?? ''));
        popup
          .setLngLat([lon, lat])
          .setHTML(
            `<div class="station-popup"><strong>${name}</strong><br/><span>${lineName}</span></div>`,
          )
          .addTo(map);
      });
      map.on('mouseleave', 'network-stations', () => {
        popup.remove();
      });

      setReady(true);
    });

    // クリック(モードに応じた処理は App 側。スナップ判定だけここで行う)
    map.on('click', (e) => {
      const lngLat: [number, number] = [e.lngLat.lng, e.lngLat.lat];
      const snap = snapEnabledRef.current ? findSnap(networkRef.current, lngLat) : null;
      onClickRef.current(lngLat, snap);
    });

    // スナップ対象のハイライト
    map.on('mousemove', (e) => {
      if (!map.getSource('snap-highlight')) return;
      if (!snapEnabledRef.current) {
        if (highlightIdRef.current !== null) {
          highlightIdRef.current = null;
          (map.getSource('snap-highlight') as maplibregl.GeoJSONSource).setData(EMPTY_FC);
        }
        return;
      }
      const snap = findSnap(networkRef.current, [e.lngLat.lng, e.lngLat.lat]);
      const id = snap ? snap.id : null;
      if (id === highlightIdRef.current) return;
      highlightIdRef.current = id;
      const src = map.getSource('snap-highlight') as maplibregl.GeoJSONSource;
      if (snap) {
        src.setData({
          type: 'FeatureCollection',
          features: [
            {
              type: 'Feature',
              geometry: { type: 'Point', coordinates: [snap.lon, snap.lat] },
              properties: {},
            },
          ],
        });
      } else {
        src.setData(EMPTY_FC);
      }
    });

    return () => {
      popup.remove();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
    // 初期化は1回のみ(config は初回値を使用)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // config が後から変わった場合は中心を移動
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.jumpTo({ center: config.map_center, zoom: config.map_zoom });
  }, [config]);

  // 既存ネットワーク描画
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !network) return;
    getGeoJSONSource(map, 'network-lines')?.setData(network.lines);
    getGeoJSONSource(map, 'network-stations')?.setData(network.stations);
  }, [ready, network]);

  // 新設路線描画
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const fc = newLinesToFC(displayLines, mode === 'edit' ? editingLineIndex : null);
    getGeoJSONSource(map, 'new-lines')?.setData(fc.lines);
    getGeoJSONSource(map, 'new-stations')?.setData(fc.stations);
  }, [ready, displayLines, editingLineIndex, mode]);

  // スナップ無効化時にハイライトを消し、カーソルを切替
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.getCanvas().style.cursor = snapEnabled ? 'crosshair' : '';
    if (!snapEnabled && highlightIdRef.current !== null) {
      highlightIdRef.current = null;
      getGeoJSONSource(map, 'snap-highlight')?.setData(EMPTY_FC);
    }
  }, [ready, snapEnabled]);

  // 等時圏描画
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const visible = mode === 'iso' && isoResult != null;
    const data = visible && isoResult ? isoToFC(isoResult, isoView) : EMPTY_FC;
    getGeoJSONSource(map, 'iso')?.setData(data);
    setLayersVisible(map, ISO_LAYERS, visible);
  }, [ready, mode, isoResult, isoView]);

  // 等時圏 出発地マーカー
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (mode === 'iso' && isoOrigin) {
      if (!isoMarkerRef.current) {
        isoMarkerRef.current = new maplibregl.Marker({ color: '#2563eb' })
          .setLngLat(isoOrigin)
          .addTo(map);
      } else {
        isoMarkerRef.current.setLngLat(isoOrigin);
      }
    } else if (isoMarkerRef.current) {
      isoMarkerRef.current.remove();
      isoMarkerRef.current = null;
    }
  }, [ready, mode, isoOrigin]);

  // 経路描画
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const visible = mode === 'route' && routeResult != null;
    const fcs = routeToFCs(visible ? routeResult : null);
    getGeoJSONSource(map, 'route-before')?.setData(fcs.before);
    getGeoJSONSource(map, 'route-after')?.setData(fcs.after);
    setLayersVisible(map, ROUTE_LAYERS, visible);
  }, [ready, mode, routeResult]);

  // 経路 出発地・目的地マーカー
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const sync = (
      ref: React.MutableRefObject<maplibregl.Marker | null>,
      pos: [number, number] | null,
      color: string,
    ) => {
      if (mode === 'route' && pos) {
        if (!ref.current) {
          ref.current = new maplibregl.Marker({ color }).setLngLat(pos).addTo(map);
        } else {
          ref.current.setLngLat(pos);
        }
      } else if (ref.current) {
        ref.current.remove();
        ref.current = null;
      }
    };
    sync(routeOriginMarkerRef, routeOrigin, '#16a34a');
    sync(routeDestMarkerRef, routeDest, '#dc2626');
  }, [ready, mode, routeOrigin, routeDest]);

  return <div ref={containerRef} className="map-container" />;
}
