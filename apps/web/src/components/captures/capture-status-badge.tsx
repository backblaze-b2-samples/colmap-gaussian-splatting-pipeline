import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { CaptureStatus } from "@colmap-gaussian-splatting-pipeline/shared";

const LABELS: Record<CaptureStatus, string> = {
  draft: "Draft",
  ready: "Ready",
  running: "Running",
  done: "Done",
  failed: "Failed",
};

// Done gets a green tint via a className override (no dedicated success variant).
const CLASSNAMES: Record<CaptureStatus, string> = {
  draft: "",
  ready: "",
  running: "",
  done: "bg-[var(--brand-b2)] text-white",
  failed: "",
};

const VARIANTS: Record<CaptureStatus, "default" | "secondary" | "destructive" | "outline"> = {
  draft: "outline",
  ready: "secondary",
  running: "default",
  done: "default",
  failed: "destructive",
};

export function CaptureStatusBadge({ status }: { status: CaptureStatus }) {
  return (
    <Badge variant={VARIANTS[status]} className={CLASSNAMES[status]}>
      {status === "running" && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {LABELS[status]}
    </Badge>
  );
}
