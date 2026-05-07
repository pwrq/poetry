import { useContestStore } from '../hooks/useContestStore'
import type { ClientMessage } from '../types'

interface Props {
  agentId: string
  send: (msg: ClientMessage) => void
}

export function ModelDropdown({ agentId, send }: Props) {
  const cfg = useContestStore((s) => s.agentConfigs[agentId])
  const models = useContestStore((s) => s.models)
  const phase = useContestStore((s) => s.phase)
  const updateAgentConfig = useContestStore((s) => s.updateAgentConfig)
  const disabled = phase !== 'idle'

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    if (disabled) return
    const model = e.target.value
    updateAgentConfig(agentId, { model })
    send({ type: 'change_model', data: { agent_id: agentId, model } })
  }

  if (cfg.role === 'user') return null

  return (
    <select
      value={cfg.model}
      onChange={handleChange}
      disabled={disabled}
      title={disabled ? 'Locked during contest' : undefined}
      style={{
        fontSize: '10px',
        padding: '1px 4px',
        background: '#1a1a2e',
        color: disabled ? '#4a5568' : '#e2e8f0',
        border: '1px solid #2a2a3a',
        borderRadius: '3px',
        maxWidth: '140px',
        cursor: disabled ? 'not-allowed' : 'default',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {models.map((m) => (
        <option key={m.id} value={m.id}>{m.name}</option>
      ))}
      {/* Always include current model even if not in list */}
      {cfg.model && !models.find((m) => m.id === cfg.model) && (
        <option value={cfg.model}>{cfg.model}</option>
      )}
    </select>
  )
}
