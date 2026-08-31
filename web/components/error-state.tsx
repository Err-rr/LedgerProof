export function ErrorState({ title, message }: { title: string; message: string }) {
  return (
    <div className="rounded-card border border-sev-high bg-surface p-6">
      <p className="text-text-primary">{title}</p>
      <p className="mt-2 text-sm text-text-secondary">{message}</p>
    </div>
  );
}
