import { useMemo } from 'react';
import type { NetworkGeoJSON } from '../types';

const CATEGORY_LABELS: Record<string, string> = {
  jr: 'JR',
  private: '私鉄',
  metro: '地下鉄',
  newtransit: '新交通システム',
  tram: '路面電車',
};

const CATEGORY_FALLBACK_COLORS: Record<string, string> = {
  jr: '#1e50a2',
  private: '#e4007f',
  metro: '#e60012',
  newtransit: '#00a5bf',
  tram: '#8f76d6',
};

interface ViewPanelProps {
  network: NetworkGeoJSON | null;
}

export default function ViewPanel({ network }: ViewPanelProps) {
  const legend = useMemo(() => {
    const order = ['jr', 'private', 'metro', 'newtransit', 'tram'];
    const found = new Map<string, { color: string; count: number }>();
    if (network) {
      for (const f of network.lines.features) {
        const cat = String(f.properties?.category ?? '');
        if (!cat) continue;
        const entry = found.get(cat);
        if (entry) {
          entry.count += 1;
        } else {
          found.set(cat, {
            color: String(f.properties?.color ?? CATEGORY_FALLBACK_COLORS[cat] ?? '#666'),
            count: 1,
          });
        }
      }
    }
    const cats = order.filter((c) => found.has(c));
    for (const c of found.keys()) {
      if (!cats.includes(c)) cats.push(c);
    }
    return cats.map((c) => ({
      category: c,
      label: CATEGORY_LABELS[c] ?? c,
      color: found.get(c)?.color ?? CATEGORY_FALLBACK_COLORS[c] ?? '#666',
      count: found.get(c)?.count ?? 0,
    }));
  }, [network]);

  return (
    <div className="panel">
      <p className="panel-desc">
        京阪神エリアの既存鉄道ネットワークを表示しています。駅にカーソルを合わせると駅名と路線名が表示されます。
      </p>
      <h3 className="section-title">凡例(路線カテゴリ)</h3>
      {legend.length === 0 ? (
        <p className="muted">ネットワークデータを読み込み中、または未取得です。</p>
      ) : (
        <ul className="legend-list">
          {legend.map((item) => (
            <li key={item.category} className="legend-item">
              <span className="legend-swatch" style={{ backgroundColor: item.color }} />
              <span>{item.label}</span>
              <span className="muted legend-count">{item.count} 路線</span>
            </li>
          ))}
        </ul>
      )}
      <p className="note">
        ※ 路線色はデータ由来のため、同一カテゴリ内でも路線ごとに異なります。凡例は代表色です。
      </p>
    </div>
  );
}
