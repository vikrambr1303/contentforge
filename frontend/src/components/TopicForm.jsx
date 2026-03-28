import { useEffect, useRef, useState } from "react";
import * as api from "../api/client.js";

const defaultForm = {
  name: "",
  description: "",
  style: "inspirational",
  image_style: "cinematic, soft light",
  target_count: 10,
  is_active: true,
  reference_image_strength: 0.38,
};

export default function TopicForm({ onCreated, editing, onDoneEdit }) {
  const [form, setForm] = useState(defaultForm);
  const [saving, setSaving] = useState(false);
  const [styleRefFile, setStyleRefFile] = useState(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    if (editing) {
      setForm({
        name: editing.name,
        description: editing.description || "",
        style: editing.style,
        image_style: editing.image_style,
        target_count: editing.target_count,
        is_active: editing.is_active,
        reference_image_strength:
          editing.reference_image_strength != null ? editing.reference_image_strength : 0.38,
      });
    } else {
      setForm(defaultForm);
    }
    setStyleRefFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, [editing]);

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
      target_count: form.target_count,
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
    })
      .catch((err) => alert(err.response?.data?.detail || err.message))
      .finally(() => setSaving(false));
  }

  const hasRef = Boolean(editing?.style_reference_relpath);

  return (
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
        <label className="block">
          <span className="cf-label mb-1.5">Content style</span>
          <select className="cf-select" value={form.style} onChange={(e) => setForm({ ...form, style: e.target.value })}>
            <option value="inspirational">inspirational</option>
            <option value="educational">educational</option>
            <option value="humorous">humorous</option>
            <option value="poetic">poetic</option>
          </select>
        </label>
        <label className="block">
          <span className="cf-label mb-1.5">Target count</span>
          <input
            type="number"
            min={0}
            className="cf-input"
            value={form.target_count}
            onChange={(e) => setForm({ ...form, target_count: Number(e.target.value) })}
          />
        </label>
        <label className="block sm:col-span-2">
          <span className="cf-label mb-1.5">Image mood / visual style (text prompt hint)</span>
          <input
            className="cf-input"
            value={form.image_style}
            onChange={(e) => setForm({ ...form, image_style: e.target.value })}
          />
        </label>

        <div className="sm:col-span-2 rounded-xl border border-forge-800/80 bg-forge-950/35 p-4 space-y-3">
          <div>
            <span className="cf-label">Style reference image (optional)</span>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">
              Upload an example background you like (abstract or scenery, no small text). Generation uses Stable Diffusion{" "}
              <strong className="text-slate-400">image-to-image</strong> so new backgrounds follow its palette and mood.
              Tune strength: lower stays closer to your image; higher follows the text prompt more.
            </p>
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
        {editing && (
          <button type="button" onClick={onDoneEdit} className="cf-btn-secondary">
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
