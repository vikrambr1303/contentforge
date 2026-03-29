import { useCallback, useEffect, useMemo, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";

/** Common worker mount targets; pick one or use Custom. */
const DIFFUSERS_PATH_PRESETS = [
  { path: "/models/sd15", label: "Host ./models/sd15 → /models/sd15" },
  { path: "/models/stable-diffusion", label: "/models/stable-diffusion (default layout)" },
];

function formatBytes(n) {
  if (n == null || !Number.isFinite(n) || n < 0) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  const shown = v < 10 && i > 0 ? v.toFixed(1) : Math.round(v);
  return `${shown} ${units[i]}`;
}

function formatLoadError(err) {
  if (err?.response?.data?.detail != null) {
    const d = err.response.data.detail;
    return typeof d === "string" ? d : JSON.stringify(d);
  }
  if (err?.code === "ECONNABORTED") {
    return "Request timed out — is the API running and reachable?";
  }
  if (err?.message === "Network Error" || err?.code === "ERR_NETWORK") {
    return "Could not reach the API. Use the Vite dev server (with proxy) or ensure /api is forwarded to the backend.";
  }
  return err?.message || "Failed to load settings.";
}

const CUSTOM_SD = "__custom_sd__";

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [models, setModels] = useState([]);
  const [modelsError, setModelsError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshingModels, setRefreshingModels] = useState(false);
  /** User picked "Custom…" while path still matched a preset — keep showing custom field. */
  const [sdForceCustom, setSdForceCustom] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    Promise.all([
      api.settings.get().then(setSettings),
      api.settings
        .llmModels()
        .then((data) => {
          setModels(data);
          setModelsError(null);
        })
        .catch((err) => {
          setModels([]);
          setModelsError(formatLoadError(err));
        }),
    ])
      .catch((err) => {
        setSettings(null);
        setLoadError(formatLoadError(err));
      })
      .finally(() => setLoading(false));
  }, []);

  const refreshModelsOnly = useCallback(() => {
    setRefreshingModels(true);
    setModelsError(null);
    api.settings
      .llmModels()
      .then((data) => {
        setModels(data);
        setModelsError(null);
      })
      .catch((err) => {
        setModels([]);
        setModelsError(formatLoadError(err));
      })
      .finally(() => setRefreshingModels(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const modelNames = useMemo(() => {
    const raw = models.map((m) => m.name || m.model).filter(Boolean);
    return [...new Set(raw)].sort((a, b) => a.localeCompare(b));
  }, [models]);

  /** Normalized rows from Ollama `GET /api/tags` → `models` array. */
  const ollamaModelRows = useMemo(() => {
    return models
      .map((m) => {
        const name = String(m.name || m.model || "").trim();
        if (!name) return null;
        const size = typeof m.size === "number" ? m.size : null;
        const modifiedLabel = m.modified_at
          ? new Date(m.modified_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })
          : "—";
        const d = m.details && typeof m.details === "object" ? m.details : {};
        const detailShort = [d.parameter_size, d.quantization_level].filter(Boolean).join(" · ");
        return {
          name,
          sizeLabel: formatBytes(size),
          modifiedLabel,
          detailShort,
        };
      })
      .filter(Boolean)
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [models]);

  const diffusersPathMatchesPreset = useMemo(() => {
    const p = settings?.diffusers_model_path;
    if (p == null || p === "") return false;
    return DIFFUSERS_PATH_PRESETS.some((x) => x.path === p);
  }, [settings?.diffusers_model_path]);

  const diffusersSelectValue = useMemo(() => {
    if (!settings?.diffusers_model_path) return CUSTOM_SD;
    return sdForceCustom || !diffusersPathMatchesPreset ? CUSTOM_SD : settings.diffusers_model_path;
  }, [settings, sdForceCustom, diffusersPathMatchesPreset]);

  function save(e) {
    e.preventDefault();
    if (!settings) return;
    setSaving(true);
    api.settings
      .patch({
        ollama_model: settings.ollama_model,
        diffusers_model_path: settings.diffusers_model_path,
        default_image_style: settings.default_image_style,
        caption_cta: settings.caption_cta,
        generation_retry_limit: Number(settings.generation_retry_limit ?? 2),
      })
      .then(setSettings)
      .catch((err) => alert(err.response?.data?.detail || err.message))
      .finally(() => setSaving(false));
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Settings" subtitle="Models and generation defaults." />
        <p className="text-slate-500 text-sm">Loading settings…</p>
      </div>
    );
  }

  if (loadError || !settings) {
    return (
      <div className="space-y-6 max-w-2xl">
        <PageHeader title="Settings" subtitle="Models and generation defaults." />
        <div className="rounded-2xl border border-red-900/50 bg-red-950/25 px-5 py-4 text-sm text-red-200 ring-1 ring-red-500/10">
          <p className="font-medium text-red-100">Could not load settings</p>
          <p className="mt-2 text-red-200/90 leading-relaxed">{loadError || "Unknown error."}</p>
        </div>
        <button type="button" onClick={load} className="cf-btn-primary">
          Retry
        </button>
      </div>
    );
  }

  const ollamaDatalistId = "settings-ollama-models";

  return (
    <div className="space-y-8 max-w-2xl">
      <PageHeader
        title="Settings"
        subtitle="Pick your Ollama LLM and Stable Diffusion weights path. Each topic can still choose Unsplash vs SD for backgrounds."
      />

      <form onSubmit={save} className="cf-card p-5 sm:p-6 space-y-6">
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-200">Language model (Ollama)</h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            Used for quotes, captions, blog drafts, SD prompt enrichment, Unsplash query text, and topic refine. The list
            below is loaded from Ollama&apos;s <code className="text-slate-400">/api/tags</code> (models already pulled on
            this machine). Install more with{" "}
            <code className="text-slate-400">docker compose exec ollama ollama pull &lt;name&gt;</code>, then refresh.
          </p>
          <label className="block">
            <span className="cf-label mb-1.5">Active model name</span>
            <input
              className="cf-input font-mono text-sm"
              list={ollamaDatalistId}
              value={settings.ollama_model}
              maxLength={100}
              onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
              placeholder="e.g. llama3.2 or llama3.2:latest"
            />
            <datalist id={ollamaDatalistId}>
              {modelNames.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={refreshModelsOnly}
              disabled={refreshingModels}
              className="cf-btn-secondary text-sm"
            >
              {refreshingModels ? "Refreshing…" : "Refresh from Ollama"}
            </button>
            {modelsError ? (
              <span className="text-xs text-amber-400/90 max-w-md">{modelsError}</span>
            ) : modelNames.length ? (
              <span className="text-xs text-slate-500">{modelNames.length} installed</span>
            ) : (
              <span className="text-xs text-slate-500">No models reported — check Ollama URL or pull a model</span>
            )}
          </div>

          <div className="space-y-2">
            <span className="cf-label">Installed models</span>
            {modelsError ? (
              <p className="text-xs text-amber-400/90 leading-relaxed">
                Could not load the list — see the message next to Refresh. Fix <code className="text-slate-400">OLLAMA_BASE_URL</code>{" "}
                or ensure the Ollama container is running.
              </p>
            ) : ollamaModelRows.length === 0 ? (
              <p className="text-xs text-slate-500 leading-relaxed rounded-lg border border-forge-800/80 bg-forge-950/30 px-3 py-3">
                Ollama returned no models. From the host, run e.g.{" "}
                <code className="text-slate-400">docker compose exec ollama ollama pull llama3.2</code> then click
                Refresh.
              </p>
            ) : (
              <ul className="max-h-60 overflow-y-auto rounded-xl border border-forge-800/80 bg-forge-950/40 divide-y divide-forge-800/60 ring-1 ring-inset ring-white/[0.03]">
                {ollamaModelRows.map((row) => {
                  const selected = settings.ollama_model === row.name;
                  return (
                    <li key={row.name}>
                      <button
                        type="button"
                        onClick={() => setSettings({ ...settings, ollama_model: row.name })}
                        className={`w-full text-left px-3 py-2.5 sm:px-4 sm:py-3 transition hover:bg-forge-900/55 ${
                          selected ? "bg-sky-500/[0.08] ring-1 ring-inset ring-sky-500/25" : ""
                        }`}
                      >
                        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                          <span className="font-mono text-sm text-sky-200/95">{row.name}</span>
                          <span className="text-[11px] text-slate-500 tabular-nums shrink-0">
                            {row.sizeLabel}
                            <span className="text-slate-600 mx-1">·</span>
                            {row.modifiedLabel}
                          </span>
                        </div>
                        {row.detailShort ? (
                          <p className="text-[11px] text-slate-500 mt-1 font-medium tracking-wide">{row.detailShort}</p>
                        ) : null}
                        {selected ? (
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-sky-400/90 mt-1.5">
                            Selected — Save settings to persist
                          </p>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="space-y-3 border-t border-forge-800/80 pt-5">
          <h3 className="text-sm font-semibold text-slate-200">Image model (Stable Diffusion)</h3>
          <p className="text-xs text-slate-500 leading-relaxed">
            Diffusers checkpoint directory <strong className="text-slate-400">inside the worker container</strong>. Topics
            with “Stable Diffusion” backgrounds use this path.
          </p>
          <label className="block">
            <span className="cf-label mb-1.5">Common paths</span>
            <select
              className="cf-select"
              value={diffusersSelectValue}
              onChange={(e) => {
                const v = e.target.value;
                if (v === CUSTOM_SD) {
                  setSdForceCustom(true);
                  return;
                }
                setSdForceCustom(false);
                setSettings({ ...settings, diffusers_model_path: v });
              }}
            >
              {DIFFUSERS_PATH_PRESETS.map((x) => (
                <option key={x.path} value={x.path}>
                  {x.label}
                </option>
              ))}
              <option value={CUSTOM_SD}>Custom path…</option>
            </select>
          </label>
          {diffusersSelectValue === CUSTOM_SD ? (
            <label className="block">
              <span className="cf-label mb-1.5">Custom path (container)</span>
              <input
                className="cf-input font-mono text-xs"
                value={settings.diffusers_model_path}
                onChange={(e) => setSettings({ ...settings, diffusers_model_path: e.target.value })}
                placeholder="/path/to/diffusers/model"
              />
            </label>
          ) : null}
        </div>
        <div className="space-y-4 border-t border-forge-800/80 pt-5">
          <h3 className="text-sm font-semibold text-slate-200">Defaults</h3>
          <label className="block">
            <span className="cf-label mb-1.5">Default image visual style</span>
            <input
              className="cf-input"
              value={settings.default_image_style}
              onChange={(e) => setSettings({ ...settings, default_image_style: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="cf-label mb-1.5">Caption call-to-action</span>
            <input
              className="cf-input"
              value={settings.caption_cta}
              onChange={(e) => setSettings({ ...settings, caption_cta: e.target.value })}
            />
          </label>
          <label className="block max-w-xs">
            <span className="cf-label mb-1.5">Generation retries on failure</span>
            <input
              type="number"
              min={0}
              max={10}
              className="cf-input"
              value={settings.generation_retry_limit ?? 2}
              onChange={(e) =>
                setSettings({ ...settings, generation_retry_limit: Number(e.target.value) })
              }
            />
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              How many times the worker may run again after a failed quote, image, or full pipeline step (0 = one
              attempt only; 2 = up to 3 tries total). Does not apply if the worker process is killed (e.g. OOM).
            </p>
          </label>
          <button type="submit" disabled={saving} className="cf-btn-primary">
            {saving ? "Saving…" : "Save settings"}
          </button>
        </div>
      </form>
    </div>
  );
}
