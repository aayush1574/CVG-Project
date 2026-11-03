# CardioScope — standalone frontend

A separate, locally running React / TypeScript / Vite / Tailwind / Lucide interface. The original application in `app/frontend`, its backend, trained models, and API contracts are untouched.

## Run

```powershell
cd 'D:\CVG Project\CVG 2\frontend-preview'
npm install
npm run dev
```

Open http://127.0.0.1:5174. The server binds only to loopback. There is no API proxy, backend URL, authentication, analytics, remote font request, or model connection.

`npm run build` performs a strict TypeScript check and creates the standalone production site in `dist`. `npm run preview` serves that build on port 5174; stop the development server first.

## What works locally

- Welcome page, collapsible demo guide, help, and three-step assessment journey.
- Full-bleed silent park video with three selectable background scenes and a global motion pause control. Videos pause outside the viewport and when the browser tab is hidden. Reduced-motion and data-saving preferences show still posters without loading the videos.
- Clickable process walkthrough, everyday-context photo tabs, previous/next controls, and an accessible enlarged photo viewer.
- One-time kinetic headline reveals, staggered section headings, gentle scroll-driven photo depth, and a reading-progress line. A subtle algorithmic SVG contour field responds to scroll and fine-pointer movement without intercepting clicks.
- App-wide motion controls share one preference across navigation. Manual pause, live system reduced-motion changes, and data-saving settings disable motion without hiding content. The preference stays in memory for the current page session; it is not saved to browser storage.
- Short button, tab, navigation, input, and disclosure feedback, with visible keyboard focus and 44px photograph controls. Scroll work is scheduled only after input or resize events; the contour field has no continuous animation loop.
- The walkthrough has explicit idle, tracking, pressed, morphing, settling, and suspended interaction states. Pointer movement and press pressure deform SVG paths in real time; choosing a step morphs the same vectors into a new contour configuration and moves the selected-tab underline. Keyboard and touch selection use the same transitions.
- Rapid step changes continue from the current vector geometry. Motion stops when settled, paused, offscreen, or in a hidden tab; pointer cancellation and navigation clean up pending work. Reduced motion switches directly to the selected shape.
- All 27 existing clinical fields, grouped into personal details, vital signs, labs, and lifestyle. Personal inputs start empty; missing values remain missing.
- Local single-record CSV / JSON import with source labels, editable review, validation, replacement, and removal. Field names match the existing application's keys; CSV needs one header row and one data row.
- File selection and validation for laboratory PDFs/images and ECG CSV, NPY, WFDB DAT + HEA, and images. Files remain in tab memory.
- Numeric ECG CSV viewing with named standard lead columns: lead I, six limb leads, or twelve leads. Lead selection, zoom, panning, and sampling-rate controls use actual supplied samples.
- Recorded synthetic sample report, separate research indices and event estimates, condition abstention states, arithmetic clinical ratios, and input completeness.
- Scenario sliders and number inputs compare baseline and edited **inputs**, keeping the original assessment intact. They do not predict risk changes.
- Print/save PDF includes disclosures, supplied values, waveform when available, and scenario comparison. Browser dialogs handle the save destination.
- Desktop, tablet, mobile, keyboard controls, visible focus, and reduced motion.

## Deliberate frontend-only limits

Personal prediction, PREVENT calculation, PDF/image OCR, NPY/WFDB decoding, waveform diagnosis, and scenario inference are unavailable. The UI explains this rather than simulating an engine or producing medical results. No `/api/health`, `/api/parse-report`, `/api/predict`, or `/api/simulate` request is made.

Data lives only in React state and local File objects, so refreshing clears it. **Save input details** on the review screen exports a local JSON file for reimport. No browser storage is used.

The sample is copied from `artifacts/report_upload_audit_local.json`, `results[1]`, into `src/demo-record.json`. It is a historical synthetic test response: age 46, female, seven supplied inputs. Its health index, PREVENT output, and available clinical scores are shown unchanged. Missing composite/Framingham/ECG outputs and missing assumption metadata remain unavailable. Editing any sample input invalidates those recorded outputs. Acute MI and conduction-block decisions remain inconclusive; clinical and waveform outputs are separate.

## Main files

- `src/main.tsx`: application state, navigation, welcome, review, help, sample flow.
- `src/WelcomeExperience.tsx`, `src/welcome-motion.css`: video playback, background scenes, interactive walkthrough, photo exploration, scroll reveals, reduced motion, and pause controls.
- `src/useMotionPreference.ts`, `src/useScrollMotion.ts`: shared motion preference, lifecycle cleanup, and event-driven scroll/pointer effects.
- `src/ContourField.tsx`, `src/contour-field.css`: deterministic decorative contour paths; no health signal is represented.
- `src/contourGeometry.ts`: matching vector topology for three contour configurations and local pointer deformation.
- `src/workflowMachine.ts`, `src/useWorkflowInteraction.ts`: interaction state transitions, stale-completion protection, pointer/focus events, and visibility handling.
- `src/motion-system.css`, `src/interaction-polish.css`: kinetic typography, scroll depth, accessible motion fallbacks, and control feedback.
- `src/Inputs.tsx`, `src/data.ts`: file handling, validation, clinical inputs, CSV parsers.
- `src/ReportView.tsx`: report, real waveform viewer, scenario input comparisons, printing.
- `src/index.css`, `src/refinement.css`, `src/inputs.css`, `src/report.css`: responsive design and motion.
- `public/images/care.jpg`, `public/images/CREDITS.md`: licensed local photograph and attribution.
- `public/media/CREDITS.md`: licensed background video and additional photograph sources.

Manrope and DM Serif Display are bundled from Fontsource; their licenses are included in the corresponding installed packages. The interface makes no runtime font calls.

## Verification

Start the dev server, then run:

```powershell
npx playwright install chromium
npm run check:ui
```

The checks cover manual validation, import/correction, file pairing and sampling rate, navigation retention, recorded sample reliability, scenario reset, real waveform viewing, PDF generation, mobile layouts, focus, reduced motion, and absence of API/remote calls. Motion checks also verify real scroll/pointer transform changes, manual pause across navigation, dynamic system preference changes, complete heading accessible names, and static behavior while paused. `qa/state-morph-check.mjs` verifies intermediate SVG path geometry, interrupted transitions, cancelled presses, keyboard/touch parity, and stopped paint work after settling or suspension. Automated accessibility scans cover welcome, upload, manual entry, review, and report. Screenshots and intermediate PDF output are written under `qa/`.

Research & Educational Simulation Only. This interface is not a medical device.
