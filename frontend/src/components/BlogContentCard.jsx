import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import * as api from "../api/client.js";

function statusBadgeClass(status) {
  switch (status) {
    case "approved":
      return "bg-emerald-500/12 text-emerald-300 ring-1 ring-emerald-500/25";
    case "draft":
      return "bg-amber-500/10 text-amber-200 ring-1 ring-amber-500/20";
    case "rejected":
      return "bg-rose-500/12 text-rose-300 ring-1 ring-rose-500/25";
    case "posted":
      return "bg-sky-500/12 text-sky-200 ring-1 ring-sky-500/30";
    default:
      return "bg-forge-800 text-slate-300 ring-1 ring-forge-700/80";
  }
}

function blogTitle(md) {
  if (!md) return "Blog post";
  const m = md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : "Blog post";
}

function blogExcerpt(md) {
  if (!md) return "—";
  const lines = md.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#"));
  const t = lines.join(" ").replace(/\*\*/g, "").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  return t.length > 280 ? `${t.slice(0, 277)}…` : t || "—";
}

function diagramCount(item) {
  const j = item.blog_assets_json;
  if (Array.isArray(j) && j.length) return j.length;
  const m = (item.blog_markdown || "").match(/!\[Diagram \d+\]\(diagram_\d+\.png\)/g);
  return m ? m.length : 0;
}

/** Split markdown into alternating text and diagram image segments for the reader view. */
function splitMarkdownForReader(md) {
  const re = /!\[([^\]]*)\]\(diagram_(\d+)\.png\)/g;
  const segments = [];
  let last = 0;
  let m = re.exec(md);
  while (m !== null) {
    if (m.index > last) {
      segments.push({ type: "text", text: md.slice(last, m.index) });
    }
    segments.push({ type: "img", alt: m[1] || "Diagram", index: parseInt(m[2], 10) });
    last = m.index + m[0].length;
    m = re.exec(md);
  }
  if (last < md.length) {
    segments.push({ type: "text", text: md.slice(last) });
  }
  return segments.length ? segments : [{ type: "text", text: md }];
}

