export default function PageHeader({ title, subtitle, children }) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <h1 className="text-3xl font-semibold tracking-tight text-white">{title}</h1>
        {subtitle ? (
          <p className="mt-2 text-sm text-slate-400 max-w-2xl leading-relaxed">{subtitle}</p>
        ) : null}
      </div>
      {children ? <div className="flex flex-wrap items-center gap-2 shrink-0">{children}</div> : null}
    </div>
  );
}
