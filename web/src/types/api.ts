export interface AccountSummaryResponse {
  account: string
  summary: {
    NetLiquidation?: number | null
    TotalCashValue?: number | null
    AvailableFunds?: number | null
    BuyingPower?: number | null
    GrossPositionValue?: number | null
    MaintMarginReq?: number | null
    UnrealizedPnL?: number | null
    RealizedPnL?: number | null
  }
}

export interface PositionResponse {
  symbol: string
  sec_type: string
  exchange: string
  position: number
  avg_cost: number | null
}

export interface SymbolSearchResult {
  symbol: string
  name: string
  sec_type: string
  exchange: string
}

export interface MarketDataResponse {
  symbol: string
  bid: number | null
  ask: number | null
  last: number | null
  volume: number | null
  close: number | null
}

export interface TriggerEvent {
  timestamp: string
  rule_name: string
  symbol: string
  price: number
}

export interface RuleCondition {
  type: 'price_above' | 'price_below' | 'price_change_pct' | 'volume_above'
  threshold: number
}

export interface RuleResponse {
  name: string
  symbol: string
  condition: RuleCondition
  action: string
  cooldown: number
  enabled: boolean
  last_triggered: string | null
}
