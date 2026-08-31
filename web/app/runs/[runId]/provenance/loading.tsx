function Block({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-surface-raised ${className}`} />;
}

export default function Loading() {
  return (
    <div>
      <Block className="h-3 w-48" />
      <Block className="mt-3 h-9 w-72" />
      <Block className="mt-2 h-4 w-full max-w-xl" />

      <div className="mt-10 flex flex-col gap-8 md:flex-row">
        <div className="w-full space-y-2 md:w-64">
          <Block className="h-9 w-full" />
          <Block className="h-8 w-full" />
          <Block className="h-8 w-full" />
          <Block className="h-8 w-full" />
        </div>
        <div className="flex-1 space-y-4">
          <Block className="h-16 w-48" />
          <Block className="h-24 w-full max-w-md" />
          <Block className="h-16 w-48" />
        </div>
      </div>
    </div>
  );
}
