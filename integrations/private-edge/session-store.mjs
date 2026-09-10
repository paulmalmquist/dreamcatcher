/** Local reference only. Work adapters must implement this async contract using
 * an encrypted shared store with atomic insertion/capacity enforcement and TTL.
 * Tokens stay on the server. Sharing this object tests replicas, not durability.
 */
export function createMemorySessionStore({now=Date.now,capacity=5000}={}){
 const sessions=new Map();
 function prune(){for(const [key,s] of sessions)if(s.expires_at*1000<=now())sessions.delete(key)}
 return {
  persistent:false,
  async put(id,session){prune();if(sessions.size>=capacity||sessions.has(id)||session.expires_at*1000<=now())return false;sessions.set(id,structuredClone(session));return true},
  async get(id){prune();const value=sessions.get(id);return value?structuredClone(value):undefined},
  async delete(id){sessions.delete(id)}
 };
}
