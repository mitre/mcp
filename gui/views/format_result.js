// Convert the LLM's lightly-marked-up process_result into safe HTML for the
// Result panel. Handles the patterns the workflow signatures actually emit:
//
//   **bold**                 -> <strong>bold</strong>
//   "- item" at column 0     -> top-level <ul><li>
//   "• item" at column >=2   -> nested <ul><li> inside the parent's <li>
//   blank line               -> closes any open list and starts a new block
//   anything else            -> <p>plain text</p>
//
// HTML is escaped first so process_result never injects markup. Only the
// bold and bullet patterns survive into the output.

const HTML_ESCAPES = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;',
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, ch => HTML_ESCAPES[ch])
}

function applyBold(s) {
  return s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
}

export function formatProcessResult(text) {
  if (!text) return ''

  const lines = String(text).split(/\r?\n/)
  const out = []
  let openLists = 0    // number of currently-open <ul> tags
  let openLi = false   // is there a currently-open <li> at the deepest list?

  const closeLi = () => {
    if (openLi) {
      out.push('</li>')
      openLi = false
    }
  }
  const closeListsTo = (depth) => {
    while (openLists > depth) {
      closeLi()
      out.push('</ul>')
      openLists--
      // After closing a nested list, the parent <li> at the next-shallower
      // level is still open and may need closing on the next sibling.
      openLi = openLists > 0
    }
  }

  for (const raw of lines) {
    if (raw.trim() === '') {
      closeListsTo(0)
      continue
    }

    const m = raw.match(/^(\s*)([-•])\s+(.*)$/)
    if (m) {
      const indent = m[1].length
      // Two spaces per nesting level, with a hard floor of 1 so a bare
      // top-level "- " always opens depth 1 rather than depth 0.
      const depth = Math.max(1, Math.floor(indent / 2) + 1)

      if (depth > openLists) {
        // Going deeper: nest a new <ul> inside the currently-open <li>.
        // Do NOT close openLi; the nested list lives inside it.
        while (openLists < depth) {
          out.push('<ul>')
          openLists++
        }
      } else {
        // Same depth or shallower: close the current <li>, close any
        // deeper lists, then close the parent <li> at this depth (which
        // becomes "open" again after a nested list collapses) so the
        // new item is a sibling rather than another nested child.
        closeLi()
        closeListsTo(depth)
        closeLi()
      }
      out.push('<li>' + applyBold(escapeHtml(m[3])))
      openLi = true
    } else {
      closeListsTo(0)
      out.push('<p>' + applyBold(escapeHtml(raw.trim())) + '</p>')
    }
  }
  closeListsTo(0)
  return out.join('')
}
