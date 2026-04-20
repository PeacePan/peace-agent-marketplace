# Migration 機制與流程

程式碼位置：
- Migration 檔案：`electron/main/database/migrations/{mutable,readonly}/`
- 向後相容：`electron/main/database/migrate-compat.ts`
- Drizzle Kit 配置：`electron/drizzle.config.{mutable,readonly}.ts`（**注意：在 `electron/` 根目錄，不是 `electron/main/database/`**）

---

## Migration 檔案結構

```
migrations/
├── mutable/
│   └── 20260320112530_nostalgic_captain_america/
│       ├── migration.sql      ← SQL DDL 陳述句
│       └── snapshot.json      ← Schema 完整快照（供 drizzle-kit 比對用）
│
└── readonly/
    └── 20260320122848_huge_harrier/
        ├── migration.sql
        └── snapshot.json
```

### 命名格式

```
{YYYYMMDDHHmmss}_{random_name}/
```

- **時間戳**：migration 產生的時間，14 位數字
- **名稱**：drizzle-kit 自動產生的隨機名稱（無業務含義）
- 每個 migration 是一個**目錄**，包含 `migration.sql` 和 `snapshot.json`

### migration.sql 內容

包含純 SQL DDL 陳述句，以 `--> statement-breakpoint` 分隔：

```sql
CREATE TABLE `offline_sale` (
	`name` text PRIMARY KEY NOT NULL,
	`pos_store_name` text NOT NULL,
	...
);
--> statement-breakpoint
CREATE TABLE `offline_sale_lines_items` (
	...
);
--> statement-breakpoint
CREATE INDEX `idx_offline_paid_at` ON `offline_sale` (`paid_at`);
```

### snapshot.json 內容

Schema 的完整快照，包含所有表、欄位、索引、外鍵的定義。
drizzle-kit 使用它來比對當前 schema 與上次 migration 的差異，產生增量 migration。

---

## npm scripts

| 指令 | 用途 | 說明 |
|------|------|------|
| `npm run db:generate` | 產生 migration | 從 schema 差異產生 SQL migration 檔案 |
| `npm run db:push` | 推送到本地 DB | 直接修改 DB schema，不產生 migration 檔案 |
| `npm run db:check` | 檢查一致性 | 驗證 migration 檔案與 schema 是否同步 |
| `npm run db:studio` | 開啟 Drizzle Studio | 視覺化 DB 管理介面 |
| `npm run db:reset` | 重置 DB | 刪除 migration + DB 檔案，重新 generate |

### 指令實際內容

```bash
# db:generate — 兩個 DB 各自產生
drizzle-kit generate --config=electron/drizzle.config.mutable.ts && \
drizzle-kit generate --config=electron/drizzle.config.readonly.ts

# db:push — 兩個 DB 各自推送
drizzle-kit push --config=electron/drizzle.config.mutable.ts && \
drizzle-kit push --config=electron/drizzle.config.readonly.ts

# db:check — 兩個 DB 各自檢查
drizzle-kit check --config=electron/drizzle.config.mutable.ts && \
drizzle-kit check --config=electron/drizzle.config.readonly.ts

# db:reset — 清除所有 migration 與 DB，重新產生
bash bin/db-reset.sh
```

---

## 日常開發工作流程

### 開發中：npm run dev 自動 push

`npm run dev`（`bin/dev.sh`）在啟動 Electron 之前**自動執行 `db:push`**，將當前 schema 直接同步到本地 DB。
開發時只需修改 schema，重啟 dev server 即可，無需手動 push。

```bash
# dev.sh 內部流程
npx drizzle-kit push --config=electron/drizzle.config.mutable.ts
npx drizzle-kit push --config=electron/drizzle.config.readonly.ts
# 啟動 Electron...
```

### Commit 前：產生 migration

```bash
# 從 schema 產生 migration
npm run db:generate

# 驗證 migration 與 schema 一致
npm run db:check
```

**MUST**：commit 前必須 `db:generate`，確保 migration 與 schema 同步。
否則 staging / production 啟動時 `migrate()` 不會套用最新 schema 變更。

### 需要重置開發環境

```bash
npm run db:reset
```

`db-reset.sh` 執行流程：
1. `taskkill` 結束 Electron 行程（釋放 DB 鎖）
2. 刪除 source migration 目錄（`electron/main/database/migrations/`）
3. 刪除 dist migration 目錄（`electron/dist/electron/main/database/migrations/`）
4. 刪除各環境（development / staging / production）的 DB 檔案
5. 重跑 `db:generate` 從頭產生 migration

