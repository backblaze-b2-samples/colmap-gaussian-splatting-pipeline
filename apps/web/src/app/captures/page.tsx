import Link from "next/link";
import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { CapturesList } from "@/components/captures/captures-list";

export default function CapturesPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="min-w-0">
          <h1 className="page-title">Captures</h1>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            Photogrammetry reconstruction jobs. Each capture ingests an image set
            or a capture video, runs COLMAP structure-from-motion on CPU, and
            stages a Nerfstudio/gsplat-ready bundle — every input and artifact
            versioned under its own prefix on Backblaze B2.
          </p>
        </div>
        <Button asChild size="sm" className="h-8 shrink-0">
          <Link href="/captures/new">
            <Plus aria-hidden="true" className="h-3.5 w-3.5" />
            New capture
          </Link>
        </Button>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <CapturesList />
      </div>
    </div>
  );
}
