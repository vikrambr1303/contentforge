import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import * as api from "../api/client.js";

/** Voice / tone presets (values must match backend `ContentStyle`). */
const CONTENT_STYLE_OPTIONS = [
  { value: "inspirational", label: "Inspirational — uplifting, motivational" },
  { value: "educational", label: "Educational — clear, teaches something" },
  { value: "humorous", label: "Humorous — jokes, wit, light" },
  { value: "poetic", label: "Poetic — lyrical, metaphor-rich" },
  { value: "professional", label: "Professional — polished, business-appropriate" },
  { value: "conversational", label: "Conversational — friendly, like talking to a peer" },
  { value: "provocative", label: "Provocative — bold, challenges assumptions" },
  { value: "minimalist", label: "Minimalist — very short, essential words only" },
  { value: "storytelling", label: "Storytelling — narrative, scene, character" },
  { value: "authoritative", label: "Authoritative — expert, credible, instructional" },
  { value: "empathetic", label: "Empathetic — warm, validating, human" },
  { value: "journalistic", label: "Journalistic — neutral, factual, concise" },
];

/**
 * Saved verbatim to `image_style` (max 500). Tuned for SD prompts; also work as Unsplash-style keywords.
 */
const IMAGE_MOOD_PRESETS = [
  { value: "cinematic, soft light", label: "Cinematic — soft light, gentle contrast" },
  { value: "golden hour, warm tones, natural light", label: "Golden hour — warm, sun-kissed" },
  { value: "cool tones, misty, atmospheric depth", label: "Cool & atmospheric" },
  { value: "minimalist, clean, generous negative space", label: "Minimal / editorial" },
  { value: "bold colors, high contrast, graphic composition", label: "Bold & graphic" },
  { value: "soft pastel, dreamy, gentle diffusion", label: "Pastel / dreamy" },
  { value: "dark moody, low key, dramatic shadows", label: "Dark & moody" },
  { value: "bright airy, high key, soft shadows", label: "Bright & airy" },
  { value: "documentary, natural light, authentic texture", label: "Documentary / authentic" },
  { value: "abstract gradients, soft shapes, non-literal", label: "Abstract — good for quote cards" },
  { value: "nature landscape, wide serene vista", label: "Nature / landscape" },
  { value: "urban modern, architecture, clean geometry", label: "Urban / modern" },
];

const CUSTOM_IMAGE_MOOD = "__custom__";

const defaultForm = {
  name: "",
  description: "",
  style: "inspirational",
  image_style: "cinematic, soft light",
  background_source: "diffusers",
  is_active: true,
  reference_image_strength: 0.38,
};

function StyleReferenceFields({
  isUnsplash,
  hasRef,
  editing,
  form,
  setForm,
  setStyleRefFile,
  fileInputRef,
  removeReference,
}) {
  return (
    <>
      <div>
        <span className="cf-label">Style reference image (optional)</span>
        {isUnsplash ? (
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            Background source is <strong className="text-slate-400">Unsplash</strong>, so this image is{" "}
            <strong className="text-slate-400">not</strong> used for generation right now. You can still add one if you
            might switch this topic to Stable Diffusion later.
          </p>
        ) : (
          <p className="text-xs text-slate-500 mt-1 leading-relaxed">
            Upload an example background you like (abstract or scenery, no small text). With Stable Diffusion, generation
            uses <strong className="text-slate-400">image-to-image</strong> so new backgrounds follow its palette and
            mood. Tune strength: lower stays closer to your image; higher follows the text prompt more.
          </p>
        )}
      </div>
      {hasRef && (
        <div className="flex flex-wrap items-start gap-3">
          <img
            src={api.topics.referenceImageUrl(editing.id)}
            alt="Style reference"
            className="h-28 w-auto max-w-[10rem] rounded-lg object-cover ring-1 ring-white/10"
          />
          <button type="button" onClick={removeReference} className="cf-btn-danger text-xs py-2">
            Remove reference
          </button>
        </div>
      )}
      <label className="block">
        <span className="text-xs text-slate-500 mb-1.5 block">
          JPEG, PNG, or WebP · max 8MB · uploads when you click Create topic or Update topic.
        </span>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="text-xs text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-forge-800 file:px-3 file:py-1.5 file:text-sm file:text-slate-200 hover:file:bg-forge-700"
          onChange={(e) => setStyleRefFile(e.target.files?.[0] || null)}
        />
      </label>
      <label className="block max-w-xs">
        <span className="cf-label mb-1.5">Img2img strength</span>
        <input
          type="number"
          min={0.12}
          max={0.92}
          step={0.02}
          className="cf-input"
          value={form.reference_image_strength}
          onChange={(e) => setForm({ ...form, reference_image_strength: Number(e.target.value) })}
        />
        <p className="text-[11px] text-slate-500 mt-1">Try 0.30–0.45 for a strong style match.</p>
      </label>
    </>
  );
}

