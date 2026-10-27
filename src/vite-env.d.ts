/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_KVIE_STT_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
