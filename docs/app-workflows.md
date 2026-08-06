<!-- last_verified: 2026-08-06 -->
# App Workflows

User journeys inside the application. The primary journey is the **Capture**
lifecycle; the File Explorer, Upload, and Settings journeys are kept from the
starter.

## Create and run a Capture (primary journey)

- User navigates to `/captures/new` and fills the create form:
  - **Name** (free text; hint `e.g. heritage-facade-01`)
  - **Source** (RadioGroup: Image set | Capture video; default Image set)
  - **Quality** (Select: Low / Medium / High; default Medium)
  - **Matcher** (Select: Exhaustive / Sequential; default Exhaustive)
  - **Max image dimension** (numeric; default 1600, "downscales large frames so CPU SfM finishes quickly")
- Submitting creates a `draft` capture (a manifest in B2) and lands on the detail page
- **Ingest frames**: the detail page shows an ingest panel matching the source type — upload overlapping photos, or upload a video the server samples into frames. Frames are downscaled and stored under `captures/<id>/inputs/`; the capture becomes `ready`
- **Run**: the Run button starts COLMAP SfM. The capture flips to `running` and the preview area shows an indeterminate stage list (SIFT extraction → matching → mapping → bundle → preview) — never a fabricated percentage. The page polls until the run finishes
- **Done**: the detail page shows the sparse point-cloud preview, the pipeline stage timeline (with dense MVS marked skipped on a CPU host), reconstruction metrics, the `ns-train` command for GPU training, and the versioned artifacts on B2 with download links
- **Edit / Delete / Re-run**: Edit opens the pre-filled form; Delete removes the capture's own B2 prefix (AlertDialog confirm); Re-run re-processes the current frames
- On failure the detail page shows the recorded error in an Alert
- See: [SfM reconstruction](features/sfm-reconstruction.md), [Capture ingest](features/capture-ingest.md), [Splat staging](features/splat-staging.md)

## Browse the Captures library

- User navigates to `/captures`
- A grid of capture cards shows each reconstruction's preview thumbnail, status, frame count, and (when done) registered images + sparse points
- The list polls while any capture is running so status flips and new previews appear automatically
- Empty state offers a New capture CTA
- See: [Captures library + dashboard](features/captures-dashboard.md)

## Upload Files

- User navigates to `/upload`
- Drops or selects files in the dropzone
- Client validates file size (max 100MB) and type
- A determinate progress bar tracks the bytes leaving the browser; once they are all sent the row switches to "Storing in B2..." with an *indeterminate* sweeping bar for the server-side phase (put_object + checksums + metadata). That phase has no percentage to report — measured at 25s on a 54MB file — and a bar parked at a full 100% read as finished-but-stuck
- On success: toast notification, green checkmark, and a "View in Files" link through to the browser
- On failure: red status icon with error message
- User can clear completed uploads
- The queue lives in an app-wide provider: navigating to another page keeps the upload running, shows an "Uploading N files" indicator in the header, and keeps the duplicate-upload guard armed
- Reloading or closing mid-upload asks for confirmation first; if the upload dies anyway, the next load says which file didn't finish
- See: [File Upload](features/file-upload.md)

## Browse and Manage Files

- User navigates to `/files`
- Page loads the 100 most recent objects from the API (sorted most recent first). While it loads, the page says so on screen and escalates the wording if the wait runs long — a full bucket listing measured 2.8s-21s cold
- If that limit was hit, a notice states how many objects the bucket actually holds — the page never claims to show everything
- Files displayed in tree view with folders and type-specific icons
- Folders auto-expand on load until the *majority* of the listed files are reachable without clicking, so the page's own "click a file" instruction is always actionable. Stopping at the first visible file was not enough: one stray top-level object left the other 99 sealed in collapsed folders while the page claimed to show 100
- Clicking a file row opens its preview; the per-row actions menu (preview / download / delete) is always visible, on every viewport
- Arriving at `/files?preview=<key>` expands that file's folders and opens its preview directly. This is how the ⌘K palette and the dashboard's recent-uploads rows hand off a *specific* file; the param is consumed on arrival so it doesn't re-fire later
- **Preview**: opens dialog with image/PDF preview + metadata panel, and the file's Download / Delete actions — the advertised "click a file" path offers everything the row menu does. The loading state holds until the media paints; a failure offers "Open in a new tab". The preview URL is signed with `Content-Disposition: inline` so PDFs render in place
- **Download**: shows a pending state on the row plus a toast while the presigned URL is fetched, then starts the download via an anchor click (which, unlike a popup, still works if the click's user activation expired during a slow presign). Failures are reported; the click can never silently do nothing
- **Delete**: the confirmation dialog stays open showing "Deleting..." until the request settles, then the row disappears with the toast (optimistic cache update) and the list reconciles with the server. The dialog is held deliberately — Radix closes on action click by default, which dismissed the only pending state and left the row looking untouched while the delete was still in flight
- Empty bucket shows "No files found" with upload prompt
- See: [File Browser](features/file-browser.md)

## View Dashboard

- User navigates to `/` (home)
- Stat cards show: captures, frames ingested, sparse points reconstructed, artifacts on B2
- A bar chart shows B2 write activity over the last 7 days
- The recent-captures table lists the latest captures with their point counts, updated time, and status; each name links to the capture detail
- While metrics load, the page states it in words above the cards rather than showing silent skeletons
- Empty state: "No captures yet" with a New capture CTA
- See: [Captures library + dashboard](features/captures-dashboard.md)

## Change Preferences

- User navigates to `/settings`
- A banner at the top states that the page is mostly a demonstration: only Theme is wired up for real, the rest showcases what a settings page can look like when you adapt the kit
- **Theme** (real): editing it and saving applies it immediately and persists it (`next-themes`), and the header's theme toggle drives the same state
- **Profile and preference fields** (demo): Display name, Bio, Default file view (Tree/List/Grid), Email me on every upload, Warn me when approaching quota + threshold. Each is labelled "Demo field", persists to `localStorage` only, and drives no behaviour — there is no account system, mailer, quota banner, activity log, or List/Grid view behind them yet
- Saving reports honestly: a success toast that separates the real theme change from the locally-stored demo values, or a warning toast if the browser blocked storage (theme still changes). It never claims a save that did not happen — the original page toasted "Settings saved" for fields that changed nothing
- Danger Zone actions are a demo — no real delete runs
- See: [Settings](features/settings.md)