function imageStyleMatchesPreset(text) {
  return IMAGE_MOOD_PRESETS.some((o) => o.value === text);
}

export default function TopicForm({ onCreated, editing, onDoneEdit }) {
  const [form, setForm] = useState(defaultForm);
  /** When true, show custom textarea even if text equals a preset (user chose "Custom…"). */
  const [imageMoodUseCustom, setImageMoodUseCustom] = useState(false);
  const [saving, setSaving] = useState(false);
  const [styleRefFile, setStyleRefFile] = useState(null);
  const fileInputRef = useRef(null);

  const [refineOpen, setRefineOpen] = useState(false);
  const [scopeWhole, setScopeWhole] = useState(false);
  const [scopeDesc, setScopeDesc] = useState(true);
  const [scopeImg, setScopeImg] = useState(false);
  const [scopeStyle, setScopeStyle] = useState(false);
  const [refineNote, setRefineNote] = useState("");
  const [refineLoading, setRefineLoading] = useState(false);
  const [refineErr, setRefineErr] = useState(null);
  const [refineResult, setRefineResult] = useState(null);

  useEffect(() => {
    if (editing) {
      const img = editing.image_style || "";
      setForm({
        name: editing.name,
        description: editing.description || "",
        style: editing.style,
        image_style: img,
        background_source: editing.background_source || "diffusers",
        is_active: editing.is_active,
        reference_image_strength:
          editing.reference_image_strength != null ? editing.reference_image_strength : 0.38,
      });
      setImageMoodUseCustom(!imageStyleMatchesPreset(img));
    } else {
      setForm(defaultForm);
      setImageMoodUseCustom(false);
    }
    setStyleRefFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [editing]);

  useEffect(() => {
    if (!refineOpen) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [refineOpen]);

  useEffect(() => {
    if (!refineOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") setRefineOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [refineOpen]);

  function openRefine() {
    setRefineErr(null);
    setRefineResult(null);
    setRefineOpen(true);
  }

  function buildRefineScopes() {
    if (scopeWhole) return ["whole"];
    const s = [];
    if (scopeDesc) s.push("description");
    if (scopeImg) s.push("image_style");
    if (scopeStyle) s.push("style");
    return s;
  }

  function setWhole(v) {
    setScopeWhole(v);
    if (v) {
      setScopeDesc(false);
      setScopeImg(false);
      setScopeStyle(false);
    }
  }

  function runRefine() {
    const scopes = buildRefineScopes();
    if (scopes.length === 0) {
      setRefineErr("Select at least one area to improve.");
      return;
    }
    setRefineLoading(true);
    setRefineErr(null);
    api.topics
      .refinePreview({
        name: form.name,
        description: form.description || null,
        style: form.style,
        image_style: form.image_style,
        background_source: form.background_source,
        scopes,
        user_note: refineNote.trim() || null,
      })
      .then(setRefineResult)
      .catch((err) => {
        const d = err.response?.data?.detail;
        let msg = err.message || "Request failed";
        if (typeof d === "string") msg = d;
        else if (Array.isArray(d)) msg = d.map((x) => (x && typeof x === "object" && x.msg ? x.msg : String(x))).join(" ");
        else if (d != null) msg = typeof d === "object" ? JSON.stringify(d) : String(d);
        setRefineErr(msg);
      })
      .finally(() => setRefineLoading(false));
  }

  function applySuggestion(field) {
    if (!refineResult) return;
    if (field === "description" && refineResult.description) {
      setForm((f) => ({ ...f, description: refineResult.description.text }));
    }
    if (field === "image_style" && refineResult.image_style) {
      const t = refineResult.image_style.text;
      setForm((f) => ({ ...f, image_style: t }));
      setImageMoodUseCustom(!imageStyleMatchesPreset(t));
    }
    if (field === "style" && refineResult.style) {
      setForm((f) => ({ ...f, style: refineResult.style.value }));
    }
  }

  function applyAllSuggestions() {
    if (!refineResult) return;
    const nextImg = refineResult.image_style?.text;
    setForm((f) => ({
      ...f,
      ...(refineResult.description ? { description: refineResult.description.text } : {}),
      ...(refineResult.image_style ? { image_style: refineResult.image_style.text } : {}),
      ...(refineResult.style ? { style: refineResult.style.value } : {}),
    }));
    if (nextImg !== undefined) setImageMoodUseCustom(!imageStyleMatchesPreset(nextImg));
    setRefineOpen(false);
  }

  function removeReference(e) {
    e.preventDefault();
    if (!editing) return;
    api.topics
      .deleteReferenceImage(editing.id)
      .then((row) => onCreated?.(row))
      .catch((err) => alert(err.response?.data?.detail || err.message));
  }

  function submit(e) {
    e.preventDefault();
    setSaving(true);
    const body = {
      name: form.name,
      description: form.description,
      style: form.style,
      image_style: form.image_style,
      background_source: form.background_source,
      is_active: form.is_active,
      reference_image_strength: form.reference_image_strength,
    };
    const p = editing ? api.topics.update(editing.id, body) : api.topics.create(body);
    p.then(async (row) => {
      let latest = row;
      if (styleRefFile) {
        latest = await api.topics.uploadReferenceImage(row.id, styleRefFile);
      }
      setStyleRefFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onCreated?.(latest);
      onDoneEdit?.();
      setForm(defaultForm);
      setImageMoodUseCustom(false);
    })
      .catch((err) => alert(err.response?.data?.detail || err.message))
      .finally(() => setSaving(false));
  }

  const hasRef = Boolean(editing?.style_reference_relpath);
  const isUnsplash = form.background_source === "unsplash";
  const imageMoodSelectValue =
    imageMoodUseCustom || !imageStyleMatchesPreset(form.image_style) ? CUSTOM_IMAGE_MOOD : form.image_style;

  const styleRefProps = {
    isUnsplash,
    hasRef,
    editing,
    form,
    setForm,
    setStyleRefFile,
    fileInputRef,
    removeReference,
  };

  const hasAnySuggestion =
    refineResult &&
    (refineResult.description || refineResult.image_style || refineResult.style);

  const refinePanel =
    refineOpen &&
    typeof document !== "undefined" &&
    createPortal(
      <div className="fixed inset-0 z-[300] flex justify-end" role="dialog" aria-modal="true" aria-label="Improve topic">
        <button
          type="button"
          className="absolute inset-0 bg-black/70 backdrop-blur-sm"
          aria-label="Close"
          onClick={() => setRefineOpen(false)}
        />
        <div className="relative z-10 flex h-full w-full max-w-lg flex-col border-l border-forge-800 bg-forge-950 shadow-2xl shadow-black/40">
          <div className="flex items-start justify-between gap-3 border-b border-forge-800 px-5 py-4 shrink-0">
            <div>
              <h3 className="text-lg font-semibold text-white">Improve this topic</h3>
              <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                Suggestions are previews until you apply them. Nothing is saved until you create or update the topic.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setRefineOpen(false)}
              className="cf-btn-ghost text-sm text-slate-400 hover:text-white shrink-0"
            >
              Close
            </button>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
            <div className="space-y-2">
              <span className="cf-label">What to improve</span>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scopeWhole}
                  onChange={(e) => setWhole(e.target.checked)}
                  className="rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40"
                />
                Whole brief (balanced pass)
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scopeDesc}
                  disabled={scopeWhole}
                  onChange={(e) => {
                    setScopeDesc(e.target.checked);
                    if (e.target.checked) setScopeWhole(false);
                  }}
                  className="rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40 disabled:opacity-40"
                />
                Description
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scopeImg}
                  disabled={scopeWhole}
                  onChange={(e) => {
                    setScopeImg(e.target.checked);
                    if (e.target.checked) setScopeWhole(false);
                  }}
                  className="rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40 disabled:opacity-40"
                />
                Image mood / visual style
              </label>
              <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={scopeStyle}
                  disabled={scopeWhole}
                  onChange={(e) => {
                    setScopeStyle(e.target.checked);
                    if (e.target.checked) setScopeWhole(false);
                  }}
                  className="rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40 disabled:opacity-40"
                />
                Content style
              </label>
            </div>
            <label className="block">
              <span className="cf-label mb-1.5">Extra instructions (optional)</span>
              <textarea
                className="cf-input min-h-[72px] resize-y text-sm"
                value={refineNote}
                onChange={(e) => setRefineNote(e.target.value)}
                placeholder="e.g. Warmer tone, more clinical, shorter description…"
              />
            </label>
            {refineErr ? (
              <div className="rounded-lg border border-red-900/50 bg-red-950/30 px-3 py-2 text-sm text-red-200">{refineErr}</div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={runRefine}
                disabled={refineLoading || buildRefineScopes().length === 0}
                className="cf-btn-primary text-sm"
              >
                {refineLoading ? "Generating…" : "Generate suggestions"}
              </button>
              {refineResult ? (
                <button type="button" onClick={runRefine} disabled={refineLoading} className="cf-btn-secondary text-sm">
                  Regenerate
                </button>
              ) : null}
            </div>
            {refineResult && !hasAnySuggestion && !refineLoading ? (
              <p className="text-sm text-slate-500">No suggestions returned. Try another scope or add a note.</p>
            ) : null}
            {refineResult?.description ? (
              <div className="rounded-xl border border-forge-800/80 bg-forge-950/50 p-4 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-sky-400/90">Description</span>
                  <span className="text-[10px] text-slate-500 tabular-nums">{refineResult.description.text.length} chars</span>
                </div>
                {refineResult.description.rationale ? (
                  <details className="text-xs text-slate-500">
                    <summary className="cursor-pointer text-slate-400 hover:text-slate-300">Why this change</summary>
                    <p className="mt-1 leading-relaxed">{refineResult.description.rationale}</p>
                  </details>
                ) : null}
                <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{refineResult.description.text}</p>
                <button type="button" onClick={() => applySuggestion("description")} className="cf-btn-secondary text-xs">
                  Apply description
                </button>
              </div>
            ) : null}
            {refineResult?.image_style ? (
              <div className="rounded-xl border border-forge-800/80 bg-forge-950/50 p-4 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold uppercase tracking-wide text-sky-400/90">Image mood / visual style</span>
                  <span className="text-[10px] text-slate-500 tabular-nums">{refineResult.image_style.text.length}/500</span>
                </div>
                {refineResult.image_style.rationale ? (
                  <details className="text-xs text-slate-500">
                    <summary className="cursor-pointer text-slate-400 hover:text-slate-300">Why this change</summary>
                    <p className="mt-1 leading-relaxed">{refineResult.image_style.rationale}</p>
                  </details>
                ) : null}
                <p className="text-sm text-slate-200">{refineResult.image_style.text}</p>
                <button type="button" onClick={() => applySuggestion("image_style")} className="cf-btn-secondary text-xs">
                  Apply image style
                </button>
              </div>
            ) : null}
            {refineResult?.style ? (
              <div className="rounded-xl border border-forge-800/80 bg-forge-950/50 p-4 space-y-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-sky-400/90">Content style</span>
                {refineResult.style.rationale ? (
                  <details className="text-xs text-slate-500">
                    <summary className="cursor-pointer text-slate-400 hover:text-slate-300">Why this change</summary>
                    <p className="mt-1 leading-relaxed">{refineResult.style.rationale}</p>
                  </details>
                ) : null}
                <p className="text-sm text-slate-200">
                  {CONTENT_STYLE_OPTIONS.find((o) => o.value === refineResult.style.value)?.label ?? refineResult.style.value}
                </p>
                <button type="button" onClick={() => applySuggestion("style")} className="cf-btn-secondary text-xs">
                  Apply content style
                </button>
              </div>
            ) : null}
            {hasAnySuggestion ? (
              <button type="button" onClick={applyAllSuggestions} className="cf-btn-primary w-full text-sm">
                Apply all & close
              </button>
            ) : null}
          </div>
        </div>
      </div>,
      document.body
    );

  return (
    <>
      <form onSubmit={submit} className="cf-card p-5 sm:p-6 space-y-5">
        <h2 className="text-lg font-semibold text-white">{editing ? "Edit topic" : "New topic"}</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="block sm:col-span-2">
            <span className="cf-label mb-1.5">Name</span>
            <input
              className="cf-input"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="cf-label mb-1.5">Description</span>
            <textarea
              className="cf-input min-h-[80px] resize-y"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="cf-label mb-1.5">Content style</span>
            <select className="cf-select" value={form.style} onChange={(e) => setForm({ ...form, style: e.target.value })}>
              {!CONTENT_STYLE_OPTIONS.some((o) => o.value === form.style) && form.style ? (
                <option value={form.style}>Custom: {form.style}</option>
              ) : null}
              {CONTENT_STYLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              Guides quote, caption, and blog voice. Refine with AI can suggest a different preset from this list.
            </p>
          </label>

          <label className="block sm:col-span-2">
            <span className="cf-label mb-1.5">Background images</span>
            <select
              className="cf-select"
              value={form.background_source}
              onChange={(e) => setForm({ ...form, background_source: e.target.value })}
            >
              <option value="diffusers">Stable Diffusion (model path from Settings)</option>
              <option value="unsplash">Unsplash (stock photos from the web)</option>
            </select>
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              Unsplash requires <code className="text-slate-400">UNSPLASH_ACCESS_KEY</code> in{" "}
              <code className="text-slate-400">.env</code>. Stable Diffusion uses the diffusers path in Settings. Style
              reference (below, Advanced) applies only to Stable Diffusion.
            </p>
          </label>

          <details className="sm:col-span-2 group rounded-xl border border-forge-800/80 bg-forge-950/25 open:bg-forge-950/35 ring-1 ring-transparent open:ring-white/[0.04]">
            <summary className="cursor-pointer list-none px-4 py-3.5 text-sm font-medium text-slate-200 select-none flex items-center justify-between gap-3 [&::-webkit-details-marker]:hidden">
              <span>Advanced — style reference image</span>
              <span
                className="text-slate-500 text-[10px] uppercase tracking-wider shrink-0 transition-transform group-open:rotate-180"
                aria-hidden
              >
                ▼
              </span>
            </summary>
            <div className="px-4 pb-4 pt-1 space-y-3 border-t border-forge-800/60">
              <StyleReferenceFields {...styleRefProps} />
            </div>
          </details>

          <div className="block sm:col-span-2 space-y-2">
            <label className="block">
              <span className="cf-label mb-1.5">Image mood / visual style</span>
              <select
                className="cf-select"
                value={imageMoodSelectValue}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === CUSTOM_IMAGE_MOOD) {
                    setImageMoodUseCustom(true);
                  } else {
                    setImageMoodUseCustom(false);
                    setForm({ ...form, image_style: v });
                  }
                }}
              >
                {IMAGE_MOOD_PRESETS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
                <option value={CUSTOM_IMAGE_MOOD}>Custom…</option>
              </select>
            </label>
            {imageMoodSelectValue === CUSTOM_IMAGE_MOOD ? (
              <label className="block">
                <span className="text-xs text-slate-500 mb-1.5 block">
                  Your text (Stable Diffusion: lighting, palette, lens mood. Unsplash: short keywords.) ·{" "}
                  {form.image_style.length}/500
                </span>
                <textarea
                  className="cf-input min-h-[72px] resize-y text-sm"
                  value={form.image_style}
                  maxLength={500}
                  onChange={(e) => setForm({ ...form, image_style: e.target.value })}
                  placeholder="e.g. muted teal and amber, foggy coastline, 35mm grain"
                />
              </label>
            ) : (
              <p className="text-xs text-slate-500 leading-relaxed">
                {isUnsplash
                  ? "Used as a mood keyword layer on top of Unsplash search. Style reference (Advanced) does not apply."
                  : "Combined with the worker image step (and your Advanced reference, if set). Choose Custom for full control."}
              </p>
            )}
          </div>

          <label className="flex items-center gap-3 sm:col-span-2 text-sm text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="rounded border-forge-600 text-sky-500 focus:ring-sky-500/40"
            />
            Active for generation
          </label>
        </div>
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="submit" disabled={saving} className="cf-btn-primary">
            {saving ? "Saving…" : editing ? "Update topic" : "Create topic"}
          </button>
          <button type="button" onClick={openRefine} className="cf-btn-secondary">
            Refine with AI
          </button>
          {onDoneEdit ? (
            <button
              type="button"
              onClick={() => {
                setForm(defaultForm);
                setImageMoodUseCustom(false);
                setStyleRefFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
                onDoneEdit();
              }}
              className="cf-btn-secondary"
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>
      {refinePanel}
    </>
  );
}
