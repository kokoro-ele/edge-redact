export type Risk = 'high' | 'medium' | 'low'

export type EntityType =
  // high
  | 'CN_ID'
  | 'JP_MYNUMBER'
  | 'CREDIT_CARD'
  | 'BANK_ACCOUNT'
  | 'NATIONAL_ID'
  | 'SECRET'
  // medium
  | 'PERSON'
  | 'ADDRESS'
  | 'PHONE'
  | 'EMAIL'
  | 'IP'
  | 'OTHER_ID'
  // low
  | 'ORG'
  | 'PROJECT'

export const RISK: Record<EntityType, Risk> = {
  CN_ID: 'high',
  JP_MYNUMBER: 'high',
  CREDIT_CARD: 'high',
  BANK_ACCOUNT: 'high',
  // passport, driver's licence, tax id, SSN: no checksum, often no fixed format. Highlighted for the
  // user to confirm rather than auto-redacted, so the high-risk recall floor stays reachable (PLAN.md).
  NATIONAL_ID: 'medium',
  SECRET: 'high',
  PERSON: 'medium',
  ADDRESS: 'medium',
  PHONE: 'medium',
  EMAIL: 'medium',
  IP: 'medium',
  OTHER_ID: 'medium',
  ORG: 'low',
  PROJECT: 'low',
}

export const RISK_RANK: Record<Risk, number> = { low: 0, medium: 1, high: 2 }

export interface Entity {
  /** UTF-16 offsets, end exclusive */
  start: number
  end: number
  type: EntityType
  risk: Risk
  /** 0..1 */
  score: number
  source: 'rule' | 'heuristic' | 'model'
}
