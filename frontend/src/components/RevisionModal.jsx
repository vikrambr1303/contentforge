import { useEffect, useState } from "react";
import * as api from "../api/client.js";
import { useAppStore } from "../store/useAppStore.js";

export default function RevisionModal({ open, onClose, itemId, kind, hasBlogBody }) {
  const [feedback, setFeedback] = useState("");
  const [backgroundOnly, setBackgroundOnly] = useState(false);
  const [sections, setSections] = useState([]);
  const [sectionIndex, setSectionIndex] = useState(0);
  const [loadingSections, setLoadingSections] = useState(false);
  const [busy, setBusy] = useState(false);
  const addWatchedJobIds = useAppStore((s) => s.addWatchedJobIds);

  useEffect(() => {
    if (!open) return;
    setFeedback("");
    setBackgroundOnly(false);
    if (kind === "blog") {
      setLoadingSections(true);
      api.content
        .blogSections(itemId)
        .then((rows) => {
          setSections(Array.isArray(rows) ? rows : []);
          setSectionIndex(0);
        })
        .catch(() => {
          setSections([]);
        })
        .finally(() => setLoadingSections(false));
    } else {
      setSections([]);
    }
  }, [open, itemId, kind]);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  function submit(mode) {
    if (mode === "feedback" && !feedback.trim()) {
      alert("Enter feedback to apply a guided revision.");
      return;
    }
    const body = {
      mode,
      feedback: mode === "feedback" ? feedback.trim() : "",
    };
    if (kind === "blog") {
      body.blog_section_index = sectionIndex;
    } else if (kind === "social" && mode === "feedback" && backgroundOnly) {
      body.background_only = true;
    }
    setBusy(true);
    api.content
      .revise(itemId, body)
      .then((res) => {
        if (res.job_id) addWatchedJobIds([res.job_id]);
        onClose();
      })
      .catch((e) => alert(e.response?.data?.detail || e.message))
      .finally(() => setBusy(false));
  }

  const blogReady = kind !== "blog" || (!loadingSections && sections.length > 0 && hasBlogBody);

  return (
    <div className="fixed inset-0 z-[220] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Revise content">
      <button
        type="button"
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        aria-label="Close"
        onClick={onClose}
      />
      <div className="relative z-10 w-full max-w-lg rounded-2xl border border-forge-700/90 bg-forge-950 p-5 shadow-2xl ring-1 ring-white/[0.06]">
        <h3 className="text-lg font-semibold text-white">Revise {kind === "blog" ? "blog section" : "quote & image"}</h3>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed">
          {kind === "blog"
            ? "Pick a section (split on ## headings). Feedback guides the rewrite; Regenerate rolls a fresh variation for that section only."
            : "Feedback can update the quote and background, or only the background (see below). Regenerate creates a new random variation (same topic)."}
        </p>

        {kind === "blog" ? (
          <label className="block mt-4">
            <span className="cf-label mb-1.5">Section</span>
            {loadingSections ? (
              <p className="text-xs text-slate-500">Loading sections…</p>
            ) : sections.length ? (
              <select
                className="cf-select"
                value={sectionIndex}
                onChange={(e) => setSectionIndex(Number(e.target.value))}
              >
                {sections.map((s) => (
                  <option key={s.index} value={s.index}>
                    {s.label}
                  </option>
                ))}
              </select>
            ) : (
              <p className="text-xs text-amber-200/80">No sections found. Add ## headings or wait for generation to finish.</p>
            )}
            {sections[sectionIndex]?.preview ? (
              <p className="text-[11px] text-slate-500 mt-1.5 line-clamp-2">{sections[sectionIndex].preview}</p>
            ) : null}
          </label>
        ) : null}

        <label className="block mt-4">
          <span className="cf-label mb-1.5">Feedback (for “Apply feedback”)</span>
          <textarea
            className="cf-input min-h-[100px] resize-y text-sm"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="e.g. Shorter quote, warmer tone, less abstract background…"
          />
        </label>

        {kind === "social" ? (
          <label className="mt-3 flex items-start gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={backgroundOnly}
              onChange={(e) => setBackgroundOnly(e.target.checked)}
              className="mt-0.5 rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40 focus:ring-offset-0 focus:ring-offset-transparent"
            />
            <span className="text-xs text-slate-400 leading-relaxed">
              <span className="text-slate-200 font-medium">Background only</span> — keep the current quote and author;
              apply feedback only to the image (Unsplash or Stable Diffusion).
            </span>
          </label>
        ) : null}

        <div className="flex flex-wrap gap-2 justify-end mt-5">
          <button type="button" onClick={onClose} className="cf-btn-ghost text-sm" disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            onClick={() => submit("random")}
            className="cf-btn-secondary text-sm"
            disabled={busy || !blogReady}
          >
            {busy ? "…" : "Regenerate"}
          </button>
          <button
            type="button"
            onClick={() => submit("feedback")}
            className="cf-btn-primary text-sm"
            disabled={busy || !blogReady}
          >
            {busy ? "Queueing…" : "Apply feedback"}
          </button>
        </div>
        <p className="text-[11px] text-slate-500 mt-3 leading-relaxed">
          Progress appears in the job list on the library page (and Generate if you keep it open). Only one job per item at a time.
        </p>
      </div>
    </div>
  );
}
