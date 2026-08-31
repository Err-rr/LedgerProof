function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-raised ${className}`} />;
}

export default function Loading() {
  return (
    <div>
      <Block className="h-3 w-32" />
      <Block className="mt-3 h-9 w-64" />
      <Block className="mt-2 h-4 w-48" />

      <div className="mt-12">
        <Block className="h-3 w-28" />
        <Block className="mt-3 h-20 w-full max-w-xl" />
        <Block className="mt-4 h-4 w-full max-w-2xl" />
      </div>

      <div className="mt-14 grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="h-32 rounded-card border border-border bg-surface p-6">
          <Block className="h-3 w-20" />
          <Block className="mt-4 h-8 w-16" />
        </div>
        <div className="h-32 rounded-card border border-border bg-surface p-6">
          <Block className="h-3 w-28" />
          <Block className="mt-4 h-8 w-16" />
        </div>
        <div className="h-32 rounded-card border border-border bg-surface p-6">
          <Block className="h-3 w-24" />
          <Block className="mt-4 h-8 w-20" />
        </div>
      </div>

      <div className="mt-14">
        <Block className="h-3 w-40" />
        <div className="mt-5 space-y-5">
          <Block className="h-10 w-full" />
          <Block className="h-10 w-full" />
          <Block className="h-10 w-full" />
        </div>
      </div>
    </div>
  );
}
