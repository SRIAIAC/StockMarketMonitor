/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL, e.g. "https://backend-xyz.a.run.app". Required in any
   * deployment where the frontend and backend don't share a hostname+port. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
