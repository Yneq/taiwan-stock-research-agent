# FinScope TW · React + TypeScript client

A small, independent React client for the existing FinScope FastAPI service. It
demonstrates a real member session and research request without changing the
deployed JavaScript dashboard.

## Run locally

Start the FastAPI app on `http://127.0.0.1:8000`, then:

```bash
cd frontend-react
npm ci
npm run dev
```

If the machine's global npm cache has permission errors, use
`npm ci --cache /private/tmp/finscope-react-npm-cache` instead of changing its
ownership.

Open `http://localhost:5173`. Vite proxies `/api` to FastAPI. The browser sends
the same-origin HttpOnly session cookie automatically; the frontend never reads
or stores a JWT. The portfolio demo account must be configured on the backend.

## Verify

```bash
npm test
npm run build
npm run lint
```

## Code map

- `src/types/research.ts`: TypeScript mirror of the FastAPI response contract.
- `src/api/research.ts`: HTTP requests and status/error conversion.
- `src/hooks/useResearch.ts`: idle, loading, success, and error states.
- `src/components/ResearchForm.tsx`: controlled form and validation.
- `src/components/ResearchResult.tsx`: answer, tool trace, and citations.
- `src/App.tsx`: session check, demo login, and pending question resume.
- `tests/App.test.tsx`: user-visible login, loading, result, and error behavior.

The HTTP client explicitly asks for JSON. The existing production dashboard
uses the same `/api/research` endpoint with NDJSON progress streaming; this
interview client focuses on the JSON contract and user-facing state handling.
