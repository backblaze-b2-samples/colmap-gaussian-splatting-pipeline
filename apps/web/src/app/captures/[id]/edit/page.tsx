import { CaptureEditForm } from "@/components/captures/capture-edit-form";

export default async function EditCapturePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Edit capture</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground text-pretty">
          Update this capture&apos;s name and COLMAP options. Changes take effect
          the next time you run it.
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2 max-w-2xl">
        <CaptureEditForm id={id} />
      </div>
    </div>
  );
}
