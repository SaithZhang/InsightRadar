import { afterEach,describe,it,expect,vi } from 'vitest'
import { request,officialLink,price } from '../src/api'
afterEach(()=>vi.unstubAllGlobals())
describe('runtime data boundary',()=>{
 it('propagates unavailable provider, without price fallback',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status:503,json:async()=>({code:'PROVIDER_UNAVAILABLE',message:'Unavailable'})}));await expect(request('/securities/resolve?code=002463')).rejects.toThrow('PROVIDER_UNAVAILABLE')})
 it('displays missing values as unknown, not zero',()=>{expect(price(null)).toBe('—');expect(price(undefined)).toBe('—');expect(price('bad')).toBe('—')})
 it('passes authoritative decimal strings through untouched',async()=>{const payload={ma20:'12.000000000000000012'};vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>payload}));expect(await request('/analyses/example')).toEqual(payload)})
 it('only links official HTTPS documents',()=>{expect(officialLink('https://static.cninfo.com.cn/a.pdf')).toBeDefined();expect(officialLink('javascript:alert(1)')).toBeUndefined();expect(officialLink('https://static.cninfo.com.cn.evil.test/a')).toBeUndefined()})
})