---

## Migration 執行流程（Staging / Production）

**local dev 模式（`IS_LOCAL_DEV=1`）下不執行 migration**，因為 `db:push` 已直接同步 schema。

只有 staging / production 才執行以下流程：

```
[1] ensureDrizzleMigrationTable(sqlite, migrationsFolder)
    │
    ├─ 檢查 __drizzle_migrations 表是否存在
    │  ├─ 存在 → 跳過（正常流程）
    │  └─ 不存在 → 檢查是否有使用者表
    │     ├─ 沒有使用者表 → 跳過（全新 DB，讓 migrate() 建表）
    │     └─ 有使用者表 → 舊版 DB 相容處理
    │        ├─ 建立 __drizzle_migrations 表（v1 schema）
    │        ├─ 讀取所有 migration 目錄（按名稱排序）
    │        └─ 插入記錄：hash（SHA256）、created_at（folder 時間戳）、name（folder 名稱）
    │
    ▼
[2] migrate(db, { migrationsFolder })
    │
    ├─ 掃描 migrationsFolder 中的所有 migration 目錄
    ├─ 計算每個 migration.sql 的 SHA-256 hash
    ├─ 與 __drizzle_migrations.name 欄位比對（以 name 判斷是否已執行）
    ├─ 只執行 name 不在記錄中的 migration（增量執行）
    └─ 執行完成後寫入新記錄
```

---

## __drizzle_migrations 表結構（v1）

Drizzle v1 使用以下表結構（v1 schema）：

```sql
CREATE TABLE __drizzle_migrations (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    hash     TEXT NOT NULL,    -- migration.sql 的 SHA-256 hash
    created_at NUMERIC,        -- migration folder 的時間戳（UTC ms）
    name     TEXT,             -- migration folder 名稱（e.g. 20260320112530_nostalgic_captain_america）
    applied_at TEXT            -- 套用時間（ISO 8601 字串）
);
```

### 比對機制：用 name，不是 hash

`getMigrationsToRun()` 的邏輯：

```typescript
function getMigrationsToRun(params) {
    const dbNamesSet = new Set(dbMigrations.map((m) => m.name).filter((n) => n !== null));
    return localMigrations.filter((lm) => !lm.name || !dbNamesSet.has(lm.name));
}
```

**以 `name`（folder 名稱）判斷 migration 是否已執行，不是 hash。**
Hash 只用於資料完整性校驗，不影響執行邏輯。

---

## 舊版 DB 向後相容（ensureDrizzleMigrationTable）

### 問題場景

舊版系統使用 `node:sqlite` + 手寫 SQL 建表，DB 中沒有 `__drizzle_migrations` 表。
升級到 Drizzle ORM 後，`migrate()` 找不到 migration 記錄 → 嘗試重新 `CREATE TABLE` → 失敗（表已存在）。

### 受影響的情況

- 正式環境使用者升版（本地 DB 是舊版建的）
- 開發環境使用舊版 `.gz` 解壓的 readonly DB
- 任何在 Drizzle 遷移之前建立的 DB

### 解法：ensureDrizzleMigrationTable()

**關鍵設計**：直接建立 **v1 schema**（含 `name` 欄位），並正確填入 folder 名稱。

```typescript
export function ensureDrizzleMigrationTable(
    sqlite: DatabaseSync,
    migrationsFolder: string
): void {
    // 1. 已有 migration 表 → 正常流程，不做任何事
    const hasMigrationTable = sqlite
        .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='__drizzle_migrations'")
        .get() != null;
    if (hasMigrationTable) return;

    // 2. 全新 DB（沒有任何使用者表）→ 讓 migrate() 正常建表
    const userTables = sqlite
        .prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '__drizzle_%'")
        .all();
    if (userTables.length === 0) return;

    // 3. 舊版 DB：建立 v1 schema 表並標記所有現有 migration 為已完成
    //    v1 schema 含 name + applied_at，Drizzle 不需執行 v0→v1 升級流程
    sqlite.exec(`
        CREATE TABLE IF NOT EXISTS __drizzle_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT NOT NULL,
            created_at NUMERIC,
            name TEXT,
            applied_at TEXT
        );
    `);

    for (const dirName of migrationDirs) {
        const migrationSql = readFileSync(join(migrationsFolder, dirName, 'migration.sql'), 'utf-8');
        const hash = createHash('sha256').update(migrationSql).digest('hex');
        const folderMillis = parseFolderMillis(dirName); // 從 folder 名稱前 14 碼計算 UTC ms
        insertStmt.run(hash, folderMillis, dirName, null);
    }
}
```

