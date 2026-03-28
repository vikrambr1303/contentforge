export default function PlatformCard({ meta }) {
  return (
    <div className="cf-card p-4 text-sm">
      <div className="font-semibold text-white">{meta.display_name}</div>
      <div className="text-xs text-slate-500 mt-1.5">Plugin · {meta.name}</div>
      <div className="text-xs text-slate-400 mt-2 leading-relaxed">
        Types: {meta.supported_content_types?.join(", ") || "—"}
      </div>
    </div>
  );
}
