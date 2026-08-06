import { CaptureDetail } from "@/components/captures/capture-detail";

export default async function CaptureDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <div className="animate-fade-in">
      <CaptureDetail id={id} />
    </div>
  );
}
