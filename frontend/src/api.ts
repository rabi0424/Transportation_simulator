import type {
  AppConfig,
  IsochroneRequest,
  IsochroneResponse,
  NetworkGeoJSON,
  NewLine,
  RouteRequest,
  RouteResponse,
  Scenario,
  ScenarioSummary,
} from './types';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new Error('サーバーに接続できません(バックエンドが起動しているか確認してください)');
  }
  if (!res.ok) {
    let message = `エラー(HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (body && body.detail) {
        message =
          typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
      }
    } catch {
      // detail なしはステータスのみ表示
    }
    throw new Error(message);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const api = {
  getConfig(): Promise<AppConfig> {
    return request('/api/config');
  },
  getNetwork(): Promise<NetworkGeoJSON> {
    return request('/api/network/geojson');
  },
  listScenarios(): Promise<ScenarioSummary[]> {
    return request('/api/scenarios');
  },
  createScenario(name: string, description = ''): Promise<Scenario> {
    return request('/api/scenarios', jsonInit('POST', { name, description }));
  },
  getScenario(id: string): Promise<Scenario> {
    return request(`/api/scenarios/${encodeURIComponent(id)}`);
  },
  updateScenario(
    id: string,
    body: { name?: string; description?: string; lines?: NewLine[] },
  ): Promise<Scenario> {
    return request(`/api/scenarios/${encodeURIComponent(id)}`, jsonInit('PUT', body));
  },
  deleteScenario(id: string): Promise<void> {
    return request(`/api/scenarios/${encodeURIComponent(id)}`, { method: 'DELETE' });
  },
  duplicateScenario(id: string): Promise<Scenario> {
    return request(
      `/api/scenarios/${encodeURIComponent(id)}/duplicate`,
      jsonInit('POST'),
    );
  },
  isochrone(body: IsochroneRequest): Promise<IsochroneResponse> {
    return request('/api/analysis/isochrone', jsonInit('POST', body));
  },
  route(body: RouteRequest): Promise<RouteResponse> {
    return request('/api/analysis/route', jsonInit('POST', body));
  },
};
