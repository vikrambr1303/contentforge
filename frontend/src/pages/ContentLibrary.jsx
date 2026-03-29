import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import BlogContentCard from "../components/BlogContentCard.jsx";
import ContentCard from "../components/ContentCard.jsx";
import GenerationStatus from "../components/GenerationStatus.jsx";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";
import { JOB_DONE_EVENT } from "../realtime.js";
import { useAppStore } from "../store/useAppStore.js";

export default function ContentLibrary() {
  const [items, setItems] = useState([]);
  const [topics, setTopics] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [topicFilter, setTopicFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [zipModal, setZipModal] = useState(false);
  const [includeVideo, setIncludeVideo] = useState(false);
  const [zipBusy, setZipBusy] = useState(false);
  const watchedJobIds = useAppStore((s) => s.watchedJobIds);
  const clearWatchedJobIds = useAppStore((s) => s.clearWatchedJobIds);

  const topicMap = useMemo(() => Object.fromEntries(topics.map((t) => [t.id, t])), [topics]);

  const load = useCallback(() => {
    api.platforms.accounts().then(setAccounts);
    api.content
      .list({
        topic_id: topicFilter ? Number(topicFilter) : undefined,
        status: statusFilter || undefined,
        kind: kindFilter || undefined,
        limit: 50,
      })
      .then(setItems);
  }, [topicFilter, statusFilter, kindFilter]);

  useEffect(() => {
    api.topics.list().then(setTopics);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onJobDone = () => load();
    window.addEventListener(JOB_DONE_EVENT, onJobDone);
    return () => window.removeEventListener(JOB_DONE_EVENT, onJobDone);
  }, [load]);

  function toggle(id) {
    setSelected((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  function clearSelectionFor(id) {
    setSelected((prev) => {
      const n = new Set(prev);
      n.delete(id);
      return n;
    });
  }

  function deleteSelected() {
    const ids = [...selected];
    if (!ids.length) return;
    if (
      !window.confirm(
        `Delete ${ids.length} item(s) permanently? Image, video, and background files will be removed.`
      )
    ) {
      return;
    }
    (async () => {
      try {
        for (const id of ids) {
          await api.content.remove(id);
        }
        setSelected(new Set());
        load();
      } catch (e) {
        alert(e.response?.data?.detail || e.message);
        load();
      }
    })();
  }

  function downloadZip() {
    const ids = [...selected];
    if (!ids.length) return;
    setZipBusy(true);
    api.content
      .batchZip(ids, includeVideo)
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "contentforge_export.zip";
        a.click();
        URL.revokeObjectURL(url);
        setZipModal(false);
      })
      .catch((e) => alert(e.message))
      .finally(() => setZipBusy(false));
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Content Library"
        subtitle="Social quote cards and blog posts (Markdown + diagrams). Filter by type, then copy or download for Medium and other editors."
      >
        <button
          type="button"
          disabled={!selected.size}
          onClick={() => setZipModal(true)}
          className="cf-btn-secondary"
        >
          Download ZIP
        </button>
        <button type="button" disabled={!selected.size} onClick={deleteSelected} className="cf-btn-danger">
          Delete selected
        </button>
      </PageHeader>

      <div className="cf-card p-4 sm:p-5">
        <div className="flex flex-col sm:flex-row sm:flex-wrap sm:items-end gap-4">
          <label className="block flex-1 min-w-[10rem]">
            <span className="cf-label mb-1.5">Topic</span>
            <select className="cf-select" value={topicFilter} onChange={(e) => setTopicFilter(e.target.value)}>
              <option value="">All topics</option>
              {topics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block flex-1 min-w-[10rem]">
            <span className="cf-label mb-1.5">Status</span>
            <select className="cf-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              <option value="draft">Draft</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="posted">Posted</option>
              <option value="failed">Failed (generation)</option>
            </select>
          </label>
          <label className="block flex-1 min-w-[10rem]">
            <span className="cf-label mb-1.5">Type</span>
            <select className="cf-select" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
              <option value="">All types</option>
              <option value="social">Social (quote + image)</option>
              <option value="blog">Blog (markdown)</option>
            </select>
          </label>
        </div>
      </div>

      {watchedJobIds.length > 0 ? (
        <div className="space-y-2">
          <div className="flex justify-end">
            <button type="button" onClick={() => clearWatchedJobIds()} className="cf-btn-ghost text-xs">
              Clear job list
            </button>
          </div>
          <GenerationStatus jobIds={watchedJobIds} onSettled={() => load()} />
        </div>
      ) : null}

      {!items.length ? (
        <div className="cf-card-muted p-12 text-center max-w-lg mx-auto">
          <p className="text-slate-400 text-sm leading-relaxed">
            {topicFilter || statusFilter || kindFilter
              ? "Nothing matches these filters. Try clearing filters or generate new content."
              : "No content yet. Create a topic, then use Generate for social posts or blog articles."}
          </p>
          <div className="mt-6 flex flex-wrap gap-3 justify-center">
            <Link to="/generate" className="cf-btn-primary">
              Go to Generate
            </Link>
            <Link to="/topics" className="cf-btn-secondary">
              Manage topics
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
          {items.map((c) =>
            c.kind === "blog" ? (
              <BlogContentCard
                key={c.id}
                item={c}
                topic={topicMap[c.topic_id]}
                selected={selected.has(c.id)}
                onToggle={() => toggle(c.id)}
                onRefresh={load}
                onDeleted={clearSelectionFor}
              />
            ) : (
              <ContentCard
                key={c.id}
                item={c}
                topic={topicMap[c.topic_id]}
                selected={selected.has(c.id)}
                onToggle={() => toggle(c.id)}
                accounts={accounts}
                onRefresh={load}
                onDeleted={clearSelectionFor}
              />
            )
          )}
        </div>
      )}

      {zipModal && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="cf-card p-6 max-w-sm w-full space-y-5 shadow-2xl">
            <h3 className="text-lg font-semibold text-white">Download ZIP</h3>
            <label className="flex items-center gap-3 text-sm text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={includeVideo}
                onChange={(e) => setIncludeVideo(e.target.checked)}
                className="rounded border-forge-600 text-sky-500 focus:ring-sky-500/40"
              />
              Include videos (larger file)
            </label>
            <div className="flex gap-2 justify-end pt-1">
              <button type="button" onClick={() => setZipModal(false)} className="cf-btn-ghost">
                Cancel
              </button>
              <button type="button" disabled={zipBusy} onClick={downloadZip} className="cf-btn-primary">
                {zipBusy ? "Preparing…" : "Download"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
