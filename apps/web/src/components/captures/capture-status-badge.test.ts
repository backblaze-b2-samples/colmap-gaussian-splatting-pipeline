import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CaptureStatusBadge } from "./capture-status-badge";
import type { CaptureStatus } from "@colmap-gaussian-splatting-pipeline/shared";

function render(status: CaptureStatus) {
  return renderToStaticMarkup(createElement(CaptureStatusBadge, { status }));
}

describe("CaptureStatusBadge", () => {
  it("labels each lifecycle status", () => {
    expect(render("draft")).toContain("Draft");
    expect(render("ready")).toContain("Ready");
    expect(render("running")).toContain("Running");
    expect(render("done")).toContain("Done");
    expect(render("failed")).toContain("Failed");
  });

  it("shows an animated spinner only while running", () => {
    expect(render("running")).toContain("animate-spin");
    expect(render("done")).not.toContain("animate-spin");
    expect(render("draft")).not.toContain("animate-spin");
  });

  it("tints the done badge with the B2 brand color", () => {
    expect(render("done")).toContain("--brand-b2");
  });
});
