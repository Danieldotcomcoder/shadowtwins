import { Command } from "cmdk";
import { useMemo, useState } from "react";
import type { CatalogModel } from "../../api/types";
import { fmtPerMillion, fmtTokens } from "../../lib/format";

function CompatDot({ m, profileId }: { m: CatalogModel; profileId: string }) {
  const c = m.compat?.find((x) => x.profile_id === profileId);
  if (!c) return null;
  return c.compatible ? (
    <span className="badge ok" title={c.warnings.join("; ") || "Compatible with the selected profile"}>✓ fits</span>
  ) : (
    <span className="badge bad" title={c.problems.join("; ")}>✕ {c.problems[0]?.split(":")[0] ?? "incompatible"}</span>
  );
}

function Row({ m, profileId, favorite, onToggleFav }: {
  m: CatalogModel; profileId: string; favorite: boolean; onToggleFav?: (id: string, on: boolean) => void;
}) {
  return (
    <div className="mp-row">
      <div className="mp-main">
        <div className="mp-name">
          {m.name}
          {m.is_mock && <span className="badge mock">mock</span>}
        </div>
        <div className="mp-id mono">{m.model_id}</div>
      </div>
      <div className="mp-meta">
        <span className="xsmall dim num" title="Context window">{m.context_length ? `${fmtTokens(m.context_length)} ctx` : "ctx ?"}</span>
        <span className="xsmall dim num" title="USD per million input / output tokens">
          {m.pricing_known ? `${fmtPerMillion(m.pricing.prompt)} / ${fmtPerMillion(m.pricing.completion)}` : "pricing ?"}
        </span>
        <CompatDot m={m} profileId={profileId} />
        {onToggleFav && (
          <span aria-hidden className={`mp-fav${favorite ? " on" : ""}`}
            title={favorite ? "Remove favourite" : "Add favourite"}
            onPointerDown={(e) => e.preventDefault()}
            onClick={(e) => { e.stopPropagation(); onToggleFav(m.model_id, !favorite); }}>★</span>
        )}
      </div>
    </div>
  );
}

export function ModelPicker({ models, favorites, recents, value, onChange, profileId, onToggleFav }: {
  models: CatalogModel[];
  favorites: string[];
  recents: string[];
  value: string | null;
  onChange: (id: string) => void;
  profileId: string;
  onToggleFav?: (id: string, on: boolean) => void;
}) {
  const [search, setSearch] = useState("");
  const byId = useMemo(() => new Map(models.map((m) => [m.model_id, m])), [models]);
  const favs = favorites.map((id) => byId.get(id)).filter(Boolean) as CatalogModel[];
  const recent = recents.filter((id) => !favorites.includes(id)).map((id) => byId.get(id)).filter(Boolean) as CatalogModel[];
  const sorted = useMemo(() => [...models].sort((a, b) =>
    Number(a.is_mock) - Number(b.is_mock) || a.name.localeCompare(b.name)), [models]);
  const item = (m: CatalogModel, group: string) => (
    <Command.Item key={`${group}-${m.model_id}`} value={`${group}:${m.model_id}`}
      keywords={[m.name, m.model_id]} onSelect={() => onChange(m.model_id)}
      data-selected-model={value === m.model_id ? "true" : undefined}>
      <Row m={m} profileId={profileId} favorite={favorites.includes(m.model_id)} onToggleFav={onToggleFav} />
    </Command.Item>
  );
  return (
    <Command className="mp" label="Choose a model" loop>
      <div className="mp-search">
        <span aria-hidden className="faint">⌕</span>
        <Command.Input value={search} onValueChange={setSearch} placeholder={`Search ${models.length} models by name or id…`}
          className="mp-input" />
      </div>
      <Command.List className="mp-list">
        <Command.Empty className="small dim" style={{ padding: 16 }}>No model matches “{search}”.</Command.Empty>
        {!search && favs.length > 0 && <Command.Group heading="Favourites">{favs.map((m) => item(m, "fav"))}</Command.Group>}
        {!search && recent.length > 0 && <Command.Group heading="Recent">{recent.map((m) => item(m, "recent"))}</Command.Group>}
        <Command.Group heading={search ? "Results" : "All models"}>{sorted.map((m) => item(m, "all"))}</Command.Group>
      </Command.List>
    </Command>
  );
}
