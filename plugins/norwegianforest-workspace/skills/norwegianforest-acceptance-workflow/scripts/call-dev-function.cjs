#!/usr/bin/env node
/**
 * 呼叫 dev 中台表格上的 function（JavaCat GraphQL 的 `call`）。
 *
 * 為什麼需要這支腳本：javacat MCP 只有 find／count／summarize／insert／update 等工具，
 * 沒有「呼叫 function」的工具，驗收 function 類的條件只能走 javacat-graphql-client。
 *
 * 用法：
 *   node call-dev-function.cjs --table <表名> --name <函式名稱> [--arg '<JSON 物件>'] [--dry]
 *
 * 範例：
 *   node call-dev-function.cjs --table posthirdpartypayment --name '建立大哥付分期付款交易' \
 *     --arg '{"saleName":"RD8070-ACC-01","amount":100,"storeName":"003","posConfigName":"00301"}'
 *
 * 注意事項：
 * - 只支援 dev。腳本只複製 MCP 憑證檔中 dev 的那一筆到暫存目錄，不碰 staging／production，
 *   結束時自動刪除暫存憑證。
 * - `--name` 是表格定義 `functions[].name` 註冊的名稱（多半是中文），不是腳本檔名。
 * - `--arg` 必須是 JSON 物件。javacat-graphql-client 的 `mutation.call` 會自己做 JSON.stringify，
 *   若先轉成字串再傳，函式收到的會是字串（雙重序列化），常見症狀是「缺少 XXX」之類的欄位驗證錯誤。
 * - 會產生外部副作用的函式（簡訊、金流、寫入 NetSuite 等）請先加 `--dry` 確認要呼叫的內容，
 *   取得使用者同意後再正式執行，而且只執行一次。
 * - 找不到 javacat-graphql-client 時，用環境變數 JAVACAT_GRAPHQL_CLIENT_PATH 指定套件目錄。
 */
'use strict';

const fs = require('fs');
const os = require('os');
const path = require('path');

const DEV_DOMAIN = 'data-api-development.wonderpet.asia';
const CERT_PATH = path.join(os.homedir(), '.local', 'share', 'mcp-wonderpet-table', 'certificate.json');

function fail(message) {
	console.error(`ERROR ${message}`);
	process.exit(1);
}

/** 解析 --key value 形式的參數；--dry 為旗標 */
function parseArgs(argv) {
	const result = { dry: false };
	for (let i = 0; i < argv.length; i++) {
		const key = argv[i];
		if (key === '--dry') result.dry = true;
		else if (key === '--table' || key === '--name' || key === '--arg') result[key.slice(2)] = argv[++i];
		else fail(`不認得的參數：${key}`);
	}
	return result;
}

/** 由目前目錄往上找，並補上常見安裝位置，找出 javacat-graphql-client 套件目錄 */
function locateClientPackage() {
	const candidates = [];
	if (process.env.JAVACAT_GRAPHQL_CLIENT_PATH) candidates.push(process.env.JAVACAT_GRAPHQL_CLIENT_PATH);
	const roots = [];
	for (let dir = process.cwd(); ; dir = path.dirname(dir)) {
		roots.push(dir);
		if (path.dirname(dir) === dir) break;
	}
	roots.push(path.join(os.homedir(), 'workspace', 'petpetgo'));
	for (const root of roots) {
		for (const sub of ['Ragdoll', 'Utonagan', '.']) {
			candidates.push(path.join(root, sub, 'node_modules', 'javacat-graphql-client'));
		}
	}
	const found = candidates.find((dir) => fs.existsSync(path.join(dir, 'package.json')));
	if (!found) fail('找不到 javacat-graphql-client，請設定 JAVACAT_GRAPHQL_CLIENT_PATH 指向套件目錄');
	return found;
}

/** 讀出 dev 憑證；MCP 尚未登入 dev 時直接說明原因 */
function readDevCredential() {
	if (!fs.existsSync(CERT_PATH)) fail(`找不到 MCP 憑證檔 ${CERT_PATH}，請先用 javacat MCP 登入 dev`);
	const cert = JSON.parse(fs.readFileSync(CERT_PATH, 'utf8'));
	const dev = cert[DEV_DOMAIN];
	if (!dev || !dev.jwt || !dev.cookies) fail('MCP 憑證檔裡沒有 dev 的登入資訊，請先用 javacat MCP 登入 dev');
	return { jwt: dev.jwt, cookies: dev.cookies };
}

function parseArgument(raw) {
	let parsed;
	try {
		parsed = JSON.parse(raw ?? '{}');
	} catch (error) {
		return fail(`--arg 不是合法的 JSON：${error.message}`);
	}
	const isPlainObject = typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed);
	if (!isPlainObject) fail('--arg 必須是 JSON 物件（不可是字串或陣列），避免被雙重序列化');
	return parsed;
}

async function main() {
	const args = parseArgs(process.argv.slice(2));
	if (!args.table || !args.name) fail('必須提供 --table 與 --name');
	const argument = parseArgument(args.arg);

	console.log(`目標：dev／${args.table}／${args.name}`);
	console.log(`參數：${JSON.stringify(argument)}`);
	if (args.dry) {
		console.log('DRY 僅列出將要呼叫的內容，未送出任何請求');
		return;
	}

	const credential = readDevCredential();
	const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'nf-acceptance-'));
	const authPath = path.join(tmpDir, 'graphql-auth.json');
	process.on('exit', () => fs.rmSync(tmpDir, { recursive: true, force: true }));
	fs.writeFileSync(authPath, JSON.stringify({ [DEV_DOMAIN]: credential }), { mode: 0o600 });

	const { JavaCatGraphQLClient } = require(locateClientPackage());
	const client = new JavaCatGraphQLClient({ env: 'dev', authEnvPath: authPath });
	if (!client.isSignedIn) fail('dev 憑證已過期，請先用 javacat MCP 重新登入 dev');
	const auth = await client.auth.authenticate();
	console.log(`登入身分：${auth.user && auth.user.name}`);

	try {
		const result = await client.mutation.call({ table: args.table, name: args.name, argument });
		console.log(`RESULT ${JSON.stringify(result)}`);
	} catch (error) {
		fail(error && error.message ? error.message : String(error));
	}
}

main().catch((error) => fail(error && error.message ? error.message : String(error)));
