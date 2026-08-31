import { Eyebrow } from "@/components/eyebrow";
import { Count } from "@/components/data-text";
import type { StageResult } from "@/lib/api-types";

/**
 * The upload screen can't show live per-pass progress -- the run is
 * synchronous, so there is no intermediate state to poll. This is what it
 * shows instead once the response comes back: exactly what each pass did,
 * measured, not a re-enactment.
 */
export function PipelineDetail({ stages, durationMs }: { stages: StageResult[]; durationMs: number }) {
  if (stages.length === 0) return null;

  return (
    <div className="mt-14">
      <Eyebrow>Pipeline detail</Eyebrow>
      <p className="mt-2 text-sm text-text-secondary">
        What each pass actually found, in{" "}
        <span className="tabular-nums text-text-primary">{durationMs.toFixed(0)}ms</span> total.
      </p>
      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-text-secondary">
              <th className="py-2 pr-4 font-normal">Pass</th>
              <th className="py-2 pr-4 font-normal">Matches</th>
              <th className="py-2 pr-4 font-normal">Exceptions</th>
              <th className="py-2 font-normal">Duration</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((stage) => (
              <tr key={stage.pass_number} className="border-b border-border last:border-0">
                <td className="py-3 pr-4 text-text-primary">
                  <span className="mr-2 font-mono text-xs text-text-muted">{String(stage.pass_number).padStart(2, "0")}</span>
                  {stage.name}
                </td>
                <td className="py-3 pr-4">
                  <Count value={stage.matches} />
                </td>
                <td className="py-3 pr-4">
                  <Count value={stage.exceptions} />
                </td>
                <td className="tabular-nums py-3 text-text-primary">{stage.duration_ms.toFixed(1)}ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
