/**
 * 以本機簽發的機台令牌檢視 Abyssinian 的機台端點：驗收時不必手寫 curl 加 jq（這台機器沒有 jq）。
 * 由 harness.sh 複製到 Abyssinian/.local-data/accept/ 後以 `node_modules/.bin/tsx` 在 Abyssinian/ 目錄執行。
 *
 * 只允許連本機（127.0.0.1、localhost、[::1]）：令牌是用本機假密鑰（.env 的 DEVICE_TOKEN_SECRET）簽的，遠端環境的令牌是真實令牌，不簽發。
 * 輸出只有名稱、版本、筆數、大小、sha256 前 8 碼與狀態，不印令牌；資料集內容只印每筆的 name，不印其他欄位（專屬資料集含門市密鑰欄位）。
 *
 * 用法（--device 預設是 POS＋門市編號＋01）：
 *   tsx device-peek.mts --base-url <網址> --store 001 manifest
 *   tsx device-peek.mts --base-url <網址> --store 001 dataset pospromotion [--version 1] [--save <檔案>]
 *   tsx device-peek.mts --base-url <網址> shared-diff 001,002,003
 *   tsx device-peek.mts --base-url <網址> --store 001 get /api/v1/device/datasets/__user__?version=99
 *
 * 指令：
 *   manifest        列出該門市 manifest 的 ETag 與每個資料集的範疇、版本、筆數、大小、sha256 前 8 碼
 *   dataset <名稱>   下載資料集（依 manifest 的範疇走共用或專屬路徑；--version 指定版本，預設 manifest 的版本），
 *                   驗證本文的 sha256 等於回應標頭與 manifest，印每筆的 name；--save 把原始位元組存檔
 *   shared-diff     對每間門市各自取 manifest，比對所有「共用」條目是否逐字相同，並列出各門市專屬條目的版本
 *   get <路徑>       對任意路徑 GET，印狀態碼與關鍵標頭（etag、content-range、content-length、x-content-sha256、cache-control）與本文長度
 * 結束碼：0 正常；1 驗證不符（sha256 不一致、共用條目不同）；2 參數錯誤。
 */
import { createHash } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';

import { readLocalSecret, signLocalDeviceToken } from '../../scripts/lib/device-token';

const cLocalHosts: string[] = ['127.0.0.1', 'localhost', '[::1]'];
const cArgs: Args = parseArgs(process.argv.slice(2));

main().then((code: number): void => {
	process.exitCode = code;
});

