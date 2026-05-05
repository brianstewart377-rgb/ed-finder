/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public-facing API base. Override per environment in .env files; falls back
   *  to /api when unset (production deploy through nginx). */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
