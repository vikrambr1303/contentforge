import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import * as api from "../api/client.js";
import RevisionModal from "./RevisionModal.jsx";

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

function ImagePlaceholder() {
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center bg-gradient-to-br from-forge-800/90 via-forge-950 to-black">
      <div className="rounded-full bg-forge-800/80 p-3 ring-1 ring-white/5">
        <svg className="h-8 w-8 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.25}
            d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
          />
        </svg>
      </div>
      <p className="text-xs text-slate-500 max-w-[12rem] leading-snug">No image yet — generate or re-run image for this item.</p>
    </div>
  );
}

export default function ContentCard({
  item,
  topic,
  selected,
  onToggle,
  accounts,
  onRefresh,
  onDeleted,
}) {
  const [preview, setPreview] = useState(false);
  const [edit, setEdit] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [quote, setQuote] = useState(item.quote_text || "");
  const [accountId, setAccountId] = useState(accounts[0]?.id || "");
  const [revisionOpen, setRevisionOpen] = useState(false);

  useEffect(() => {
    if (!Array.isArray(accounts) || accounts.length === 0) return;
    setAccountId((prev) => {
      const ok =
        prev != null &&
        prev !== "" &&
        accounts.some((a) => String(a.id) === String(prev));
      return ok ? prev : accounts[0].id;
    });
  }, [accounts]);

  useEffect(() => {
    if (!preview) return;
    const onKey = (e) => {
      if (e.key === "Escape") setPreview(false);
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [preview]);

  const mediaV = item.updated_at ? encodeURIComponent(item.updated_at) : String(item.id);
  const imgSrc = item.image_path ? `/api/content/${item.id}/image?v=${mediaV}` : null;
  const vidSrc = item.video_path ? `/api/content/${item.id}/video?v=${mediaV}` : null;
  const showImage = Boolean(imgSrc) && !imgError;

  function saveQuote() {
    api.content
      .patch(item.id, { quote_text: quote, quote_author: item.quote_author })
      .then(() => {
        setEdit(false);
        onRefresh?.();
      })
      .catch((e) => alert(e.response?.data?.detail || e.message));
  }

  function setStatus(status) {
    api.content.patch(item.id, { status }).then(() => onRefresh?.());
  }

  function post() {
    if (!accountId) {
      alert("Add an account under Platforms first.");
      return;
    }
    api.platforms
      .post({ content_item_id: item.id, account_id: Number(accountId) })
      .then((r) => alert(r.ok ? "Posted" : r.error || "Failed"))
      .catch((e) => alert(e.response?.data?.detail || e.message));
  }

  function deleteContent() {
    if (
      !window.confirm(
        "Delete this content permanently? Image, video, and background files on disk will be removed."
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

  return (
    <article className="cf-card overflow-hidden flex flex-col group hover:border-forge-700/90 transition-colors">
      <div className="relative aspect-[9/16] max-h-80 bg-forge-950 ring-1 ring-inset ring-white/[0.04]">
        {showImage ? (
          <button type="button" onClick={() => setPreview(true)} className="absolute inset-0 block focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/50 focus-visible:ring-inset">
            <img
              src={imgSrc}
              alt=""
              className="w-full h-full object-cover transition duration-300 group-hover:scale-[1.02]"
              onError={() => setImgError(true)}
            />
          </button>
        ) : (
          <ImagePlaceholder />
        )}
        <label className="absolute top-2.5 left-2.5 flex items-center gap-2 rounded-lg bg-forge-950/90 px-2.5 py-1.5 text-xs text-slate-300 ring-1 ring-white/10 backdrop-blur-sm cursor-pointer hover:bg-forge-900/95">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="rounded border-forge-600 bg-forge-900 text-sky-500 focus:ring-sky-500/40 focus:ring-offset-0 focus:ring-offset-transparent"
          />
          Select
        </label>
      </div>
      <div className="p-4 space-y-3 flex-1 flex flex-col">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-sky-400/90">{topic?.name || `Topic ${item.topic_id}`}</p>
          {edit ? (
            <textarea
              className="cf-input mt-2 min-h-[88px] resize-y"
              value={quote}
              onChange={(e) => setQuote(e.target.value)}
            />
          ) : (
            <p className="mt-1.5 text-sm text-slate-100 leading-relaxed line-clamp-5">{item.quote_text || "—"}</p>
          )}
          {item.quote_author ? (
            <p className="mt-2 text-xs text-slate-500 italic">— {item.quote_author}</p>
          ) : null}
        </div>
        <span
          className={`inline-flex w-fit text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-md ${statusBadgeClass(item.status)}`}
        >
          {item.status}
        </span>
        <div className="flex flex-wrap gap-2 mt-auto pt-1">
          {edit ? (
            <>
              <button type="button" onClick={saveQuote} className="cf-btn-primary text-xs py-2 px-3">
                Save
              </button>
              <button type="button" onClick={() => setEdit(false)} className="cf-btn-ghost text-xs">
                Cancel
              </button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => setEdit(true)} className="cf-btn-secondary text-xs py-2">
                Edit quote
              </button>
              <button
                type="button"
                onClick={() => setRevisionOpen(true)}
                className="cf-btn-secondary text-xs py-2 text-violet-200 border-violet-900/40 bg-violet-950/20 hover:bg-violet-950/35"
              >
                Revise
              </button>
              <button type="button" onClick={() => setStatus("approved")} className="cf-btn-secondary text-xs py-2 text-emerald-200 border-emerald-900/40 bg-emerald-950/20 hover:bg-emerald-950/35">
                Approve
              </button>
              <button type="button" onClick={() => setStatus("rejected")} className="cf-btn-secondary text-xs py-2 text-rose-200 border-rose-900/40 bg-rose-950/20 hover:bg-rose-950/35">
                Reject
              </button>
              <button
                type="button"
                onClick={deleteContent}
                disabled={deleting}
                className="cf-btn-danger text-xs py-2 disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Delete"}
              </button>
              {item.image_path && (
                <a href={api.content.downloadImageUrl(item.id)} download className="cf-btn-ghost text-xs border border-transparent">
                  Download image
                </a>
              )}
              {item.video_path && (
                <a href={api.content.downloadVideoUrl(item.id)} download className="cf-btn-ghost text-xs border border-transparent">
                  Download video
                </a>
              )}
            </>
          )}
        </div>
        {Array.isArray(accounts) && accounts.length > 0 ? (
          <div className="flex flex-wrap gap-2 items-stretch border-t border-forge-800/80 pt-3">
            <select
              className="cf-select flex-1 min-w-[8rem] text-xs py-2"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.display_name} ({a.platform})
                </option>
              ))}
            </select>
            <button type="button" onClick={post} className="cf-btn-primary text-xs py-2 px-4 shrink-0">
              Post
            </button>
          </div>
        ) : null}
      </div>

      <RevisionModal
        open={revisionOpen}
        onClose={() => setRevisionOpen(false)}
        itemId={item.id}
        kind="social"
        hasBlogBody
      />

      {preview &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Full screen preview"
            className="fixed inset-0 z-[200] flex items-center justify-center bg-black cursor-zoom-out"
            onClick={() => setPreview(false)}
          >
            {vidSrc ? (
              <video
                src={vidSrc}
                controls
                className="max-h-full max-w-full w-auto h-auto object-contain pointer-events-auto cursor-default"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              showImage && (
                <img
                  src={imgSrc}
                  alt=""
                  className="max-h-full max-w-full w-auto h-auto object-contain select-none"
                />
              )
            )}
          </div>,
          document.body
        )}
    </article>
  );
}
