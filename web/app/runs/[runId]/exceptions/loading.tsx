function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-raised ${className}`} />;
}

export default function Loading() {
  return (
    <div>
      <Block className="h-3 w-40" />
      <Block className="mt-3 h-9 w-64" />
      <Block className="mt-2 h-4 w-48" />

      <div className="mt-10 flex justify-between">
        <Block className="h-9 w-64" />
        <Block className="h-9 w-40" />
      </div>
      <Block className="mt-4 h-4 w-48" />

      <div className="mt-4 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Block key={i} className="h-11 w-full" />
        ))}
      </div>
    </div>
  );
}
