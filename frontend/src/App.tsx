import { useWebSocket } from './hooks/useWebSocket'
import { useContestStore } from './hooks/useContestStore'
import { ControlBar } from './components/ControlBar'
import { PersonalityModal } from './components/PersonalityModal'
import { UserInputColumn } from './components/UserInputColumn'
import { ScoreBoard } from './components/ScoreBoard'
import { AgentPanel } from './components/AgentPanel'
import { MessageFeed } from './components/MessageFeed'
import './styles/global.css'
import './styles/grid.css'

export default function App() {
  const { send } = useWebSocket()
  const serverError = useContestStore((s) => s.serverError)
  const setServerError = useContestStore((s) => s.setServerError)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <ControlBar send={send} />
      {serverError && (
        <div style={{
          background: '#450a0a', color: '#fca5a5', padding: '8px 16px',
          fontSize: '13px', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          borderBottom: '1px solid #7f1d1d', flexShrink: 0,
        }}>
          <span>⚠ {serverError}</span>
          <button
            onClick={() => setServerError(null)}
            style={{ background: 'none', border: 'none', color: '#fca5a5', cursor: 'pointer', fontSize: '16px' }}
          >✕</button>
        </div>
      )}
      <ScoreBoard />
      <AgentPanel send={send} />
      <MessageFeed />
      <UserInputColumn send={send} />
      <PersonalityModal send={send} />
    </div>
  )
}
