// RAG file picker state for the chat sidebar.
//
// Owns the network calls (GET /plugin/mcp/rag/list, POST /plugin/mcp/rag/upload)
// and the small reactive surface the panel renders. Modeled on useMcpRun.js so
// every component that talks to the MCP API follows the same shape:
// take $api, return refs + action functions.
//
// The panel calls fetch() once on mount and after every successful upload; the
// caller doesn't need to know which endpoint backs which action.
//
// Errors prefer the server's `{error: "..."}` payload when present and fall
// back to a user-readable default — matching what the rest of the chat UI does.
//
// Filename validation is duplicated here (must end in `.json`) only so the
// upload button can disable cheap input before a round-trip; the backend in
// app/mcp_api.py is still the source of truth.
//
// File-size formatting is exposed as a helper so the template stays free of
// inline math.

import { ref } from 'vue'

const ACCEPTED_EXT = '.json'

export function useRagFiles($api) {
  const ragFiles = ref([])           // [{filename, size, modified}]
  const selectedFile = ref(null)     // File picked in the input, not yet uploaded
  const isUploading = ref(false)
  const uploadMessage = ref('')
  const uploadError = ref('')

  function clearStatus() {
    uploadMessage.value = ''
    uploadError.value = ''
  }

  function isJsonFile(file) {
    if (!file) return false
    return (
      file.type === 'application/json' ||
      file.name.toLowerCase().endsWith(ACCEPTED_EXT)
    )
  }

  function onFileSelected(event) {
    clearStatus()
    const file = event.target.files?.[0]
    if (!file) {
      selectedFile.value = null
      return
    }
    if (!isJsonFile(file)) {
      selectedFile.value = null
      uploadError.value = 'Please select a .json file.'
      return
    }
    selectedFile.value = file
  }

  async function fetchRagFiles() {
    try {
      const res = await $api.get('/plugin/mcp/rag/list')
      ragFiles.value = res.data.files || []
      return ragFiles.value
    } catch (err) {
      uploadError.value =
        err?.response?.data?.error || 'Failed to fetch RAG files.'
      return []
    }
  }

  async function uploadRag() {
    if (!selectedFile.value) return
    isUploading.value = true
    clearStatus()
    try {
      const fd = new FormData()
      fd.append('file', selectedFile.value)
      const res = await $api.post('/plugin/mcp/rag/upload', fd)
      uploadMessage.value =
        `Uploaded ${res.data.filename} (${formatBytes(res.data.size)})`
      selectedFile.value = null
      await fetchRagFiles()
    } catch (err) {
      uploadError.value =
        err?.response?.data?.error || 'Upload failed.'
    } finally {
      isUploading.value = false
    }
  }

  return {
    ragFiles,
    selectedFile,
    isUploading,
    uploadMessage,
    uploadError,
    onFileSelected,
    fetchRagFiles,
    uploadRag,
  }
}

export function formatBytes(bytes) {
  if (bytes === 0 || bytes == null) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

export function formatDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString() } catch { return iso }
}
