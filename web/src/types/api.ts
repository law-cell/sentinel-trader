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

export interface AlertAction {
  type: 'alert'
}

export interface StockOrderAction {
  type: 'propose_stock_order'
  side: 'BUY' | 'SELL'
  quantity: number
  order_type: 'MARKET' | 'LIMIT'
  limit_price: number | null
}

export interface OptionOrderAction {
  type: 'propose_option_order'
  right: 'C' | 'P'
  strike: number
  expiry_days: number
  quantity: number
}

export type Action = AlertAction | StockOrderAction | OptionOrderAction

export interface RuleResponse {
  name: string
  symbol: string
  condition: RuleCondition
  channel: string
  action: Action
  cooldown: number
  enabled: boolean
  last_triggered: string | null
}
