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

## Next Checks

- Guest opens `/` and sees the file list.
- Guest clicks the login icon and sees the centered login panel.
- Guest cannot open `/watch/{video_id}` without login.
- Guest cannot stream `/videos/{video_id}/stream` without login.
- New user can register with login and password.
- New regular user sees the current available videos after registration.
- Existing admin can still open `/admin`.
