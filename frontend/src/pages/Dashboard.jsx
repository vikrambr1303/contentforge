import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";
import { JOB_DONE_EVENT } from "../realtime.js";

export default function Dashboard() {
  const [apiStatus, setApiStatus] = useState(null);
  const [topics, setTopics] = useState([]);
  const [content, setContent] = useState([]);

  const refresh = useCallback(() => {
    api.checkHealth().then(setApiStatus).catch(() => setApiStatus({ status: "down" }));
    api.topics.list().then(setTopics).catch(() => {});
    api.content.list({ limit: 5 }).then(setContent).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const onJobDone = () => refresh();
    window.addEventListener(JOB_DONE_EVENT, onJobDone);
    return () => window.removeEventListener(JOB_DONE_EVENT, onJobDone);
  }, [refresh]);

  return (
    <div className="space-y-10">
      <PageHeader
        title="Dashboard"
        subtitle="Quick read on API health, topics, and your latest generated items."
      />

      <div className="grid sm:grid-cols-3 gap-4 lg:gap-5">
        <div className="cf-card p-5">
          <p className="cf-label mb-2">API</p>
          <p className="text-2xl font-semibold text-emerald-400">
            {apiStatus?.status === "ok" ? "Online" : "Unavailable"}
          </p>
          <p className="text-xs text-slate-500 mt-2">
            {apiStatus?.status === "ok" ? "Backend responded to health check." : "Start the API or check your proxy."}
          </p>
        </div>
        <div className="cf-card p-5">
          <p className="cf-label mb-2">Active topics</p>
          <p className="text-2xl font-semibold text-white tabular-nums">{topics.filter((t) => t.is_active).length}</p>
          <p className="text-xs text-slate-500 mt-2">Eligible for generation.</p>
        </div>
        <div className="cf-card p-5">
          <p className="cf-label mb-2">Recent preview</p>
          <p className="text-2xl font-semibold text-white tabular-nums">{content.length}</p>
          <p className="text-xs text-slate-500 mt-2">Latest five items loaded.</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Link to="/generate" className="cf-btn-primary">
          Generate content
        </Link>
        <Link to="/topics" className="cf-btn-secondary">
          Manage topics
        </Link>
        <Link to="/library" className="cf-btn-secondary">
          Open library
        </Link>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Recent content</h2>
        <ul className="space-y-2">
          {content.map((c) => {
            const preview =
              c.kind === "blog"
                ? (c.blog_markdown || "").match(/^#\s+(.+)$/m)?.[1]?.trim() || "Blog post"
                : c.quote_text || "";
            const short = preview.slice(0, 100) + (preview.length > 100 ? "…" : "");
            return (
              <li
                key={c.id}
                className="cf-card-muted flex flex-wrap items-baseline justify-between gap-2 px-4 py-3 text-sm text-slate-300"
              >
                <span className="min-w-0">
                  <span className="text-slate-500 font-mono text-xs mr-2">#{c.id}</span>
                  {c.kind === "blog" ? (
                    <span className="text-violet-300/90 text-[10px] font-semibold uppercase tracking-wide mr-2">Blog</span>
                  ) : null}
                  <span className="text-slate-200">{short || "—"}</span>
                </span>
                <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 shrink-0">{c.status}</span>
              </li>
            );
          })}
          {!content.length && <li className="text-slate-500 text-sm">No content yet.</li>}
        </ul>
      </div>
    </div>
  );
}
