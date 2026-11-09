export async function request<T>(path:string, body?:unknown, method = body === undefined ? 'GET' : 'POST',
                                  timeout = body === undefined ? 15000 : 100000):Promise<T> {
 const response=await fetch('/api/v1'+path,{method,headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(timeout)})
 const result=await response.json()
 if(!response.ok)throw new Error(`${result.code??response.status} · ${result.message??'请求失败，请重试'}`)
 return result as T
}
export function price(value: string | null | undefined, digits = 2): string {
 if (value == null || !Number.isFinite(Number(value))) return '—'
 return new Intl.NumberFormat('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value as `${number}`)
}
export function officialLink(url:string|undefined):string|undefined {try {const u=new URL(url??'');return u.protocol==='https:'&&['www.cninfo.com.cn','static.cninfo.com.cn'].includes(u.hostname)?u.href:undefined}catch{return undefined}}

export const SECURITY_CODE = /^[0-9]{6}(\.(SH|SZ|BJ))?$/
export function dateTime(value: string): string {
 return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
