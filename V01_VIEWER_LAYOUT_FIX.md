# Rajan Dental v0.1 — Document viewer and footer adjustment

This maintenance release **does not change the displayed application version** (v0.1) and does not modify the database or backend API.

## Frontend improvements
- JPEG/PNG document viewer: wheel up/down zooms 25–400%, mouse drag pans enlarged images, rotation and reset controls remain available.
- PDF document viewer: uses browser-native inline PDF display rather than a zoom-parameterized iframe; also provides **Open PDF** in browser tab (for browsers that cannot render embedded PDFs), and a Download action. PDF pages can be scrolled in the browser PDF viewer. Zoom buttons adjust its requested scale; exact handling depends on the browser's built-in PDF viewer.
- Sidebar navigation scrolls independently when there are many menu items; version/logout footer stays at the bottom of the sidebar.
- Main application footer is aligned below page content. Mobile footer appears above the fixed bottom navigation rather than being hidden.

## Local install / preserving data
1. Stop the frontend (`Ctrl+C`). Back up the existing working project.
2. From this ZIP, replace **only** `rajan_dental_app/frontend/src/main.jsx` and `rajan_dental_app/frontend/src/style.css` in the existing installation.
3. Run `npm run dev` from the existing `frontend` folder and hard-refresh the browser (`Ctrl+Shift+R`). Backend and database do not need to be replaced.

## Validation
- TypeScript JSX parser: passed (0 parse errors).
- Backend scripts: `test_next.py`, `test_v24.py`, `test_v22.py` passed.
- ZIP integrity: verified.
- Full Vite build and interactive Firefox/Chrome PDF preview: **not verified** in this environment. Check PDF display and image panning locally.

## Known limitation
PDF first-page thumbnails are not generated; the gallery shows a PDF icon. Full PDFs open in the preview viewer or new browser tab. A future thumbnail renderer would require PDF rasterization infrastructure (for example PDF.js or a secured server-side renderer).
