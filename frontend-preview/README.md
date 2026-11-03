# CardioScope connected frontend

This interface now uses the research API for report extraction, prediction and simulation. Run npm ci and npm run dev with the backend on port 8000. See the root README for model restoration, setup and tests.

npm run build checks TypeScript and builds dist. npm run check:ui tests connected workflows and request lifecycle. npm run check:motion tests motion, keyboard, touch, reduced motion and responsive layouts. Historical offline QA scripts are reference only; their no-API assumptions do not apply to this integration.

The original disconnected design remains on the frontend branch. Current results use ConnectedReport and the verified model report panels. Extraction evidence survives navigation and stays bound to the submitted assessment. Browser state is in memory; uploads are processed by the backend.