### 為什麼必須用 v1 schema

Drizzle 內部在呼叫 `migrate()` 前，會先執行 `upgradeSyncIfNeeded()`：
- 若偵測到 v0 schema（無 `name` 欄位）→ 觸發複雜的 v0→v1 升級流程
- 升級時需用 millis 或 hash 比對 DB 記錄與 local migration，若不匹配會 throw error

直接建立 v1 schema 可完全繞過升級流程，`getMigrationsToRun()` 直接用 `name` 比對即可正確判斷哪些已執行。

### 三種情境的處理邏輯

| 情境 | 有 __drizzle_migrations | 有使用者表 | 處理方式 |
|------|------------------------|-----------|---------|
| 正常 DB | ✅ | ✅ | 跳過，讓 migrate() 正常增量執行 |
| 全新 DB | ❌ | ❌ | 跳過，讓 migrate() 從頭建表 |
| 舊版 DB | ❌ | ✅ | 建立 v1 記錄表 + 標記已完成 → migrate() 只跑新的 |

---

## Custom Migration 使用時機

`drizzle-kit generate` **無法偵測** rename 操作，會當作「刪舊 + 加新」= **資料丟失**。

### 必須使用 custom migration 的情況

| 操作 | 原因 |
|------|------|
| 改欄位名稱 | `ALTER TABLE RENAME COLUMN` — drizzle-kit 視為刪除 + 新增 |
| 改欄位型別 | SQLite 不支援直接改型別，需重建表 |

### Custom migration 步驟

1. 先用 `db:generate` 產生初始 migration
2. 手動修改 `migration.sql`，改為正確的 `ALTER TABLE RENAME COLUMN` 等語句
3. 同步修改 `snapshot.json`（或重新 generate 讓 snapshot 正確）
4. 執行 `db:check` 確認一致性

---

## Migration 與 .gz 初始 DB 的協作

```
[首次安裝]
.gz 解壓 → 得到已含表結構的 DB（無 __drizzle_migrations）
    ↓
ensureDrizzleMigrationTable() → 偵測舊版 DB，建立 v1 記錄，標記已有 migration 為完成
    ↓
migrate() → 只執行 .gz 版本之後新增的 migration

[升版]
新版 .gz 覆蓋舊 DB（如果版本更新）
    ↓
ensureDrizzleMigrationTable() → 重新標記（新 DB 同樣沒有 migration 記錄）
    ↓
migrate() → 補上 .gz 與最新 schema 之間的差異 migration
```

這確保了：
- 使用 `.gz` 初始化的 DB 不會重複執行已包含的 migration
- `.gz` 之後的 schema 變更會透過增量 migration 補上
- 整個流程對使用者透明，不需要手動操作

---

## create:init-db 腳本的建表機制

`scripts/create-initial-database.ts` 建立全新的 readonly DB（用於產生 `.gz` 初始資料庫），
**不走 migration 歷史**，改用 `drizzle-kit push` 直接同步當前 schema：

```typescript
function initializeTables(dbPath: string): void {
    // 透過 INIT_DB_URL env var 告知 drizzle.config.readonly.ts 目標路徑
    execSync(`npx drizzle-kit push --config=electron/drizzle.config.readonly.ts`, {
        stdio: 'inherit',
        cwd: projectRoot,
        env: { ...process.env, INIT_DB_URL: dbPath },
    });
}
```

`drizzle.config.readonly.ts` 會優先讀取 `INIT_DB_URL`：

```typescript
function getDevDbCredentials() {
    if (process.env.INIT_DB_URL) return { url: process.env.INIT_DB_URL };
    // ... 其餘邏輯
}
```

這樣確保 `create:init-db` 建出的 DB 永遠符合最新 schema，不受 migration 歷史狀態影響。

---

## 交易中的外鍵處理

Migration 和 replace 操作中使用 `PRAGMA defer_foreign_keys = ON`：

```sql
-- 在交易開始時
PRAGMA defer_foreign_keys = ON;

-- 執行 DDL / DML 操作
-- （此時外鍵約束暫時不檢查）

-- 交易 COMMIT 時才檢查外鍵約束
COMMIT;
```

這允許在交易中先刪除被引用的記錄再插入新記錄（先刪後寫的同步模式），
只要 COMMIT 時所有外鍵關係都成立即可。
