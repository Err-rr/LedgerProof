import { humanizeCode } from "@/lib/format";

interface FiltersProps {
  severities: string[];
  codes: string[];
  severityFilter: string;
  codeFilter: string;
  onSeverityChange: (value: string) => void;
  onCodeChange: (value: string) => void;
}

const SELECT_CLASS =
  "rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-text-primary focus:outline-none";

export function Filters({ severities, codes, severityFilter, codeFilter, onSeverityChange, onCodeChange }: FiltersProps) {
  return (
    <div className="flex flex-wrap gap-3">
      <select
        aria-label="Filter by severity"
        value={severityFilter}
        onChange={(event) => onSeverityChange(event.target.value)}
        className={SELECT_CLASS}
      >
        <option value="all">All severities</option>
        {severities.map((severity) => (
          <option key={severity} value={severity}>
            {severity.charAt(0).toUpperCase() + severity.slice(1)}
          </option>
        ))}
      </select>

      <select
        aria-label="Filter by exception code"
        value={codeFilter}
        onChange={(event) => onCodeChange(event.target.value)}
        className={SELECT_CLASS}
      >
        <option value="all">All codes</option>
        {codes.map((code) => (
          <option key={code} value={code}>
            {humanizeCode(code)}
          </option>
        ))}
      </select>
    </div>
  );
}
