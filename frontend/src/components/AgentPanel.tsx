import { useContestStore, roleColor } from '../hooks/useContestStore'
import { ModelDropdown } from './ModelDropdown'
import type { ClientMessage } from '../types'

interface Props {
  send: (msg: ClientMessage) => void
}

export function AgentPanel({ send }: Props) {
  const agentOrder = useContestStore((s) => s.agentOrder)
  const agentConfigs = useContestStore((s) => s.agentConfigs)
  const openModal = useContestStore((s) => s.setPersonalityModalAgent)
  const phase = useContestStore((s) => s.phase)
  const contestStarted = phase !== 'idle'

  return (
    <div className="agent-panel">
      {agentOrder.map((id) => {
        const cfg = agentConfigs[id]
        if (!cfg) return null
        const accent = roleColor(cfg.role)
        return (
          <div key={id} className="agent-card" style={{ borderTop: `3px solid ${accent}` }}>
            <div className="agent-card__name" style={{ color: accent }}>{cfg.name}</div>
            <div className="agent-card__role" style={{ color: accent }}>{cfg.role}</div>
            <div className="agent-card__controls">
              {cfg.role !== 'user' && <ModelDropdown agentId={id} send={send} />}
              <button
                className="btn-personality"
                onClick={() => openModal(id)}
                title={
                  contestStarted
                    ? 'View (read-only during contest)'
                    : cfg.role === 'user'
                    ? 'Change name'
                    : 'Edit persona'
                }
              >
                {cfg.role === 'user'
                  ? contestStarted ? '👁 name' : '✎ rename'
                  : contestStarted ? '👁 persona' : '✎ persona'}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
