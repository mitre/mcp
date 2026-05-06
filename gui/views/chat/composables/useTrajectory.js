// Derive human-readable thought lines, the created adversary, and the
// abilities ordered under it from a DSPy ReAct trajectory dict.
//
// Trajectory shape (from /plugin/mcp/status):
//   {
//     thought_0: "...",  thought_1: "...",
//     tool_name_0: "create_ability", tool_args_0: "{...}", observation_0: "{...}",
//     ...
//   }

import { computed } from 'vue'

function splitSentences(thought) {
  return String(thought).split(/[.?!]\s+/).map(s => s.trim()).filter(Boolean)
}

function safeParse(v) {
  if (v == null) return null
  if (typeof v !== 'string') return v
  try { return JSON.parse(v) } catch { return null }
}

export function useTrajectory(trajectoryRef) {
  // Ordered list of thought strings.
  const thoughts = computed(() => {
    const traj = trajectoryRef.value || {}
    return Object.entries(traj)
      .filter(([k]) => k.startsWith('thought_'))
      .sort(([a], [b]) => {
        const idx = (k) => parseInt(k.match(/\d+/)?.[0] || 0)
        return idx(a) - idx(b)
      })
      .map(([, v]) => v)
  })

  // Sentences that the existing UI suppresses because the inject panels
  // already display the same information visually.
  function isInjectedSentence(sentence) {
    return sentence.includes('I have successfully created') && (
      sentence.includes('abilities') || sentence.includes('adversary')
    )
  }

  // Adversary created during this run, if any. Pulled from the
  // create_adversary tool call's args + observation.
  const adversary = computed(() => {
    const traj = trajectoryRef.value || {}
    const advEntry = Object.entries(traj).find(
      ([k, v]) => k.startsWith('tool_name_') && v === 'create_adversary'
    )
    if (!advEntry) return null

    const idx = advEntry[0].split('_')[2]
    const args = safeParse(traj[`tool_args_${idx}`])
    const obs = safeParse(traj[`observation_${idx}`])
    if (!args || !Array.isArray(args.atomic_ordering)) return null

    return {
      name: args.name || 'Unnamed Adversary',
      uuid: obs?.adversary_id || 'unknown-uuid',
      ability_uuids: args.atomic_ordering,
    }
  })

  // Map of ability_id -> human name, harvested from every observation in
  // the trajectory (some return a single object, some a list).
  const abilityNamesById = computed(() => {
    const traj = trajectoryRef.value || {}
    const map = {}
    Object.entries(traj)
      .filter(([k]) => k.startsWith('observation_'))
      .forEach(([, v]) => {
        const parsed = safeParse(v)
        if (parsed?.ability_id && parsed?.name) {
          map[parsed.ability_id] = parsed.name
        }
        if (Array.isArray(parsed)) {
          parsed.forEach(item => {
            const obj = typeof item === 'string' ? safeParse(item) : item
            if (obj?.ability_id && obj?.name) map[obj.ability_id] = obj.name
          })
        }
      })
    return map
  })

  // Ability names listed in the order the adversary references them.
  const abilityNames = computed(() => {
    const adv = adversary.value
    if (!adv) return []
    return adv.ability_uuids
      .map(uuid => abilityNamesById.value[uuid])
      .filter(Boolean)
  })

  return {
    thoughts,
    adversary,
    abilityNames,
    splitSentences,
    isInjectedSentence,
  }
}
