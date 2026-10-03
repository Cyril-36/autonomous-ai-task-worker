# Console

The operator console for the task worker: sign in, give the worker a task, watch it work, answer its questions, approve exact changes, and read the verified evidence report.

React + TypeScript + Vite. The wire format is `docs/INTERFACES.md` §1.

```bash
npm install
npm run dev:mock    # http://localhost:5173 against an in-memory mock of the API (sandbox password: sandbox-demo)
npm run dev         # http://localhost:5173, proxying /api to the backend on :8100
npm test            # reducer, stream and formatting tests
npm run build       # console/dist, served by the backend at /
```

How it works: `src/state/runReducer.ts` folds `RunEvent`s into the view, so live updates and history replay share one code path. `src/api/stream.ts` follows the server-sent event stream, resumes with `Last-Event-ID`, and drops anything already applied. Everything shown as "verified" comes from the server's `VerificationResult`; the console never infers completion from steps.
