import { useCallback, useEffect, useState } from "react";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";

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

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [models, setModels] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    setLoadError(null);
    Promise.all([
      api.settings.get().then(setSettings),
      api.settings.llmModels().then(setModels).catch(() => setModels([])),
    ])
      .catch((err) => {
        setSettings(null);
        setLoadError(formatLoadError(err));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
        background_source: settings.background_source || "diffusers",
      })
      .then(setSettings)
      .catch((err) => alert(err.response?.data?.detail || err.message))
      .finally(() => setSaving(false));
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <PageHeader title="Settings" subtitle="Models, background source, and defaults." />
        <p className="text-slate-500 text-sm">Loading settings…</p>
      </div>
    );
  }

  if (loadError || !settings) {
    return (
      <div className="space-y-6 max-w-xl">
        <PageHeader title="Settings" subtitle="Models, background source, and defaults." />
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

  const modelNames = models.map((m) => m.name || m.model).filter(Boolean);

  return (
    <div className="space-y-8 max-w-xl">
      <PageHeader
        title="Settings"
        subtitle="Ollama, background images (Stable Diffusion or Unsplash), and generation defaults."
      />

      <form onSubmit={save} className="cf-card p-5 sm:p-6 space-y-5">
        <label className="block">
          <span className="cf-label mb-1.5">Background source</span>
          <select
            className="cf-select"
            value={settings.background_source || "diffusers"}
            onChange={(e) => setSettings({ ...settings, background_source: e.target.value })}
          >
            <option value="diffusers">Stable Diffusion (local model)</option>
            <option value="unsplash">Unsplash (stock photos from the web)</option>
          </select>
          <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
            Unsplash requires <code className="text-slate-400">UNSPLASH_ACCESS_KEY</code> in{" "}
            <code className="text-slate-400">.env</code> (create a free app at unsplash.com/developers). Topic
            style reference images only apply to Stable Diffusion.
          </p>
        </label>
        <label className="block">
          <span className="cf-label mb-1.5">Ollama model</span>
          <select
            className="cf-select"
            value={settings.ollama_model}
            onChange={(e) => setSettings({ ...settings, ollama_model: e.target.value })}
          >
            <option value={settings.ollama_model}>{settings.ollama_model}</option>
            {modelNames
              .filter((m) => m !== settings.ollama_model)
              .map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
          </select>
          <p className="text-xs text-slate-500 mt-1.5">Populated from Ollama when reachable.</p>
        </label>
        <label className="block">
          <span className="cf-label mb-1.5">Diffusers model path (container)</span>
          <input
            className="cf-input font-mono text-xs"
            value={settings.diffusers_model_path}
            onChange={(e) => setSettings({ ...settings, diffusers_model_path: e.target.value })}
          />
        </label>
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
      </form>
    </div>
  );
}