/** 依指令分派 */
async function main(): Promise<number> {
	const url: URL = new URL(cArgs.baseUrl);
	if (!cLocalHosts.includes(url.hostname)) fatal(`只允許本機目標，收到 ${url.hostname}`);
	switch (cArgs.command) {
		case 'manifest':
			return showManifest(requireStore());
		case 'dataset':
			return showDataset(requireStore(), cArgs.rest[0] ?? fatal('dataset 需要資料集名稱'));
		case 'shared-diff':
			return sharedDiff((cArgs.rest[0] ?? fatal('shared-diff 需要門市清單，例如 001,002,003')).split(','));
		case 'get':
			return rawGet(requireStore(), cArgs.rest[0] ?? fatal('get 需要路徑'));
		default:
			return fatal('指令必須是 manifest、dataset、shared-diff、get 之一');
	}
}
/** 取得這次要用的門市編號 */
function requireStore(): string {
	return cArgs.store ?? fatal('這個指令需要 --store');
}
/** 簽發某門市某台機台的本機令牌；機台預設是 POS＋門市編號＋01 */
function tokenFor(store: string): string {
	return signLocalDeviceToken({ secret: readLocalSecret(process.env), deviceName: cArgs.device ?? `POS${store}01` });
}
/** 對機台端點 GET；帶令牌，要求不壓縮 */
async function get(store: string, path: string): Promise<Response> {
	return fetch(new URL(path, cArgs.baseUrl), { headers: { authorization: `Bearer ${tokenFor(store)}`, 'accept-encoding': 'identity' } });
}
/** 取 manifest 並解析；非 200 就結束 */
async function fetchManifest(store: string): Promise<Manifest> {
	const res: Response = await get(store, `/api/v1/device/stores/${store}/manifest`);
	if (res.status !== 200) fatal(`門市 ${store} 的 manifest 回 ${res.status}`);
	return (await res.json()) as Manifest;
}
/** 一行 manifest 條目的摘要 */
function summarize(entry: ManifestEntry): string {
	return `${entry.scope.padEnd(6)} ${entry.name.padEnd(26)} v${String(entry.version).padEnd(4)} 筆數=${String(entry.recordCount).padEnd(6)} 大小=${String(entry.size).padEnd(8)} sha256=${entry.sha256.slice(0, 8)}`;
}
/** manifest 指令 */
async function showManifest(store: string): Promise<number> {
	const manifest: Manifest = await fetchManifest(store);
	console.log(`門市 ${store} manifest etag=${manifest.etag}，共 ${manifest.datasets.length} 個資料集`);
	for (const entry of manifest.datasets) console.log(summarize(entry));
	return 0;
}
/** dataset 指令：下載、驗 sha256、列出每筆的 name */
async function showDataset(store: string, name: string): Promise<number> {
	const manifest: Manifest = await fetchManifest(store);
	const entry: ManifestEntry =
		manifest.datasets.find((candidate: ManifestEntry): boolean => candidate.name === name) ?? fatal(`manifest 沒有 ${name}`);
	const version: number = cArgs.version ?? entry.version;
	const path: string =
		entry.scope === 'shared'
			? `/api/v1/device/datasets/${name}?version=${version}`
			: `/api/v1/device/stores/${store}/datasets/${name}?version=${version}`;
	const res: Response = await get(store, path);
	console.log(`GET ${path} → ${res.status}`);
	if (res.status !== 200) return 1;
	const bytes: Buffer = Buffer.from(await res.arrayBuffer());
	const sha: string = createHash('sha256').update(bytes).digest('hex');
	const headerSha: string | null = res.headers.get('x-content-sha256');
	const matchesHeader: boolean = sha === headerSha;
	const matchesManifest: boolean = version !== entry.version || sha === entry.sha256;
	console.log(
		`版本=${version} 大小=${bytes.byteLength} sha256=${sha.slice(0, 8)} 標頭相符=${matchesHeader} manifest 相符=${version === entry.version ? matchesManifest : '（指定了舊版本，不與目前 manifest 比）'}`,
	);
	if (cArgs.save !== void 0) writeFileSync(cArgs.save, bytes);
	console.log(`各筆 name：${recordNames(entry, bytes).join('、')}`);
	return matchesHeader && matchesManifest ? 0 : 1;
}
/** 取出資料集每筆的 name：jsonl 一行一筆；file 是 gzip 的 JSON 陣列，只回筆數 */
function recordNames(entry: ManifestEntry, bytes: Buffer): string[] {
	if (entry.kind === 'file') return [`（gzip 的 JSON 陣列，${(JSON.parse(gunzipSync(bytes).toString('utf8')) as unknown[]).length} 筆）`];
	const names: string[] = [];
	for (const line of bytes.toString('utf8').split('\n')) {
		if (line === '') continue;
		const record: Record<string, unknown> = JSON.parse(line) as Record<string, unknown>;
		const body: Record<string, unknown> | undefined =
			typeof record.body === 'object' && record.body !== null ? (record.body as Record<string, unknown>) : void 0;
		names.push(String(record.name ?? body?.name ?? record._id ?? '?').trim());
	}
	return names;
}
/** shared-diff 指令：各門市 manifest 的共用條目應逐字相同 */
async function sharedDiff(stores: string[]): Promise<number> {
	const manifests: (Manifest & { store: string })[] = [];
	for (const store of stores) manifests.push({ store, ...(await fetchManifest(store)) });
	const sharedOf: (datasets: ManifestEntry[]) => string = (datasets: ManifestEntry[]): string =>
		JSON.stringify(datasets.filter((entry: ManifestEntry): boolean => entry.scope === 'shared'));
	const reference: string = sharedOf(manifests[0].datasets);
	let allSame: boolean = true;
	for (const manifest of manifests) {
		const same: boolean = sharedOf(manifest.datasets) === reference;
		allSame = allSame && same;
		const storeEntries: string = manifest.datasets
			.filter((entry: ManifestEntry): boolean => entry.scope === 'store')
			.map((entry: ManifestEntry): string => `${entry.name}=v${entry.version}`)
			.join(' ');
		console.log(`門市 ${manifest.store}：共用條目與 ${manifests[0].store} ${same ? '逐字相同' : '不同'}；manifest etag=${manifest.etag}`);
		console.log(`  專屬版本：${storeEntries}`);
	}
	console.log(
		`共用條目 sha256：${manifests[0].datasets
			.filter((entry: ManifestEntry): boolean => entry.scope === 'shared')
			.map((entry: ManifestEntry): string => `${entry.name}@v${entry.version}:${entry.sha256.slice(0, 8)}`)
			.join(' ')}`,
	);
	return allSame ? 0 : 1;
}
/** get 指令 */
async function rawGet(store: string, path: string): Promise<number> {
	const res: Response = await get(store, path);
	const bytes: Buffer = Buffer.from(await res.arrayBuffer());
	console.log(`GET ${path} → ${res.status}，本文 ${bytes.byteLength} 位元組`);
	for (const name of ['etag', 'content-range', 'content-length', 'x-content-sha256', 'cache-control', 'content-encoding', 'location'])
		if (res.headers.has(name)) console.log(`  ${name}: ${res.headers.get(name)}`);
	return 0;
}
/** 解析命令列 */
function parseArgs(argv: string[]): Args {
	const args: Args = { baseUrl: '', command: '', rest: [] };
	for (let index = 0; index < argv.length; index++) {
		const arg: string = argv[index];
		if (arg === '--base-url') args.baseUrl = argv[++index] ?? '';
		else if (arg === '--store') args.store = argv[++index];
		else if (arg === '--device') args.device = argv[++index];
		else if (arg === '--version') args.version = Number(argv[++index]);
		else if (arg === '--save') args.save = argv[++index];
		else if (args.command === '') args.command = arg;
		else args.rest.push(arg);
	}
	if (args.baseUrl === '') fatal('需要 --base-url');
	return args;
}
/** 印錯誤並以 2 結束 */
function fatal(message: string): never {
	console.error(`錯誤：${message}`);
	process.exit(2);
}

/** 命令列參數 */
type Args = {
	/** 目標網址，必須是本機 */
	baseUrl: string;
	/** 門市編號 */
	store?: string;
	/** 機台編號，預設 POS＋門市編號＋01 */
	device?: string;
	/** 指定下載的版本 */
	version?: number;
	/** 存檔路徑 */
	save?: string;
	/** 指令 */
	command: string;
	/** 指令之後的位置參數 */
	rest: string[];
};
/** manifest：ETag 與全部資料集條目 */
type Manifest = {
	/** 整份清單的 ETag（含雙引號） */
	etag: string;
	/** 資料集條目，共用在前、專屬在後 */
	datasets: ManifestEntry[];
};
/** manifest 的一個條目 */
type ManifestEntry = {
	name: string;
	scope: 'shared' | 'store';
	version: number;
	kind: 'jsonl' | 'file';
	sha256: string;
	size: number;
	recordCount: number;
};
