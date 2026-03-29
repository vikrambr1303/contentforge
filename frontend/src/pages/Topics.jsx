import { useCallback, useEffect, useState } from "react";
import TopicForm from "../components/TopicForm.jsx";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";

export default function Topics() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    return api.topics
      .list()
      .then(setItems)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(t) {
    setEditing(t);
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        title="Topics"
        subtitle="Creative briefs for generation — tone, visual style, and how many pieces to aim for per topic."
      >
        {!formOpen ? (
          <button type="button" onClick={openCreate} className="cf-btn-primary">
            New topic
          </button>
        ) : (
          <button type="button" onClick={closeForm} className="cf-btn-secondary">
            Back to list
          </button>
        )}
      </PageHeader>

      {formOpen ? (
        <div className="space-y-2">
          <p className="text-xs text-slate-500">
            {editing ? (
              <>
                Editing <span className="text-slate-300 font-medium">{editing.name}</span> — save to apply or cancel to
                return to the list.
              </>
            ) : (
              <>New topic — save to create or cancel to return to the list.</>
            )}
          </p>
          <TopicForm onCreated={() => load()} editing={editing} onDoneEdit={closeForm} />
        </div>
      ) : (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 mb-3">All topics</h2>
          <div className="cf-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[36rem]">
                <thead>
                  <tr className="border-b border-forge-800 bg-forge-950/50 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-3.5">Name</th>
                    <th className="px-4 py-3.5">Style</th>
                    <th className="px-4 py-3.5">Background</th>
                    <th className="px-4 py-3.5">Active</th>
                    <th className="px-4 py-3.5 w-36 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-forge-800/80">
                  {loading && (
                    <tr>
                      <td colSpan={5} className="px-4 py-10 text-center text-slate-500">
                        Loading topics…
                      </td>
                    </tr>
                  )}
                  {!loading &&
                    items.map((t) => (
                      <tr key={t.id} className="hover:bg-forge-800/25 transition-colors">
                        <td className="px-4 py-4 align-top">
                          <div className="font-medium text-white">{t.name}</div>
                          <div className="text-xs text-slate-500 mt-1 line-clamp-2 max-w-md">{t.description}</div>
                        </td>
                        <td className="px-4 py-4 text-slate-300 align-top">{t.style}</td>
                        <td className="px-4 py-4 text-slate-400 align-top text-xs">
                          {t.background_source === "unsplash" ? "Unsplash" : "Stable Diff."}
                        </td>
                        <td className="px-4 py-4 align-top">
                          <span
                            className={
                              t.is_active
                                ? "inline-flex text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-md bg-emerald-500/12 text-emerald-300 ring-1 ring-emerald-500/20"
                                : "inline-flex text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-md bg-forge-800 text-slate-400 ring-1 ring-forge-700/80"
                            }
                          >
                            {t.is_active ? "Yes" : "No"}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right align-top space-x-1">
                          <button
                            type="button"
                            onClick={() => openEdit(t)}
                            className="cf-btn-ghost text-xs text-sky-400 hover:text-sky-300"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            onClick={() =>
                              api.topics
                                .remove(t.id)
                                .then(() => {
                                  if (editing?.id === t.id) closeForm();
                                  return load();
                                })
                                .catch((e) => alert(e.response?.data?.detail || e.message))
                            }
                            className="cf-btn-ghost-danger text-xs"
                          >
                            Delete
                          </button>
                        </td>
                      </tr>
                    ))}
                  {!loading && items.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-12 text-center">
                        <p className="text-slate-400 text-sm mb-4 max-w-md mx-auto leading-relaxed">
                          No topics yet. Create one to set tone, visual style, and targets for Generate and the content
                          library.
                        </p>
                        <button type="button" onClick={openCreate} className="cf-btn-primary">
                          New topic
                        </button>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
