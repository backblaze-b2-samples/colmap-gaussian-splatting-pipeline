"use client";

import Link from "next/link";
import { ArrowRight, Boxes } from "lucide-react";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { CaptureStatusBadge } from "@/components/captures/capture-status-badge";
import { useCaptures } from "@/lib/queries";
import { formatDate } from "@/lib/utils";

export function RecentCapturesTable() {
  const { data: captures = [], isLoading, error, refetch } = useCaptures();
  const recent = captures.slice(0, 8);

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Recent Captures</CardTitle>
        <CardAction className="self-center">
          <Link
            href="/captures"
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            View all
            <ArrowRight className="h-3 w-3" />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState error={error} onRetry={() => refetch()} />
        ) : recent.length === 0 ? (
          <EmptyState
            icon={Boxes}
            title="No captures yet"
            description="Create a capture and run COLMAP structure-from-motion."
          />
        ) : (
          <Table className="table-fixed">
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="w-[38%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Capture
                </TableHead>
                <TableHead className="w-[16%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Points
                </TableHead>
                <TableHead className="w-[24%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Updated
                </TableHead>
                <TableHead className="w-[22%] text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Status
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {recent.map((capture) => (
                <TableRow key={capture.id} className="table-row-hover">
                  <TableCell className="font-medium">
                    <Link
                      href={`/captures/${capture.id}`}
                      className="block truncate rounded-sm underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                      title={`Open ${capture.name}`}
                    >
                      {capture.name}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap tabular-nums">
                    {capture.status === "done"
                      ? capture.metrics.sparse_points.toLocaleString()
                      : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground whitespace-nowrap">
                    {formatDate(capture.updated_at)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap">
                    <CaptureStatusBadge status={capture.status} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
