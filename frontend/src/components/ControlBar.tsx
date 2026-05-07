import { useState, useEffect } from 'react'
import { useContestStore } from '../hooks/useContestStore'
import type { ClientMessage } from '../types'

const PHASE_LABELS: Record<string, string> = {
  idle: 'Waiting to start',
  setup: 'Setting up',
  hiring: 'Hiring agents',
  performance: 'Performance',
  deliberation: 'Judges Deliberating',
  scoring: 'Scoring',
  post_contest: 'Contest Over',
  chat: 'Live',
}

interface Props {
  send: (msg: ClientMessage) => void
}

export function ControlBar({ send }: Props) {
  const connected = useContestStore((s) => s.connected)
  const phase = useContestStore((s) => s.phase)
  const currentRound = useContestStore((s) => s.currentRound)
  const totalRounds = useContestStore((s) => s.totalRounds)
  const finalResults = useContestStore((s) => s.finalResults)
  const judgingMode = useContestStore((s) => s.judgingMode)
  const maxSlot = useContestStore((s) => s.maxSlot)
  const waitingForUser = useContestStore((s) => s.waitingForUser)
  const messageDelay = useContestStore((s) => s.messageDelay)
  const setMessageDelay = useContestStore((s) => s.setMessageDelay)
  const resetAll = useContestStore((s) => s.resetAll)

  const [starting, setStarting] = useState(false)

  // Clear "starting" once Romano sends something or awaits user input
  useEffect(() => {
    if (maxSlot > 0 || waitingForUser || phase !== 'idle') {
      setStarting(false)
    }
  }, [maxSlot, waitingForUser, phase])

  const showStart = connected && maxSlot === 0 && !starting

  function handleStart() {
    setStarting(true)
    send({ type: 'start_contest', data: {} })
  }

  function handleReset() {
    setStarting(false)
    resetAll()
    send({ type: 'reset_contest', data: {} })
  }

  function handleJudgingMode(mode: 'sequential' | 'autogen') {
    send({ type: 'change_judging_mode', data: { mode } })
  }

  return (
    <div
      style={{
        height: 'var(--header-height)',
        background: '#12121a',
        borderBottom: '1px solid #2a2a3a',
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '0 16px',
      }}
    >
      {/* Connection dot */}
      <div
        style={{
          width: 8, height: 8, borderRadius: '50%',
          background: connected ? '#10b981' : '#ef4444',
          flexShrink: 0,
        }}
        title={connected ? 'Connected' : 'Disconnected'}
      />

      <div style={{ fontWeight: 700, fontSize: '15px', color: '#6366f1', letterSpacing: '0.05em' }}>
        🎭 POETRY CONTEST
      </div>

      {/* Round indicator */}
      {currentRound > 0 && (
        <div
          style={{
            fontSize: '15px',
            fontWeight: 800,
            letterSpacing: '0.05em',
            padding: '2px 10px',
            borderRadius: '6px',
            background: '#1e1e2e',
            border: '1px solid #6366f1',
            color: '#e2e8f0',
          }}
        >
          Round <span style={{ color: '#6366f1' }}>{currentRound}</span>/{totalRounds}
        </div>
      )}

      {/* Phase indicator */}
      <div
        style={{
          fontSize: '11px',
          padding: '2px 8px',
          borderRadius: '4px',
          background: '#1e1e2e',
          color: '#f59e0b',
          fontWeight: 600,
        }}
      >
        {PHASE_LABELS[phase] ?? phase}
      </div>

      {/* Start button / Starting indicator */}
      {showStart && (
        <button
          onClick={handleStart}
          style={{
            padding: '5px 18px',
            background: '#10b981',
            border: 'none',
            borderRadius: '6px',
            color: '#fff',
            fontSize: '13px',
            fontWeight: 700,
            cursor: 'pointer',
            letterSpacing: '0.04em',
          }}
        >
          ▶ Start Contest
        </button>
      )}

      {starting && (
        <span style={{ fontSize: '12px', color: '#f59e0b', fontWeight: 600 }}>
          ⏳ Starting…
        </span>
      )}

      {waitingForUser && (
        <span style={{
          fontSize: '12px', color: '#f59e0b', fontWeight: 700,
          animation: 'pulse 1.2s ease-in-out infinite',
        }}>
          💬 Reply to Romano ↓
        </span>
      )}

      {showStart && (
        <span style={{ fontSize: '11px', color: '#6b7280', fontStyle: 'italic' }}>
          Click Start — Romano will assemble the cast
        </span>
      )}

      {/* Winner chip */}
      {finalResults?.winner && (
        <div style={{ fontSize: '11px', color: '#10b981', fontWeight: 600 }}>
          🏆 {finalResults.winner.contestant_name}
        </div>
      )}

      <div style={{ flex: 1 }} />

      {/* Pace slider */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#94a3b8' }}>
        <span>Pace:</span>
        <input
          type="range"
          min={0}
          max={30}
          step={5}
          value={Math.round(messageDelay / 1000)}
          onChange={(e) => setMessageDelay(Number(e.target.value) * 1000)}
          style={{ width: '70px', accentColor: '#6366f1', cursor: 'pointer' }}
          title="Delay between messages"
        />
        <span style={{ minWidth: '36px', color: '#e2e8f0' }}>
          {messageDelay === 0 ? 'instant' : `${Math.round(messageDelay / 1000)}s`}
        </span>
      </div>

      {/* Judging mode toggle */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: '#94a3b8' }}>
        <span>Judging:</span>
        {(['sequential', 'autogen'] as const).map((mode) => (
          <button
            key={mode}
            onClick={() => handleJudgingMode(mode)}
            style={{
              padding: '2px 8px',
              borderRadius: '4px',
              border: '1px solid',
              borderColor: judgingMode === mode ? '#6366f1' : '#2a2a3a',
              background: judgingMode === mode ? '#1e1b4b' : 'transparent',
              color: judgingMode === mode ? '#a5b4fc' : '#6b7280',
              cursor: 'pointer',
              fontSize: '11px',
              fontWeight: judgingMode === mode ? 700 : 400,
            }}
          >
            {mode === 'sequential' ? '⟶ Sequential' : '⇄ AutoGen'}
          </button>
        ))}
      </div>

      <button
        onClick={handleReset}
        style={{
          padding: '4px 12px', background: 'transparent',
          border: '1px solid #ef4444', borderRadius: '4px',
          color: '#ef4444', fontSize: '12px', cursor: 'pointer', fontWeight: 600,
        }}
      >
        Reset
      </button>
    </div>
  )
}
