import { create } from 'zustand'
import type {
  AgentMessage,
  AgentConfig,
  AgentRole,
  Phase,
  RoundScore,
  CumulativeScore,
  FinalResults,
  StateUpdate,
} from '../types'

// Role order for inserting newly hired agents into agentOrder
const ROLE_ORDER: Record<string, number> = {
  user: 0,
  organizer: 1,
  contestant: 2,
  judge: 3,
  scorekeeper: 4,
}

// Minimal default configs for user + organizer (server will send full configs via config_sync)
const DEFAULT_USER: AgentConfig = {
  id: 'user', name: 'Boss', role: 'user', model: '', personality: '',
}
const DEFAULT_ORGANIZER: AgentConfig = {
  id: 'organizer', name: 'MC Romano', role: 'organizer',
  model: 'anthropic/claude-3.5-haiku', personality: '',
}

export interface ModelOption { id: string; name: string }

interface ContestStore {
  // Connection
  connected: boolean
  setConnected: (v: boolean) => void

  // Available models (fetched once from server)
  models: ModelOption[]
  setModels: (m: ModelOption[]) => void

  // Messages
  messages: AgentMessage[]
  maxSlot: number
  addMessage: (msg: AgentMessage) => void
  setHistory: (msgs: AgentMessage[]) => void

  // Contest state
  phase: Phase
  currentRound: number
  totalRounds: number
  waitingForUser: boolean
  waitingPrompt: string
  performanceOrder: string[]
  contestNumber: number
  judgingMode: 'sequential' | 'autogen'
  updateContestState: (s: StateUpdate) => void

  // Dynamic agent order (populated as MC hires agents)
  agentOrder: string[]

  // Agent configs
  agentConfigs: Record<string, AgentConfig>
  updateAgentConfig: (agentId: string, updates: Partial<AgentConfig>) => void

  // Scores
  roundScores: Record<number, RoundScore[]>
  roundTopics: Record<number, string>
  cumulative: CumulativeScore[]
  finalResults: FinalResults | null
  setScores: (round: number, scores: RoundScore[], cumulative: CumulativeScore[]) => void
  setFinalResults: (r: FinalResults) => void

  // UI
  personalityModalAgent: string | null
  setPersonalityModalAgent: (id: string | null) => void

  // Message pace (ms between displayed messages)
  messageDelay: number
  setMessageDelay: (ms: number) => void

  // Server error banner
  serverError: string | null
  setServerError: (e: string | null) => void

  // Reset
  resetAll: () => void
}

const initialState = {
  connected: false,
  models: [] as ModelOption[],
  messages: [],
  maxSlot: 0,
  phase: 'idle' as Phase,
  currentRound: 0,
  totalRounds: 3,
  waitingForUser: false,
  waitingPrompt: '',
  performanceOrder: [],
  contestNumber: 1,
  judgingMode: 'sequential' as 'sequential' | 'autogen',
  agentOrder: ['user', 'organizer'],
  agentConfigs: {
    user: { ...DEFAULT_USER },
    organizer: { ...DEFAULT_ORGANIZER },
  } as Record<string, AgentConfig>,
  roundScores: {},
  roundTopics: {},
  cumulative: [],
  finalResults: null,
  personalityModalAgent: null,
  messageDelay: 0,
  serverError: null as string | null,
}

export const useContestStore = create<ContestStore>((set) => ({
  ...initialState,

  setConnected: (v) => set({ connected: v }),
  setModels: (m) => set({ models: m }),

  addMessage: (msg) =>
    set((s) => ({
      messages: [...s.messages, msg],
      maxSlot: Math.max(s.maxSlot, msg.slot),
    })),

  setHistory: (msgs) =>
    set({
      messages: msgs,
      maxSlot: msgs.length > 0 ? Math.max(...msgs.map((m) => m.slot)) : 0,
    }),

  updateContestState: (s) =>
    set((prev) => ({
      phase: s.phase ?? prev.phase,
      currentRound: s.current_round ?? prev.currentRound,
      totalRounds: s.total_rounds ?? prev.totalRounds,
      waitingForUser: s.waiting_for_user ?? prev.waitingForUser,
      waitingPrompt: s.waiting_prompt ?? prev.waitingPrompt,
      performanceOrder: s.performance_order ?? prev.performanceOrder,
      contestNumber: s.contest_number ?? prev.contestNumber,
      judgingMode: s.judging_mode ?? prev.judgingMode,
      roundTopics:
        s.topic && s.current_round
          ? { ...prev.roundTopics, [s.current_round]: s.topic }
          : prev.roundTopics,
    })),

  updateAgentConfig: (agentId: string, updates: Partial<AgentConfig>) =>
    set((s) => {
      const isNew = !s.agentOrder.includes(agentId)
      const existing = s.agentConfigs[agentId]
      const merged = existing ? { ...existing, ...updates } : ({ id: agentId, ...updates } as AgentConfig)

      let newOrder = s.agentOrder
      if (isNew && merged.role) {
        const myRank = ROLE_ORDER[merged.role] ?? 99
        const insertIdx = newOrder.findIndex((id) => {
          const existingRole = s.agentConfigs[id]?.role ?? 'user'
          return (ROLE_ORDER[existingRole] ?? 99) > myRank
        })
        newOrder = insertIdx === -1
          ? [...newOrder, agentId]
          : [...newOrder.slice(0, insertIdx), agentId, ...newOrder.slice(insertIdx)]
      }
      return {
        agentOrder: newOrder,
        agentConfigs: { ...s.agentConfigs, [agentId]: merged },
      }
    }),

  setScores: (round, scores, cumulative) =>
    set((s) => ({
      roundScores: { ...s.roundScores, [round]: scores },
      cumulative,
    })),

  setFinalResults: (r) => set({ finalResults: r }),

  setPersonalityModalAgent: (id) => set({ personalityModalAgent: id }),

  setMessageDelay: (ms) => set({ messageDelay: ms }),

  setServerError: (e) => set({ serverError: e }),

  resetAll: () =>
    set((s) => ({
      ...initialState,
      connected: true,        // keep connection status
      models: s.models,       // keep fetched model list — WS is still open
      agentOrder: ['user', 'organizer'],
      agentConfigs: {
        user: { ...DEFAULT_USER },
        organizer: { ...DEFAULT_ORGANIZER },
      },
    })),
}))

export function roleColor(role: AgentRole): string {
  switch (role) {
    case 'organizer': return '#6366f1'   // indigo
    case 'contestant': return '#10b981'  // emerald
    case 'judge': return '#f59e0b'       // amber
    case 'scorekeeper': return '#8b5cf6' // purple
    case 'user': return '#3b82f6'        // blue
    default: return '#6b7280'
  }
}
