import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ContentCard from "../components/ContentCard.jsx";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";

export default function ContentLibrary() {
  const [items, setItems] = useState([]);
  const [topics, setTopics] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [topicFilter, setTopicFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState(() => new Set());
  const [zipModal, setZipModal] = useState(false);
  const [includeVideo, setIncludeVideo] = useState(false);
  const [zipBusy, setZipBusy] = useState(false);

  const topicMap = useMemo(() => Object.fromEntries(topics.map((t) => [t.id, t])), [topics]);

  function load() {
    api.platforms.accounts().then(setAccounts);
    api.content
      .list({
        topic_id: topicFilter ? Number(topicFilter) : undefined,
        status: statusFilter || undefined,
        limit: 50,
      })
      .then(setItems);
  }

  useEffect(() => {
    api.topics.list().then(setTopics);
  }, []);

  useEffect(() => {
    load();
  }, [topicFilter, statusFilter]);

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
        subtitle="Browse, approve, edit, download, and post your generated pieces."
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
            </select>
          </label>
        </div>
      </div>

      {!items.length ? (
        <div className="cf-card-muted p-12 text-center max-w-lg mx-auto">
          <p className="text-slate-400 text-sm leading-relaxed">
            {topicFilter || statusFilter
              ? "Nothing matches these filters. Try clearing filters or generate new content."
              : "No content yet. Create a topic, then run a full generation from the Generate page."}
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
          {items.map((c) => (
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
          ))}
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
