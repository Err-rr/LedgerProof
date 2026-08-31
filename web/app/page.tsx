import { Eyebrow } from "@/components/eyebrow";
import { UploadRunner } from "@/components/upload/upload-runner";

export default function UploadPage() {
  return (
    <div>
      <Eyebrow>01 — Upload and run</Eyebrow>
      <h1 className="mt-3 text-3xl tracking-tight2 text-text-primary">Reconcile a settlement batch</h1>
      <p className="mt-3 max-w-2xl text-text-secondary">
        Upload the five source files for one batch. Orders, payments, settlements, and the bank statement are
        required; refunds are optional.
      </p>

      <div className="mt-10">
        <UploadRunner />
      </div>
    </div>
  );
}
