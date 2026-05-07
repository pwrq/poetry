import { useState, useEffect } from 'react'
import { useContestStore } from '../hooks/useContestStore'
import type { ClientMessage } from '../types'

interface Props {
  send: (msg: ClientMessage) => void
}

export function PersonalityModal({ send }: Props) {
  const agentId = useContestStore((s) => s.personalityModalAgent)
  const cfg = useContestStore((s) => (agentId ? s.agentConfigs[agentId] : null))
  const close = useContestStore((s) => s.setPersonalityModalAgent)
  const updateAgentConfig = useContestStore((s) => s.updateAgentConfig)
  const phase = useContestStore((s) => s.phase)
  const readOnly = phase !== 'idle'

  const [name, setName] = useState('')
  const [text, setText] = useState('')
  const [eraseMemory, setEraseMemory] = useState(false)

  useEffect(() => {
    if (cfg) {
      setName(cfg.name)
      setText(cfg.personality)
      setEraseMemory(false)
    }
  }, [cfg])

  if (!agentId || !cfg) return null

  function handleSave() {
    if (readOnly || !agentId) return
    const updates: { name?: string; personality?: string } = {}
    if (name && name !== cfg!.name) updates.name = name
    if (text !== cfg!.personality) updates.personality = text
    updateAgentConfig(agentId, { name, personality: text })
    send({
      type: 'change_personality',
      data: {
        agent_id: agentId,
        name,
        personality: text,
        erase_memory: eraseMemory,
      },
    })
    close(null)
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 100,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={() => close(null)}
    >
      <div
        style={{
          background: '#1a1a2e', border: '1px solid #2a2a3a', borderRadius: '8px',
          padding: '20px', width: '480px', maxWidth: '90vw',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ fontWeight: 700, fontSize: '14px', marginBottom: '4px', color: '#e2e8f0' }}>
          {readOnly ? 'Agent Info' : 'Edit Agent'} — {cfg.name}
        </div>
        {readOnly && (
          <div style={{ fontSize: '10px', color: '#f59e0b', marginBottom: '10px' }}>
            Read-only during contest
          </div>
        )}

        {/* Name field */}
        <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
          Display name
        </label>
        <input
          value={name}
          onChange={readOnly ? undefined : (e) => setName(e.target.value)}
          readOnly={readOnly}
          disabled={readOnly}
          style={{
            width: '100%', background: '#0a0a0f', border: '1px solid #2a2a3a',
            borderRadius: '4px', color: readOnly ? '#cbd5e1' : '#e2e8f0', fontSize: '13px',
            padding: '5px 8px', fontFamily: 'inherit', marginBottom: '10px',
            cursor: readOnly ? 'default' : 'text',
          }}
        />

        {/* Personality textarea — hidden for user role */}
        {cfg.role !== 'user' && (
          <>
            <label style={{ fontSize: '11px', color: '#94a3b8', display: 'block', marginBottom: '4px' }}>
              Personality prompt
            </label>
            <textarea
              value={text}
              onChange={readOnly ? undefined : (e) => setText(e.target.value)}
              readOnly={readOnly}
              disabled={readOnly}
              rows={7}
              style={{
                width: '100%', background: '#0a0a0f', border: '1px solid #2a2a3a',
                borderRadius: '4px', color: readOnly ? '#cbd5e1' : '#e2e8f0', fontSize: '12px',
                padding: '8px', fontFamily: 'inherit', resize: 'vertical',
                cursor: readOnly ? 'default' : 'text',
              }}
            />
          </>
        )}

        {cfg.role !== 'user' && !readOnly && (
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginTop: '12px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#94a3b8', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={eraseMemory}
                onChange={(e) => setEraseMemory(e.target.checked)}
              />
              Erase memory
            </label>
            <span style={{ fontSize: '10px', color: '#6b7280' }}>
              {eraseMemory ? 'Agent starts fresh with new personality' : 'Agent keeps conversation history'}
            </span>
          </div>
        )}

        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '16px' }}>
          <button
            onClick={() => close(null)}
            style={{ padding: '6px 14px', background: 'transparent', border: '1px solid #2a2a3a', borderRadius: '4px', color: '#94a3b8', cursor: 'pointer', fontSize: '12px' }}
          >
            {readOnly ? 'Close' : 'Cancel'}
          </button>
          {!readOnly && (
            <button
              onClick={handleSave}
              style={{ padding: '6px 14px', background: '#6366f1', border: 'none', borderRadius: '4px', color: '#fff', cursor: 'pointer', fontSize: '12px', fontWeight: 600 }}
            >
              Save
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
