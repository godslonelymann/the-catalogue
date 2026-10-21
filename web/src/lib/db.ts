import "server-only";
import { Pool, types } from "pg";

// NUMERIC (prices) as JS numbers. Prices are at most 10 digits, so this is exact enough.
types.setTypeParser(types.builtins.NUMERIC, (v) => Number(v));

// Connection settings come from the standard PG* environment variables
// (PGHOST, PGPORT, PGDATABASE, PGUSER), see web/.env.example.
const globalForPool = globalThis as unknown as { pool?: Pool };
export const pool = globalForPool.pool ?? new Pool({ max: 5 });
if (process.env.NODE_ENV !== "production") globalForPool.pool = pool;

export async function query<T>(sql: string, params: unknown[] = []): Promise<T[]> {
  const result = await pool.query(sql, params);
  return result.rows as T[];
}
