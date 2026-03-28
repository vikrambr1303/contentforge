import { create } from "zustand";
import { persist } from "zustand/middleware";

const MAX_WATCHED_JOBS = 50;

/** Persisted so Generate page survives reload while Celery runs. */
export const useAppStore = create(
  persist(
    (set) => ({
      watchedJobIds: [],
      addWatchedJobIds: (ids) => {
        const incoming = (ids || []).filter((n) => Number.isFinite(n));
        if (!incoming.length) return;
        set((state) => {
          const prev = state.watchedJobIds || [];
          const merged = [...new Set([...incoming, ...prev])];
          return { watchedJobIds: merged.slice(0, MAX_WATCHED_JOBS) };
        });
      },
      clearWatchedJobIds: () => set({ watchedJobIds: [] }),
      removeWatchedJobIds: (ids) => {
        const drop = new Set(ids);
        set((state) => ({
          watchedJobIds: state.watchedJobIds.filter((id) => !drop.has(id)),
        }));
      },
    }),
    {
      name: "contentforge-ui",
      partialize: (state) => ({ watchedJobIds: state.watchedJobIds }),
    }
  )
);
