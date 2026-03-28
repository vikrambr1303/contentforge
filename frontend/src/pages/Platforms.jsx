import { useEffect, useState } from "react";
import PlatformCard from "../components/PlatformCard.jsx";
import PageHeader from "../components/PageHeader.jsx";
import * as api from "../api/client.js";

export default function Platforms() {
  const [plugins, setPlugins] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [history, setHistory] = useState([]);
  const [form, setForm] = useState({
    platform: "instagram",
    display_name: "",
    access_token: "",
    instagram_user_id: "",
    privacy_level: "SELF_ONLY",
    mark_as_ai_generated: false,
  });

  function refresh() {
    api.platforms.list().then(setPlugins);
    api.platforms.accounts().then(setAccounts);
    api.platforms.history().then(setHistory);
  }

  useEffect(() => {
    refresh();
  }, []);

  function submit(e) {
    e.preventDefault();
    const credentials =
      form.platform === "tiktok"
        ? {
            access_token: form.access_token,
            privacy_level: form.privacy_level,
            mark_as_ai_generated: form.mark_as_ai_generated,
          }
        : {
            access_token: form.access_token,
            instagram_user_id: form.instagram_user_id,
          };
    api.platforms
      .addAccount({
        platform: form.platform,
        display_name: form.display_name,
        credentials,
      })
      .then(() => {
        setForm({
          ...form,
          display_name: "",
          access_token: "",
          instagram_user_id: "",
        });
        refresh();
      })
      .catch((err) => alert(err.response?.data?.detail || err.message));
  }

  return (
    <div className="space-y-10">
      <PageHeader
        title="Platforms"
        subtitle="Available posting plugins, connected accounts, and recent publish attempts."
      />

      <div className="grid sm:grid-cols-2 gap-4">
        {plugins.map((p) => (
          <PlatformCard key={p.name} meta={p} />
        ))}
      </div>

      <form onSubmit={submit} className="cf-card p-5 sm:p-6 space-y-4 max-w-lg">
        <h2 className="text-lg font-semibold text-white">Add account</h2>
        <label className="block">
          <span className="cf-label mb-1.5">Platform</span>
          <select
            className="cf-select"
            value={form.platform}
            onChange={(e) => setForm({ ...form, platform: e.target.value })}
          >
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
          </select>
        </label>
        <label className="block">
          <span className="cf-label mb-1.5">Display name</span>
          <input
            className="cf-input"
            value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            required
          />
        </label>
        <label className="block">
          <span className="cf-label mb-1.5">
            {form.platform === "tiktok" ? "User access token (OAuth)" : "Long-lived access token"}
          </span>
          <input
            className="cf-input"
            type="password"
            autoComplete="off"
            value={form.access_token}
            onChange={(e) => setForm({ ...form, access_token: e.target.value })}
            required
          />
        </label>
        {form.platform === "instagram" ? (
          <label className="block">
            <span className="cf-label mb-1.5">Instagram User ID (Professional)</span>
            <input
              className="cf-input"
              value={form.instagram_user_id}
              onChange={(e) => setForm({ ...form, instagram_user_id: e.target.value })}
              required
            />
            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
              Graph API user id for a <strong className="text-slate-400">Professional</strong> Instagram —{" "}
              <strong className="text-slate-400">Creator</strong> or <strong className="text-slate-400">Business</strong>{" "}
              (Instagram → Settings → Account → Switch to professional account). It must be linked to a{" "}
              <strong className="text-slate-400">Facebook Page</strong>; Meta’s Instagram Graph API treats both account
              types the same for posting.
            </p>
          </label>
        ) : (
          <>
            <label className="block">
              <span className="cf-label mb-1.5">Privacy level</span>
              <select
                className="cf-select"
                value={form.privacy_level}
                onChange={(e) => setForm({ ...form, privacy_level: e.target.value })}
              >
                <option value="PUBLIC_TO_EVERYONE">PUBLIC_TO_EVERYONE</option>
                <option value="MUTUAL_FOLLOW_FRIENDS">MUTUAL_FOLLOW_FRIENDS</option>
                <option value="FOLLOWER_OF_CREATOR">FOLLOWER_OF_CREATOR</option>
                <option value="SELF_ONLY">SELF_ONLY (common for unaudited apps)</option>
              </select>
              <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">
                Must match an option from TikTok&apos;s{" "}
                <code className="text-slate-400">POST /v2/post/publish/creator_info/query/</code> for this account
                (validation uses this when saving).
              </p>
            </label>
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.mark_as_ai_generated}
                  onChange={(e) => setForm({ ...form, mark_as_ai_generated: e.target.checked })}
                  className="rounded border-forge-600 bg-forge-900 text-sky-500"
                />
                <span className="text-sm text-slate-300">
                  Mark posts as AI-generated on TikTok (<code className="text-slate-400">is_aigc</code>)
                </span>
              </label>
              <p className="text-xs text-slate-500 leading-relaxed pl-7">
                Off by default. Instagram posting in ContentForge does not send an AI flag. Enable this only if you want
                TikTok&apos;s AI label or your situation requires disclosure per TikTok&apos;s policies.
              </p>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              TikTok only accepts <strong className="text-slate-400">video</strong>. Use content with an MP4 and set{" "}
              <code className="text-slate-400">PUBLIC_BASE_URL</code> or <code className="text-slate-400">NGROK_LOCAL_API_URL</code>{" "}
              for HTTPS; verify the URL prefix in the TikTok developer portal for <code className="text-slate-400">PULL_FROM_URL</code>.
            </p>
          </>
        )}
        <button type="submit" className="cf-btn-primary">
          Save & validate
        </button>
      </form>

      <div>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Accounts</h2>
        <ul className="space-y-2">
          {accounts.map((a) => (
            <li
              key={a.id}
              className="cf-card-muted flex items-center justify-between gap-3 px-4 py-3 text-sm"
            >
              <span className="text-slate-200">
                {a.display_name} <span className="text-slate-500">· {a.platform}</span>
              </span>
              <button
                type="button"
                onClick={() => api.platforms.removeAccount(a.id).then(refresh)}
                className="cf-btn-ghost-danger text-xs shrink-0"
              >
                Remove
              </button>
            </li>
          ))}
          {!accounts.length && <li className="text-slate-500 text-sm">No accounts yet.</li>}
        </ul>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Post history</h2>
        <ul className="space-y-2 text-sm text-slate-400">
          {history.slice(0, 20).map((h) => (
            <li key={h.id} className="cf-card-muted px-3 py-2 text-xs sm:text-sm">
              Content #{h.content_item_id} — {h.status}
              {h.platform_post_id && ` · ${h.platform_post_id}`}
            </li>
          ))}
          {!history.length && <li className="text-slate-500">No posts yet.</li>}
        </ul>
      </div>
    </div>
  );
}