export default function BlogContentCard({ item, topic, selected, onToggle, onRefresh, onDeleted }) {
  const [edit, setEdit] = useState(false);
  const [body, setBody] = useState(item.blog_markdown || "");
  const [deleting, setDeleting] = useState(false);
  const [copyDone, setCopyDone] = useState(false);
  const [readerOpen, setReaderOpen] = useState(false);

  useEffect(() => {
    setBody(item.blog_markdown || "");
  }, [item.blog_markdown, item.id]);

  useEffect(() => {
    if (!readerOpen) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") setReaderOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [readerOpen]);

  const nDiag = diagramCount(item);
  const hasBody = Boolean(item.blog_markdown && item.blog_markdown.trim());

  function saveMarkdown() {
    api.content
      .patch(item.id, { blog_markdown: body })
      .then(() => {
        setEdit(false);
        onRefresh?.();
      })
      .catch((e) => alert(e.response?.data?.detail || e.message));
  }

  function setStatus(status) {
    api.content.patch(item.id, { status }).then(() => onRefresh?.());
  }

  function copyMarkdown() {
    const text = item.blog_markdown || "";
    if (!text) return;
    navigator.clipboard.writeText(text).then(
      () => {
        setCopyDone(true);
        setTimeout(() => setCopyDone(false), 2000);
      },
      () => alert("Could not copy to clipboard.")
    );
  }

  function deleteContent() {
    if (
      !window.confirm(
        "Delete this blog post permanently? Markdown and diagram files on disk will be removed."
      )
    ) {
      return;
    }
    setDeleting(true);
    api.content
      .remove(item.id)
      .then(() => {
        onDeleted?.(item.id);
        onRefresh?.();
      })
      .catch((e) => alert(e.response?.data?.detail || e.message))
      .finally(() => setDeleting(false));
  }

  function handleCardClick(e) {
    if (e.target.closest("a, button, input, textarea, label")) return;
    if (edit || !hasBody) return;
    setReaderOpen(true);
  }

  return (
    <article
      className={`cf-card overflow-hidden flex flex-col group hover:border-forge-700/90 transition-colors ${
        hasBody && !edit ? "cursor-pointer" : ""
      }`}
      onClick={handleCardClick}
    >
      <div className="flex items-start gap-3 p-4 border-b border-forge-800/80 bg-forge-950/40">
        <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer shrink-0">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40 focus:ring-offset-0 focus:ring-offset-transparent"
          />
          Select
        </label>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-400/90">Blog</p>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-sky-400/90 truncate">
            {topic?.name || `Topic ${item.topic_id}`}
          </p>
          <h3 className="text-base font-semibold text-white mt-1 leading-snug line-clamp-2">
            {blogTitle(item.blog_markdown)}
          </h3>
        </div>
      </div>

      <div className="p-4 space-y-3 flex-1 flex flex-col">
        {edit ? (
          <textarea
            className="cf-input min-h-[200px] resize-y font-mono text-xs leading-relaxed"
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        ) : (
          <p className="text-sm text-slate-400 leading-relaxed line-clamp-5">{blogExcerpt(item.blog_markdown)}</p>
        )}

        {nDiag > 0 && hasBody ? (
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: nDiag }, (_, i) => (
              <img
                key={i}
                src={api.content.diagramUrl(item.id, i)}
                alt=""
                className="h-16 w-auto max-w-[6rem] object-contain rounded border border-forge-800 bg-forge-950"
              />
            ))}
          </div>
        ) : null}

        {!hasBody && item.status === "draft" ? (
          <p className="text-xs text-amber-200/80">Generation in progress or failed — refresh in a moment.</p>
        ) : null}

        <span
          className={`inline-flex w-fit text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-md ${statusBadgeClass(item.status)}`}
        >
          {item.status}
        </span>

        <div className="flex flex-wrap gap-2 mt-auto pt-1">
          {edit ? (
            <>
              <button type="button" onClick={saveMarkdown} className="cf-btn-primary text-xs py-2 px-3">
                Save
              </button>
              <button type="button" onClick={() => setEdit(false)} className="cf-btn-ghost text-xs">
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => setEdit(true)} className="cf-btn-secondary text-xs py-2" disabled={!hasBody}>
                Edit markdown
              </button>
              <button
                type="button"
                onClick={copyMarkdown}
                className="cf-btn-secondary text-xs py-2"
                disabled={!hasBody}
              >
                {copyDone ? "Copied" : "Copy markdown"}
              </button>
              {hasBody ? (
                <a
                  href={api.content.downloadBlogZipUrl(item.id)}
                  className="cf-btn-ghost text-xs py-2 px-3 border border-forge-700/80 rounded-lg inline-flex items-center"
                >
                  Download ZIP
                </a>
              ) : (
                <span className="cf-btn-ghost text-xs py-2 px-3 border border-forge-700/80 rounded-lg inline-flex items-center opacity-40 cursor-not-allowed">
                  Download ZIP
                </span>
              )}
              <button type="button" onClick={() => setStatus("approved")} className="cf-btn-secondary text-xs py-2 text-emerald-200 border-emerald-900/40 bg-emerald-950/20 hover:bg-emerald-950/35">
                Approve
              </button>
              <button type="button" onClick={() => setStatus("rejected")} className="cf-btn-secondary text-xs py-2 text-rose-200 border-rose-900/40 bg-rose-950/20 hover:bg-rose-950/35">
                Reject
              </button>
              <button type="button" onClick={deleteContent} disabled={deleting} className="cf-btn-danger text-xs py-2 disabled:opacity-50">
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </>
          )}
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed border-t border-forge-800/60 pt-3">
          Click the card to read the full post. Paste into Medium or another editor: use{" "}
          <strong className="text-slate-400">Copy markdown</strong> and upload each diagram image where the{" "}
          <code className="text-slate-400">diagram_N.png</code> placeholders sit, or use{" "}
          <strong className="text-slate-400">Download ZIP</strong> for <code className="text-slate-400">post.md</code> plus PNGs.
        </p>
      </div>

      {readerOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={`blog-reader-title-${item.id}`}
            className="fixed inset-0 z-[200] flex items-center justify-center p-4 sm:p-6"
            onClick={() => setReaderOpen(false)}
          >
            <div className="absolute inset-0 bg-black/80 backdrop-blur-sm" aria-hidden />
            <div
              className="relative z-10 flex w-full max-w-3xl max-h-[min(90vh,56rem)] flex-col rounded-2xl border border-forge-700/90 bg-forge-950 shadow-2xl ring-1 ring-white/[0.06]"
              onClick={(e) => e.stopPropagation()}
            >
              <header className="flex shrink-0 items-start justify-between gap-3 border-b border-forge-800/90 px-5 py-4">
                <div className="min-w-0">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-400/90">Blog</p>
                  <h2 id={`blog-reader-title-${item.id}`} className="text-lg font-semibold text-white leading-snug pr-2">
                    {blogTitle(item.blog_markdown)}
                  </h2>
                  <p className="mt-1 text-xs text-slate-500">{topic?.name || `Topic ${item.topic_id}`}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setReaderOpen(false)}
                  className="shrink-0 rounded-lg border border-forge-600 bg-forge-900/80 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-forge-800 hover:border-forge-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50"
                >
                  Close
                </button>
              </header>
              <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
                <div className="max-w-none">
                  {splitMarkdownForReader(item.blog_markdown || "").map((seg, i) =>
                    seg.type === "text" ? (
                      <pre
                        key={i}
                        className="whitespace-pre-wrap font-sans text-[15px] leading-[1.65] text-slate-200 border-0 bg-transparent p-0 m-0"
                      >
                        {seg.text}
                      </pre>
                    ) : (
                      <figure key={i} className="my-6">
                        <img
                          src={api.content.diagramUrl(item.id, seg.index)}
                          alt={seg.alt}
                          className="max-h-[min(50vh,28rem)] w-full rounded-lg border border-forge-800 bg-forge-900/50 object-contain"
                        />
                      </figure>
                    )
                  )}
                </div>
              </div>
            </div>
          </div>,
          document.body
        )}
    </article>
  );
}
