import { describe, expect, it } from "vitest";
import { APP_DESCRIPTION, APP_NAME } from "@/lib/app-config";

describe("app identity", () => {
  it("ships the app name and description", () => {
    expect(APP_NAME).toBe("COLMAP Gaussian Splatting Pipeline");
    expect(APP_DESCRIPTION).toBe(
      "Capture-to-B2 photogrammetry pipeline: COLMAP SfM + Gaussian Splatting / NeRF staging, every artifact versioned on Backblaze B2"
    );
  });
});
