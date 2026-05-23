# Development Plan

`agents.md` and `product_spec.md` are the source of truth for detailed rules. This file is only a short working checklist for the current product direction.

## Current Tasks

- Keep `/` available without login.
- Show the initial screen as a video/file list.
- Keep the top-right login control as a compact icon.
- Open the login form as a centered panel over the home screen.
- Keep registration on a separate `/register` page.
- Create regular users server-side from login and password.
- Store passwords only as hashes.
- Give newly self-registered regular users access to the current available video list through `VideoAccess`.
- Keep regular users synchronized with available videos so users can see each other's uploads.
- Let authenticated users upload supported video files with a custom title.
- Accept large user uploads up to 10 GB while saving files in chunks.
- Transcode uploaded H.265/HEVC files to browser-compatible H.264/AAC MP4 with ffmpeg.
- Generate video card thumbnails from the first frame with ffmpeg.
- Redirect successful uploads to the new watch page.
- Show upload animation for at least one second after submit.
- Let admins and video authors delete videos.
- Stop playback before delete requests from the watch page to avoid Windows file locks.
- Interrupt active server-side streams for the deleted video before unlinking the file.
- If Windows keeps the file locked, keep retrying physical deletion from `video_storage/` in the background.
- Keep `/watch/{video_id}` and `/videos/{video_id}/stream` protected by session and video access checks.

## Later

- Add a supported mode for connecting from other devices on the local network.
- Document server binding to `0.0.0.0`, firewall requirements, and the local network URL.
- Keep internet/WAN exposure out of scope until security requirements are specified.

## Done

- FastAPI app with Jinja2 templates and static CSS/JS.
- SQLite models for `User`, `Video`, and `VideoAccess`.
- Login/logout through cookie sessions.
- Admin user bootstrap.
- Admin pages for users, videos, scan, metadata, and access.
- Video scan from `video_storage/`.
- Chunked video streaming with `Range` support.
- Public home page that can render the file list before login.
- Separate registration page and server-side user creation.
- User upload modal with drag and drop.
- Server-side video upload into `video_storage/`.
- Watch page uses the stream endpoint MIME instead of hardcoded `video/mp4`.
- Video deletion guarded by admin-or-author checks.
- Delete route hides the video and schedules physical file deletion instead of returning 500 when Windows keeps the file locked after stream interruption.

## Next Checks

- Guest opens `/` and sees the file list.
- Guest clicks the login icon and sees the centered login panel.
- Guest cannot open `/watch/{video_id}` without login.
- Guest cannot stream `/videos/{video_id}/stream` without login.
- New user can register with login and password.
- New regular user sees the current available videos after registration.
- Authenticated user can upload a video and becomes its author.
- Another regular user can see and stream the uploaded video.
- H.265/HEVC `.mp4`, `.m4v`, `.mov`, and `.mkv` uploads are accepted as input and saved as browser-compatible `.mp4`.
- Uploaded and scanned videos get a JPEG thumbnail in `video_storage/thumbnails/`.
- Other regular users cannot delete someone else's video.
- Admin and author can delete a video.
- Existing admin can still open `/admin`.
