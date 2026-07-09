import type { FeatureCollection } from 'geojson';

/** GET /api/config */
export interface AppConfig {
  area: string;
  map_center: [number, number];
  map_zoom: number;
  bbox: [number, number, number, number];
  breaks_min_default: number[];
  population_available: boolean;
}

/** GET /api/network/geojson */
export interface NetworkGeoJSON {
  lines: FeatureCollection;
  stations: FeatureCollection;
}

export type LineCategory = 'jr' | 'private' | 'metro' | 'newtransit' | 'tram';

/** 新設路線の駅 */
export interface NewLineStation {
  name: string;
  lon: number;
  lat: number;
  snap_station_id: string | null;
}

/** 新設路線 */
export interface NewLine {
  name: string;
  color: string;
  speed_kmh: number;
  headway_min: number;
  stations: NewLineStation[];
}

/** GET /api/scenarios の要素 */
export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  line_count: number;
  updated_at: string;
}

/** シナリオ完全形 */
export interface Scenario {
  id: string;
  name: string;
  description: string;
  lines: NewLine[];
  created_at: string;
  updated_at: string;
}

/** POST /api/analysis/isochrone のリクエスト */
export interface IsochroneRequest {
  origin: [number, number];
  scenario_id: string | null;
  breaks_min: number[];
}

export interface IsochroneSummaryRow {
  max_min: number;
  area_km2_before: number;
  area_km2_after: number | null;
  population_before: number | null;
  population_after: number | null;
  stations_before: number;
  stations_after: number | null;
}

export interface IsochroneResponse {
  origin: [number, number];
  breaks_min: number[];
  before: FeatureCollection;
  after: FeatureCollection | null;
  summary: IsochroneSummaryRow[];
}

/** POST /api/analysis/route */
export interface RouteRequest {
  origin: [number, number];
  destination: [number, number];
  scenario_id: string | null;
}

export type RouteLegType = 'walk' | 'ride' | 'transfer';

export interface RouteLeg {
  type: RouteLegType;
  line_name: string | null;
  line_color: string | null;
  from_name: string;
  to_name: string;
  minutes: number;
  coords: [number, number][];
}

export interface RoutePlan {
  total_min: number;
  legs: RouteLeg[];
}

export interface RouteResponse {
  before: RoutePlan | null;
  after: RoutePlan | null;
}

/** UI モード */
export type Mode = 'view' | 'edit' | 'iso' | 'route';

/** 既存駅へのスナップ情報 */
export interface SnapInfo {
  id: string;
  name: string;
  lon: number;
  lat: number;
}

export type SaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'error';
