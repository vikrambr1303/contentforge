import { useEffect, useState } from "react";
import GenerationStatus from "../components/GenerationStatus.jsx";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";
import { useAppStore } from "../store/useAppStore.js";

export default function Generate() {
  const [mode, setMode] = useState("social");
  const [topics, setTopics] = useState([]);
  const [topicId, setTopicId] = useState("");
  const [count, setCount] = useState(1);
  const [includeVideo, setIncludeVideo] = useState(false);
  const watchedJobIds = useAppStore((s) => s.watchedJobIds);
  const addWatchedJobIds = useAppStore((s) => s.addWatchedJobIds);
  const clearWatchedJobIds = useAppStore((s) => s.clearWatchedJobIds);
  const removeWatchedJobIds = useAppStore((s) => s.removeWatchedJobIds);
  const [busy, setBusy] = useState(false);
  const [blogBusy, setBlogBusy] = useState(false);

  useEffect(() => {
    api.topics.list().then((t) => {
      setTopics(t);
      if (t.length) setTopicId((prev) => prev || String(t[0].id));
    });
  }, []);

  function run() {
    if (!topicId) return;
    setBusy(true);
    api.generation
      .generate({ topic_id: Number(topicId), count, include_video: includeVideo })
      .then((res) => {
        const ids = res.job_ids || [];
        addWatchedJobIds(ids);
      })
      .catch((e) => alert(e.response?.data?.detail || e.message))
      .finally(() => setBusy(false));
  }

  function runBlog() {
    if (!topicId) return;
    setBlogBusy(true);
    api.generation
      .blog(Number(topicId))
      .then((res) => {
        if (res.job_id) addWatchedJobIds([res.job_id]);
      })
      .catch((e) => alert(e.response?.data?.detail || e.message))
      .finally(() => setBlogBusy(false));
  }

  return (
    <div className="space-y-10">
      <PageHeader
        title="Generate"
        subtitle="Social pipeline (quote, image, video) or a long-form blog draft — optional Mermaid diagrams when they fit the topic — copy from the library when done."
      />

      <div className="flex flex-wrap gap-2 border-b border-forge-800/80 pb-3">
        <button
          type="button"
          onClick={() => setMode("social")}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
            mode === "social"
              ? "bg-sky-600/25 text-sky-200 ring-1 ring-sky-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-forge-900/60"
          }`}
        >
          Social posts
        </button>
        <button
          type="button"
          onClick={() => setMode("blog")}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
            mode === "blog"
              ? "bg-violet-600/20 text-violet-200 ring-1 ring-violet-500/30"
              : "text-slate-400 hover:text-slate-200 hover:bg-forge-900/60"
          }`}
        >
          Blog post
        </button>
      </div>

      <div className="grid gap-8 lg:grid-cols-12 lg:gap-10 items-start">
        <div className="lg:col-span-5 space-y-4">
          {mode === "social" ? (
            <div className="cf-card p-5 sm:p-6 space-y-5">
              <h2 className="text-sm font-semibold text-white">New batch</h2>
              <label className="block">
                <span className="cf-label mb-1.5">Topic</span>
                <select className="cf-select" value={topicId} onChange={(e) => setTopicId(e.target.value)}>
                  {topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="cf-label mb-1.5">Count</span>
                <input
                  type="number"
                  min={1}
                  max={50}
                  className="cf-input"
                  value={count}
                  onChange={(e) => setCount(Number(e.target.value))}
                />
                <p className="mt-1.5 text-xs text-slate-500">Each item runs sequentially on the worker (recommended on CPU).</p>
              </label>
              <label className="flex items-start gap-3 text-sm text-slate-300 cursor-pointer rounded-lg border border-forge-800/80 bg-forge-950/40 px-3 py-3 hover:border-forge-700/80 transition">
                <input
                  type="checkbox"
                  checked={includeVideo}
                  onChange={(e) => setIncludeVideo(e.target.checked)}
                  className="mt-0.5 rounded border-forge-600 text-sky-500 focus:ring-sky-500/40"
                />
                <span>
                  <span className="font-medium text-slate-200">Include video (MP4)</span>
                  <span className="block text-xs text-slate-500 mt-0.5">Ken Burns–style clip from the final image.</span>
                </span>
              </label>
              <button type="button" onClick={run} disabled={busy || !topicId} className="cf-btn-primary w-full sm:w-auto">
                {busy ? "Queueing…" : "Generate"}
              </button>
            </div>
          ) : (
            <div className="cf-card p-5 sm:p-6 space-y-5 ring-1 ring-violet-500/15">
              <h2 className="text-sm font-semibold text-violet-200">Blog article</h2>
              <p className="text-xs text-slate-500 leading-relaxed">
                The worker first classifies the topic (technical vs functional vs balanced), then Ollama writes Markdown. Mermaid
                diagrams are <strong className="text-slate-400">optional</strong> (0–2) based on that plan. When present,{" "}
                <strong className="text-slate-400">Kroki</strong> renders each to a PNG for Medium-style paste. Requires outbound
                HTTPS from the worker.
              </p>
              <label className="block">
                <span className="cf-label mb-1.5">Topic</span>
                <select className="cf-select" value={topicId} onChange={(e) => setTopicId(e.target.value)}>
                  {topics.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" onClick={runBlog} disabled={blogBusy || !topicId} className="cf-btn-primary w-full sm:w-auto bg-violet-600 hover:bg-violet-500 border-violet-500/30">
                {blogBusy ? "Queueing…" : "Generate blog post"}
              </button>
            </div>
          )}
        </div>

        <div className="lg:col-span-7 space-y-4">
          <div className="cf-card-muted p-5 sm:p-6 space-y-3">
            <h2 className="text-sm font-semibold text-sky-300/90">While you wait</h2>
            <ul className="text-sm text-slate-400 space-y-2 list-disc list-inside leading-relaxed">
              <li>First run loads models and can take several minutes on CPU.</li>
              <li>Job list and ETA update automatically; you can leave this page and come back.</li>
              <li>Finished pieces show up in Content Library as drafts.</li>
              {mode === "blog" ? (
                <li className="text-violet-200/70">
                  Blog jobs can run several minutes (long LLM output + diagram rendering). Open Content Library → filter Type → Blog to
                  find the draft.
                </li>
              ) : null}
            </ul>
          </div>
          <div className="space-y-2">
            {watchedJobIds.length > 0 && (
              <div className="flex justify-end">
                <button type="button" onClick={() => clearWatchedJobIds()} className="cf-btn-ghost text-xs">
                  Clear job list
                </button>
              </div>
            )}
            <GenerationStatus
              jobIds={watchedJobIds}
              onRemoveJobId={(id) => removeWatchedJobIds([id])}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
