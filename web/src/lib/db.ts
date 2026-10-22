import "server-only";
import { Pool, types } from "pg";

// NUMERIC (prices) as JS numbers. Prices are at most 10 digits, so this is exact enough.
types.setTypeParser(types.builtins.NUMERIC, (v) => Number(v));

// Production (Vercel): DATABASE_URL is the pooled Neon address of the "website" user, with
// sslmode=verify-full, so the server certificate and host name are checked.
// Local development: leave DATABASE_URL empty and use the standard PG* variables, see web/.env.example.
// Each Vercel function instance has its own pool, so keep it small. Neon's pooler handles the rest.
const globalForPool = globalThis as unknown as { pool?: Pool };
export const pool =
  globalForPool.pool ??
  new Pool({ connectionString: process.env.DATABASE_URL || undefined, max: 3, idleTimeoutMillis: 10_000 });
if (process.env.NODE_ENV !== "production") globalForPool.pool = pool;

export async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const result = await pool.query(sql, params);
  return result.rows as T[];
}
