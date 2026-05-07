export type AgentRole = 'organizer' | 'contestant' | 'judge' | 'scorekeeper' | 'user'
export type Visibility = 'all' | 'judges_only' | 'organizer_only'
export type Phase =
  | 'idle'
  | 'setup'
  | 'hiring'
  | 'performance'
  | 'deliberation'
  | 'scoring'
  | 'post_contest'
  | 'chat'

export interface AgentMessage {
  slot: number
  agent_id: string
  agent_name: string
  agent_role: AgentRole
  content: string
  visibility: Visibility
  round_number: number
  phase: Phase
  timestamp: string   // "HH:MM:SS" set server-side
}

export interface AgentConfig {
  id: string
  name: string
  role: AgentRole
  model: string
  personality: string
}

export interface RoundScore {
  contestant_id: string
  contestant_name: string
  on_topic: number
  originality: number
  artistic_value: number
  total: number
}

export interface CumulativeScore {
  contestant_id: string
  contestant_name: string
  total: number
  rank: number
}

// WebSocket server→client messages
export type ServerMessage =
  | { type: 'agent_message'; data: AgentMessage }
  | { type: 'state_update'; data: StateUpdate }
  | { type: 'scores'; data: ScoresPayload }
  | { type: 'final_results'; data: FinalResults }
  | { type: 'config_sync'; data: AgentConfig }
  | { type: 'history_sync'; data: AgentMessage[] }
  | { type: 'error'; data: { message: string } }

export interface StateUpdate {
  phase?: Phase
  current_round?: number
  total_rounds?: number
  waiting_for_user?: boolean
  waiting_prompt?: string
  performance_order?: string[]
  contest_number?: number
  judging_mode?: 'sequential' | 'autogen'
  topic?: string
}

export interface ScoresPayload {
  round_number: number
  scores: RoundScore[]
  cumulative: CumulativeScore[]
}

export interface FinalResults {
  winner: { contestant_id: string; contestant_name: string; total: number }
  standings: CumulativeScore[]
}

// WebSocket client→server messages
export type ClientMessage =
  | { type: 'user_topic'; data: { topic: string } }
  | { type: 'user_message'; data: { content: string } }
  | { type: 'change_model'; data: { agent_id: string; model: string } }
  | { type: 'change_personality'; data: { agent_id: string; name?: string; personality: string; erase_memory: boolean } }
  | { type: 'start_contest'; data: Record<string, never> }
  | { type: 'reset_contest'; data: Record<string, never> }
  | { type: 'change_judging_mode'; data: { mode: 'sequential' | 'autogen' } }
