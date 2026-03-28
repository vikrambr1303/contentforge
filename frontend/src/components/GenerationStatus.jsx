import { useEffect, useState } from "react";
import * as api from "../api/client.js";

function formatEta(job, nowMs = Date.now()) {
  const st = job.status;
  if (st === "done" || st === "failed") return null;
  const raw = job.progress_percent ?? job.progressPercent;
  const p = Math.max(0, Math.min(100, Number(raw) || 0));
  if (st === "queued") return "Waiting for worker…";
  const t0 = new Date(job.created_at).getTime();
  if (!Number.isFinite(t0)) return "—";
  const elapsedSec = (nowMs - t0) / 1000;
  // Brief warm-up so we do not flash a wild guess on the first paint.
  if (elapsedSec < 1.25) return "Estimating time…";
  // Linear ETA: use at least 1% progress so early stages (e.g. quote-only at 5%) still get a number.
  const pUse = Math.min(Math.max(p, 1), 99);
  const rem = (elapsedSec * (100 - p)) / pUse;
  if (!Number.isFinite(rem) || rem < 0) return "—";
  if (rem > 5400) return "Several more minutes (CPU)";
  if (rem > 90) return `~${Math.round(rem / 60)} min left`;
  if (rem < 5) return "<5s left";
  return `~${Math.ceil(rem)}s left`;
}

export default function GenerationStatus({ jobIds, onSettled }) {
  const [jobs, setJobs] = useState([]);
  const [polledOnce, setPolledOnce] = useState(false);
  const [etaTick, setEtaTick] = useState(0);

  useEffect(() => {
    if (!jobIds?.length) return undefined;
    let cancelled = false;
    const tick = () => {
      Promise.all(jobIds.map((id) => api.jobs.get(id).catch(() => null)))
        .then((rows) => {
          if (!cancelled) {
            setJobs(rows.filter(Boolean));
            setPolledOnce(true);
          }
        })
        .catch(() => {
          if (!cancelled) setPolledOnce(true);
        });
    };
    setPolledOnce(false);
    tick();
    const id = setInterval(tick, 1500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [jobIds]);

  const hasActiveJob = jobs.some((j) => !["done", "failed"].includes(j.status));
  useEffect(() => {
    if (!hasActiveJob) return undefined;
    const id = setInterval(() => setEtaTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [hasActiveJob]);

  useEffect(() => {
    if (!jobs.length) return;
    const terminal = jobs.every((j) => ["done", "failed"].includes(j.status));
    if (terminal) onSettled?.();
  }, [jobs, onSettled]);

  if (!jobIds?.length) return null;

  const nowMs = Date.now();
  void etaTick;

  return (
    <div className="cf-card p-4 sm:p-5 space-y-3">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Generation jobs</p>
      {polledOnce && jobs.length === 0 && (
        <p className="text-xs text-slate-500 leading-relaxed">
          No status returned for these IDs (they may be old or removed). Use &quot;Clear job list&quot; to reset.
        </p>
      )}
      {!polledOnce && <p className="text-xs text-slate-500">Checking status…</p>}
      <ul className="space-y-3 text-sm">
        {jobs.map((j) => {
          const rawP = j.progress_percent ?? j.progressPercent;
          const p = Math.max(0, Math.min(100, Number(rawP) || 0));
          const terminal = j.status === "done" || j.status === "failed";
          const barPct = j.status === "done" ? 100 : p;
          const barClass =
            j.status === "done"
              ? "bg-gradient-to-r from-emerald-600 to-emerald-500"
              : j.status === "failed"
                ? "bg-gradient-to-r from-rose-600 to-rose-500"
                : "bg-gradient-to-r from-sky-600 to-cyan-500";
          const eta = formatEta(j, nowMs);
          return (
            <li key={j.id} className="rounded-xl border border-forge-800/90 bg-forge-950/50 p-3.5 space-y-2 ring-1 ring-inset ring-white/[0.02]">
              <div className="flex items-center justify-between gap-2">
                <span className="text-slate-200 text-sm">
                  <span className="font-mono text-slate-500 text-xs">#{j.id}</span>{" "}
                  <span className="text-slate-500">·</span> {j.job_type}{" "}
                  <span className="text-slate-500">·</span> topic {j.topic_id}
                </span>
                <span
                  className={
                    j.status === "done"
                      ? "text-[10px] font-semibold uppercase tracking-wide text-emerald-400 shrink-0 px-2 py-0.5 rounded-md bg-emerald-500/10 ring-1 ring-emerald-500/20"
                      : j.status === "failed"
                        ? "text-[10px] font-semibold uppercase tracking-wide text-rose-400 shrink-0 px-2 py-0.5 rounded-md bg-rose-500/10 ring-1 ring-rose-500/20"
                        : j.status === "running"
                          ? "text-[10px] font-semibold uppercase tracking-wide text-amber-300 shrink-0 px-2 py-0.5 rounded-md bg-amber-500/10 ring-1 ring-amber-500/20"
                          : "text-[10px] font-semibold uppercase tracking-wide text-slate-400 shrink-0 px-2 py-0.5 rounded-md bg-forge-800 ring-1 ring-forge-700/80"
                  }
                >
                  {j.status}
                </span>
              </div>
              {j.stage && <p className="text-xs text-slate-500 leading-snug">{j.stage}</p>}
              <div className="h-2 rounded-full bg-forge-800 overflow-hidden ring-1 ring-inset ring-black/20">
                <div
                  className={`h-full transition-[width] duration-500 ease-out ${barClass}`}
                  style={{ width: `${barPct}%` }}
                />
              </div>
              <div className="flex justify-between items-center gap-2 text-[11px] text-slate-500">
                <span className="tabular-nums">{terminal && j.status === "done" ? "100%" : `${p}%`}</span>
                {!terminal && eta && <span className="text-right text-slate-400">{eta}</span>}
                {terminal && j.status === "failed" && <span className="text-rose-400/90 text-right">Stopped</span>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
