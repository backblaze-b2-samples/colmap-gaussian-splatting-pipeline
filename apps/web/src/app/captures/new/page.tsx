import { CaptureForm } from "@/components/captures/capture-form";

export default function NewCapturePage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">New capture</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground text-pretty">
          Name the reconstruction and choose how COLMAP should process it. Create
          it, then add frames (an image set or a capture video) on the detail
          page and press Run.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2 max-w-2xl">
        <CaptureForm />
      </div>
    </div>
  );
}
