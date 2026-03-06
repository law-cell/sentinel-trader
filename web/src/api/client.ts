import axios from 'axios'
import type { AccountSummaryResponse, PositionResponse, TriggerEvent, RuleResponse, MarketDataResponse, SymbolSearchResult } from '../types/api'

const api = axios.create({ baseURL: '/api' })

export async function fetchAccount(): Promise<AccountSummaryResponse> {
  const { data } = await api.get<AccountSummaryResponse>('/account')
  return data
}

export async function fetchPositions(): Promise<PositionResponse[]> {
  const { data } = await api.get<PositionResponse[]>('/positions')
  return data
}

export async function fetchHistory(limit = 10): Promise<TriggerEvent[]> {
  const { data } = await api.get<TriggerEvent[]>('/rules/history', { params: { limit } })
  return data
}

export async function fetchRules(): Promise<RuleResponse[]> {
  const { data } = await api.get<RuleResponse[]>('/rules')
  return data
}

export async function createRule(payload: object): Promise<RuleResponse> {
  const { data } = await api.post<RuleResponse>('/rules', payload)
  return data
}

export async function updateRule(name: string, payload: object): Promise<RuleResponse> {
  const { data } = await api.put<RuleResponse>(`/rules/${encodeURIComponent(name)}`, payload)
  return data
}

export async function deleteRule(name: string): Promise<void> {
  await api.delete(`/rules/${encodeURIComponent(name)}`)
}

export async function fetchMarketData(symbol: string): Promise<MarketDataResponse> {
  const { data } = await api.get<MarketDataResponse>(`/market-data/${encodeURIComponent(symbol)}`)
  return data
}

export async function searchSymbols(query: string): Promise<SymbolSearchResult[]> {
  const { data } = await api.get<SymbolSearchResult[]>(`/search/${encodeURIComponent(query)}`)
  return data
}

export async function checkHealth(): Promise<boolean> {
  try {
    await axios.get('/')
    return true
  } catch {
    return false
  }
}
