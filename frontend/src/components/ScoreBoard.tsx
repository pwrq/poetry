import { useState } from 'react'
import { useContestStore, roleColor } from '../hooks/useContestStore'

export function ScoreBoard() {
  const [collapsed, setCollapsed] = useState(false)
  const agentOrder = useContestStore((s) => s.agentOrder)
  const roundScores = useContestStore((s) => s.roundScores)
  const cumulative = useContestStore((s) => s.cumulative)
  const totalRounds = useContestStore((s) => s.totalRounds)
  const agentConfigs = useContestStore((s) => s.agentConfigs)
  const phase = useContestStore((s) => s.phase)
  const roundTopics = useContestStore((s) => s.roundTopics)

  const hasScores = Object.keys(roundScores).length > 0
  if (!hasScores && phase === 'idle') return null

  const contestants = agentOrder.filter((id) => agentConfigs[id]?.role === 'contestant')
  const rounds = Array.from({ length: totalRounds }, (_, i) => i + 1)
  const leader = cumulative.reduce<typeof cumulative[0] | null>(
    (best, c) => (!best || c.total > best.total ? c : best),
    null,
  )

  if (collapsed) {
    return (
      <div
        className="scoreboard scoreboard--collapsed"
        onClick={() => setCollapsed(false)}
        title="Click to expand"
      >
        <span style={{ color: '#8b5cf6', fontWeight: 700, fontSize: 11 }}>SCOREBOARD</span>
        {leader && (
          <span style={{ color: 'var(--text-muted)', fontSize: 11, marginLeft: 10 }}>
            Leader:{' '}
            <strong style={{ color: 'var(--text)' }}>{leader.contestant_name}</strong>{' '}
            ({leader.total} pts)
          </span>
        )}
        <span className="scoreboard__toggle"> [expand]</span>
      </div>
    )
  }

  return (
    <div className="scoreboard">
      <div className="scoreboard__header">
        <span style={{ color: '#8b5cf6', fontWeight: 700, fontSize: 11 }}>SCOREBOARD</span>
        <button className="scoreboard__toggle" onClick={() => setCollapsed(true)}>
          [collapse]
        </button>
      </div>

      {!hasScores ? (
        <div style={{ fontSize: 11, color: 'var(--text-muted)', paddingTop: 4 }}>
          Scores will appear here after judging begins.
        </div>
      ) : (
        <div className="scoreboard__table-wrap">
          <table className="scoreboard__table">
            <thead>
              <tr>
                <th className="scoreboard__th">Contestant</th>
                {rounds.flatMap((r) => [
                  <th key={`${r}-hdr`} className="scoreboard__th scoreboard__th--round" colSpan={4}>
                    R{r}{roundTopics[r] ? `: ${roundTopics[r]}` : ''}
                  </th>,
                ])}
                <th className="scoreboard__th">Total</th>
                <th className="scoreboard__th">#</th>
              </tr>
              <tr>
                <th className="scoreboard__th" />
                {rounds.flatMap((r) => [
                  <th key={`${r}-ot`} className="scoreboard__th scoreboard__th--cat">🎯</th>,
                  <th key={`${r}-or`} className="scoreboard__th scoreboard__th--cat">✨</th>,
                  <th key={`${r}-av`} className="scoreboard__th scoreboard__th--cat">🎨</th>,
                  <th key={`${r}-s`} className="scoreboard__th scoreboard__th--cat">∑</th>,
                ])}
                <th className="scoreboard__th" />
                <th className="scoreboard__th" />
              </tr>
            </thead>
            <tbody>
              {contestants.map((cid) => {
                const cfg = agentConfigs[cid]
                const cum = cumulative.find((c) => c.contestant_id === cid)
                return (
                  <tr key={cid} className="scoreboard__row">
                    <td
                      className="scoreboard__name"
                      style={{ color: roleColor('contestant') }}
                    >
                      {cfg?.name ?? cid}
                    </td>
                    {rounds.flatMap((r) => {
                      const rs = roundScores[r]?.find((s) => s.contestant_id === cid)
                      if (!rs) {
                        return [
                          <td key={`${r}-ot`} className="scoreboard__cell">—</td>,
                          <td key={`${r}-or`} className="scoreboard__cell">—</td>,
                          <td key={`${r}-av`} className="scoreboard__cell">—</td>,
                          <td key={`${r}-s`} className="scoreboard__cell scoreboard__cell--sum">—</td>,
                        ]
                      }
                      return [
                        <td key={`${r}-ot`} className="scoreboard__cell">{rs.on_topic}</td>,
                        <td key={`${r}-or`} className="scoreboard__cell">{rs.originality}</td>,
                        <td key={`${r}-av`} className="scoreboard__cell">{rs.artistic_value}</td>,
                        <td key={`${r}-s`} className="scoreboard__cell scoreboard__cell--sum">{rs.total}</td>,
                      ]
                    })}
                    <td className="scoreboard__cell scoreboard__cell--total">
                      {cum?.total ?? '—'}
                    </td>
                    <td className="scoreboard__cell">
                      {cum?.rank === 1 ? '🏆' : cum?.rank ?? '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
