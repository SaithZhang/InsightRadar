export type Decimal = string | null
export interface Candle { date:string;open:Decimal;close:Decimal;high:Decimal;low:Decimal }
export interface Zone { valid:boolean;reason:string|null;source:string|null;center:Decimal;halfWidth:Decimal;lower:Decimal;upper:Decimal }
export interface Evaluation { id:string;status:string;targetTradeDate:string;observedTradeDate:string|null;evaluatedAt:string;reason:string;conditions:Record<string,boolean> }
export interface Document {documentId:string;title:string;officialUrl:string;pdfUrl:string;pdfSha256:string|null;textExtractionStatus:string;publishedAt:string;pageCount:number;correctionOrSupplement:boolean;latestPeriodicReport:boolean}
export interface Fact {statement:string;classification:string;impact:string;whyItMatters:string;asOf:string;evidence:{documentId:string;page:number;quote:string}[]}
export interface ClosingQuote {
 canonicalCode: string; name: string; tradeDate: string; close: string; quotedAt: string; source: 'tencent';
}
export interface Report {
 closingQuote?: ClosingQuote;
 positionSnapshot?: PositionSnapshot;
 marketTiming?: {
  phase: 'PRE_OPEN' | 'IN_SESSION' | 'POST_CLOSE' | 'NON_TRADING_DAY' | 'UNKNOWN';
  requestedThrough: string;
  awaitingPublication: boolean;
  providerReleaseAt: string | null;
 };
 runId:string;requestedCode:string;canonicalCode:string|null;identity:{name:string;exchange:string}|null;officialIssuer:{name?:string};createdAt:string;asOfTradeDate:string|null;knowledgeCutoff:string;status:string;technicalStatus:string;eventStatus:string;source:string;priceBasis:Record<string,unknown>|null;dataGaps:string[];trade_authority:'none';
 candles:Candle[];indicators:{ma20:Decimal;ma55:Decimal;ma20FiveBarsAgo:Decimal;ma55FiveBarsAgo:Decimal;atr14:Decimal};indicatorSeries:{date:string;ma20:Decimal;ma55:Decimal}[];
 trend:{state:string;reasons:string[]};support:Zone;resistance:Zone;buyPlan:{id:string;baseTradeDate:string;targetTradeDate:string;zone:Zone;status:string}|null;buyPlanNotCreatedReason:string|null;
 sellReview:{state:string;reason:string;previousDate:string|null;date:string|null;previousClose:Decimal;previousMa55:Decimal;close:Decimal;ma55:Decimal};eventReview:{state:string;reason:string};
 facts:Fact[];followUps:{question:string;evidenceSource:string;criterion:string;expectedVerificationTime:string;manualConfirmationRequired:true}[];documents:Document[];
 coverage:Record<string,unknown>;semantic:Record<string,unknown>;dataQuality:{barsValid:number;targetBars:number;reliable:boolean;fresh:boolean;lastFinalizedDate:string|null;expectedSession:string|null;gaps:string[]};provenance:Record<string,unknown>;errors:{code:string;message:string}[]
}
export interface Run { runId:string;status:string;stage:string;report:Report|null;reportHash:string|null;error:{code:string;message:string}|null }
export interface HistoryItem {runId:string;requestedCode:string;status:string;createdAt:string;canonicalCode:string|null;asOfTradeDate:string|null;trend:string|null;eventStatus:string|null}

export type PositionAction = 'REVIEW_REDUCTION' | 'REVIEW_EXIT'
export interface Position {
 canonicalCode: string; quantity: number; unitCost: Decimal; onMa55Trigger: PositionAction | null;
 source: 'MANUAL'; confirmedAt: string; updatedAt: string; version: number;
}
export interface PositionItem {
 position: Position; name: string; confirmedToday: boolean; quoteDate: string | null;
 referenceClose: Decimal; marketValue: Decimal; unrealizedPnl: Decimal; unrealizedPnlPercent: Decimal;
}
export interface PositionSnapshot {
 schemaVersion: string; capturedAt: string; canonicalCode: string | null; position: Position | null;
 positionStatus: 'HOLDING' | 'CLEARED' | 'UNREGISTERED' | 'IDENTITY_UNCONFIRMED' | 'READ_FAILED';
 confirmationStatus: 'CONFIRMED' | 'STALE' | 'UNAVAILABLE';
 priceState: 'TRIGGERED' | 'NOT_TRIGGERED' | 'DATA_INSUFFICIENT';
 action: PositionAction | 'CONFIRM_POSITION' | 'OBSERVE' | 'WAIT_FOR_DATA' | 'EXIT_CONDITION_NOT_MET' | 'SET_EXIT_RULE';
 reason: string; ruleId: string; ruleVersion: string; evidence: Report['sellReview'];
 nextCheck: { tradeDate: string | null; earliestAnalysisDate: string | null; earliestAnalysisAt?: string | null; message: string };
}
