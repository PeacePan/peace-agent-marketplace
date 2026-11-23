/**
 * 本機驗收用的假中台世界。由 harness.sh 複製到 Abyssinian/.local-data/accept/ 之後以 tsx 執行（zod 等相依才找得到）。
 *
 * 為什麼用假中台：驗收要能「故意讓一筆內容不同」「新增員工看版本變化」，而共用的 dev 中台不能亂寫；
 * 假中台讓這些異動只發生在自己的行程裡，Worker 的讀取與編譯走的是真實程式碼。
 *
 * 做三件事：
 * 1. 以多工作階段版的假中台（fake-javacat-multi.mts，由 repo 內 test/integration/support/fake-javacat.ts 套 patch 產生）回應 Worker 的登入與查詢。
 *    Worker 同時有兩個 JavaCat client（機台狀態同步與來源讀取，各自登入），原檔只記得最後一次登入的工作階段，兩個 client 會互相踢掉。
 * 2. 灌入機台、令牌、門市、門市群組、活動與共用資料。
 * 3. 在控制埠提供 upsert／dump，並提供料件檔下載（假的檔案紀錄指向它）。
 *
 * 環境變數：FAKE_PORT（預設 3192）、CONTROL_PORT（預設 3193）、ITEM_COUNT（料件筆數，預設 30000）、READY_FILE（就緒時寫入假中台網址）。
 * 控制埠：
 * - GET  /ctl/dump?table=<表名>  回傳該表的表頭與表身
 * - GET  /ctl/count              回傳假中台被查詢的次數
 * - POST /ctl/upsert             本文 { table, record, lines?, touch? }；日期用 { "$date": "ISO 字串" }；touch 預設 true（更新 _updatedAt）
 * @example
 * ```
 * curl -s -X POST http://127.0.0.1:3193/ctl/upsert -d '{"table":"__user__","record":{"name":"U004","displayName":"新員工","level":"STAFF","disabled":false}}'
 * ```
 */
import { randomBytes } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'node:http';
import { gzipSync } from 'node:zlib';

import { startFakeJavaCat, type FakeJavaCat, type FakeRecord } from './fake-javacat-multi.mts';

const cFakePort: number = Number(process.env.FAKE_PORT ?? '3192');
const cControlPort: number = Number(process.env.CONTROL_PORT ?? '3193');
const cItemCount: number = Number(process.env.ITEM_COUNT ?? '30000');
const cReadyFile: string = process.env.READY_FILE ?? '.local-data/accept/run/fake.ready';
/** 與 harness.sh 寫進 .env 的 JAVACAT_ACCESS_KEY_ID、JAVACAT_SECRET_ACCESS_KEY 相同 */
const cCredentials: { accessKeyId: string; secretAccessKey: string } = { accessKeyId: 'accept-key', secretAccessKey: 'accept-secret-value' };
const cDay: number = 24 * 60 * 60 * 1000;
const cNow: Date = new Date();
const cCreated: Date = new Date(cNow.getTime() - 30 * cDay);
const cStartAt: Date = new Date(cNow.getTime() - 10 * cDay);
const cEndAt: Date = new Date(cNow.getTime() + 20 * cDay);
/** 種子機台：含停用機台、沒有 POS 前綴的純 5 碼機台、非 POS 命名的機台，用來驗證機台編號規則與同步狀態頁的分組 */
const cDevices: { name: string; enabled: boolean }[] = [
	{ name: 'POS00101', enabled: true },
	{ name: 'POS00102', enabled: true },
	{ name: 'POS00103', enabled: false },
	{ name: 'POS00111', enabled: true },
	{ name: 'POS00201', enabled: true },
	{ name: 'POS00202', enabled: true },
	{ name: 'POS00301', enabled: true },
	{ name: '00101', enabled: true },
	{ name: 'TEST-DEVICE-A', enabled: true },
];
/** 種子門市：001、002 屬北區，003 屬南區 */
const cStores: { no: string; name: string; area: string }[] = [
	{ no: '001', name: '台北信義店', area: '北區' },
	{ no: '002', name: '新北板橋店', area: '北區' },
	{ no: '003', name: '高雄左營店', area: '南區' },
];
/** 機台視角的 26 張同步表；每張都要有表格定義，後台才有中文顯示名稱 */
const cAllTables: string[] = [
	'pospromotion',
	'possalonpromotion',
	'posorderdiscount',
	'poscoupon',
	'possaloncoupon',
	'posvoucher',
	'posprintablecoupon',
	'feversocialgamesetting',
	'posfreebie',
	'posmallpromotionsetting',
	'posmallitemfilter',
	'givepointsetting',
	'pointpromotion',
	'petparkcouponevent',
	'item',
	'itemanimal',
	'itembrand',
	'itemcategory',
	'itemsmallcategory',
	'itemsubcategory',
	'serviceitem',
	'packageserviceitem',
	'partialitem',
	'posstoregroup',
	'posstore',
	'pospilot',
];
/** 有自訂欄位顯示名稱的表；其餘表只有「編號」「名稱」兩個欄位 */
const cLabelFields: Record<string, [string, string][]> = {
	pospromotion: [
		['name', '促銷編號'],
		['displayName', '促銷名稱'],
		['startAt', '開始時間'],
		['endAt', '結束時間'],
		['storeUsedAmount', '門市已用金額'],
		['target', '適用對象'],
	],
	posstore: [
		['name', '門市編號'],
		['displayName', '門市名稱'],
		['eGUIUniNo', '發票統一編號'],
		['eGUINoTitle', '發票抬頭'],
		['groupId', '群組編號'],
		['departmentId', '部門編號'],
		['taxNo', '稅籍編號'],
		['phoneNo', '電話'],
		['address', '地址'],
		['edenredClientId', 'Edenred 用戶編號'],
		['edenredClientSecret', 'Edenred 用戶密鑰'],
		['storeType', '門市類型'],
		['hasMedicamentLicense', '是否有藥商執照'],
		['isSailorCounterClosed', '水手櫃台是否已關閉'],
		['status', '營運狀態'],
		['storeManagementArea', '管理區域'],
		['storeTypeByRevenue', '營收分級'],
		['businessNo', '營業編號'],
	],
};

const fake: FakeJavaCat = await startFakeJavaCat(cCredentials, cFakePort);
seedDevices();
seedStores();
seedPromotions();
seedSharedData();
seedTableDefinitions();
const itemFile: Buffer = seedItemFile();
const control: Server = createServer((req: IncomingMessage, res: ServerResponse): void => {
	void handleControl(req, res, itemFile).catch((error: unknown): void => {
		res.statusCode = 500;
		res.end(String(error));
	});
});
await new Promise<void>((resolve: () => void): void => void control.listen(cControlPort, '127.0.0.1', resolve));
writeFileSync(cReadyFile, `${fake.endpoint}\n`);
console.log(
	`fake javacat ready: ${fake.endpoint}; control: http://127.0.0.1:${cControlPort}; item file bytes=${itemFile.byteLength}; items=${cItemCount}`,
);
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

/** 新增一筆表頭；_createdAt 預設為 30 天前，落在來源讀取的視窗之外，不會被當成剛建立 */
function add(table: string, record: FakeRecord): void {
	(fake.tables[table] ??= []).push({ _createdAt: cCreated, ...record });
}
/** 設定某筆表頭的表身 */
function addLines(table: string, key: string, rows: Record<string, FakeRecord[]>): void {
	const byKey: Record<string, Record<string, FakeRecord[]>> = (fake.lines[table] ??= {});
	byKey[key] = { ...(byKey[key] ?? {}), ...rows };
}
/** 機台與各自的令牌紀錄；令牌 2 天後到期 */
function seedDevices(): void {
	for (const device of cDevices) {
		add('__device__', { name: device.name, enabled: device.enabled });
		add('__devicetoken__', {
			name: `token-of-${device.name}`,
			deviceName: device.name,
			revoked: false,
			accessTokenExpiredAt: new Date(cNow.getTime() + 2 * cDay),
		});
	}
}
/** 門市、門市群組；edenredClientSecret 刻意帶 DO-NOT-SHOW，用來檢查後台與報告不會顯示密鑰欄位的值 */
function seedStores(): void {
	for (const store of cStores)
		add('posstore', {
			name: store.no,
			displayName: store.name,
			eGUIUniNo: '12345678',
			eGUINoTitle: '萬達寵物股份有限公司',
			groupId: 'G01',
			departmentId: `D${store.no}`,
			taxNo: `TAX${store.no}`,
			phoneNo: '02-2345-6789',
			address: `${store.name}地址 1 號`,
			edenredClientId: `EDEN-CLIENT-${store.no}`,
			edenredClientSecret: `EDEN-SECRET-${store.no}-DO-NOT-SHOW`,
			storeType: 'DIRECT',
			disableCheckAmountStartAt: null,
			disableCheckAmountEndAt: null,
			hasMedicamentLicense: store.no === '001',
			isSailorCounterClosed: false,
			status: 'OPEN',
			storeManagementArea: store.area,
			storeTypeByRevenue: 'A',
			businessNo: `BIZ${store.no}`,
		});
	add('posstoregroup', { name: '北區', displayName: '北區門市' });
	addLines('posstoregroup', '北區', { stores: [{ store: '001' }, { store: '002' }] });
	add('posstoregroup', { name: '南區', displayName: '南區門市' });
	addLines('posstoregroup', '南區', { stores: [{ store: '003' }] });
}
/** 組出活動的門市群組表身：每列是 [群組名稱, 允用或禁用] */
function groups(...rows: [string, 'ALLOW' | 'DENY'][]): FakeRecord[] {
	return rows.map(([groupName, effect]): FakeRecord => ({ groupName, effect, memo: null }));
}
/** 新增一筆活動與它的門市群組、每週表身；endsAt 預設 20 天後結束 */
function promotion(table: string, name: string, displayName: string, rows: FakeRecord[], endsAt: Date | null = cEndAt): void {
	add(table, { name, displayName, startAt: cStartAt, endAt: endsAt, storeUsedAmount: 12, target: 'ALL' });
	addLines(table, name, { storeGroups: rows, weekly: [{ day: 6 }, { day: 7 }] });
}
/**
 * 活動：商品促銷五筆（全區、北區允用、南區允用、除南區外、40 天前已結束）與其他活動表各一筆。
 * 專屬檔只該含「該門市適用」且「在讀取視窗內」的活動，所以 001／002 看得到 P-NORTH-01，003 看得到 P-SOUTH-01，P-OLD-01 誰都看不到。
 * P20261101 帶 3000 列料件表身，讓專屬檔大到足以測試續傳。
 */
function seedPromotions(): void {
	const bigItems: FakeRecord[] = Array.from({ length: 3000 }, (_, index: number): FakeRecord => ({
		item: `1${String(index).padStart(6, '0')}`,
		qty: 1,
	}));
	promotion('pospromotion', 'P20261101', '雙十一滿額折', []);
	addLines('pospromotion', 'P20261101', { items: bigItems, effects: [{ min: 1000, discount: 0.9 }] });
	promotion('pospromotion', 'P-NORTH-01', '北區限定買二送一', groups(['北區', 'ALLOW']));
	addLines('pospromotion', 'P-NORTH-01', { effects: [{ min: 2, discount: 0.5 }] });
	promotion('pospromotion', 'P-SOUTH-01', '南區限定週末折扣', groups(['南區', 'ALLOW']));
	addLines('pospromotion', 'P-SOUTH-01', { effects: [{ min: 500, discount: 0.85 }] });
	promotion('pospromotion', 'P-NOSOUTH-01', '除南區外的會員日', groups(['南區', 'DENY']));
	addLines('pospromotion', 'P-NOSOUTH-01', { effects: [{ min: 300, discount: 0.95 }] });
	promotion('pospromotion', 'P-OLD-01', '已結束很久的促銷', [], new Date(cNow.getTime() - 40 * cDay));
	promotion('posorderdiscount', 'O-ALL-01', '整單九折', []);
	promotion('posfreebie', 'F-ALL-01', '加購贈品', []);
	promotion('poscoupon', 'C-NORTH-01', '北區折扣碼', groups(['北區', 'ALLOW']));
	promotion('possalonpromotion', 'S-SOUTH-01', '南區美容促銷', groups(['南區', 'ALLOW']));
	add('givepointsetting', { name: 'GP-01', displayName: '點數卡加倍', type: 'POINT_CARD', startAt: cStartAt, endAt: null });
	addLines('givepointsetting', 'GP-01', { storeGroups: [], weekly: [] });
}
/** 共用資料：員工（帶 email、otp 這類不該進資料集的欄位）、品項分類、服務品項、分批取商品（其中一筆名稱帶前後空白） */
function seedSharedData(): void {
	const users: [string, string, string, boolean][] = [
		['U001', '王大明', 'MANAGER', false],
		['U002', '陳小美', 'STAFF', false],
		['U003', '林志強', 'STAFF', true],
	];
	for (const [name, displayName, level, disabled] of users)
		add('__user__', { name, displayName, level, disabled, email: `${name}@example.test`, otp: 'SECRET-OTP' });
	for (const [name, displayName] of [
		['DOG', '犬'],
		['CAT', '貓'],
		['BIRD', '鳥'],
	])
		add('itemanimal', { name, displayName });
	for (const [name, displayName] of [
		['B01', '皇家'],
		['B02', '希爾斯'],
		['B03', '冠能'],
	])
		add('itembrand', { name, displayName });
	for (const [name, displayName] of [
		['C01', '飼料'],
		['C02', '用品'],
	])
		add('itemcategory', { name, displayName });
	for (const [name, displayName] of [
		['SC01', '乾糧'],
		['SC02', '罐頭'],
	])
		add('itemsmallcategory', { name, displayName });
	for (const [name, displayName] of [
		['SUB01', '幼犬糧'],
		['SUB02', '成犬糧'],
	])
		add('itemsubcategory', { name, displayName });
	for (const [name, displayName] of [
		['SV01', '洗澡'],
		['SV02', '剪毛'],
	])
		add('serviceitem', { name, displayName, price: 600 });
	add('packageserviceitem', { name: 'PK01', displayName: '洗澡月包', times: 4 });
	addLines('packageserviceitem', 'PK01', { serviceItems: [{ serviceItem: 'SV01' }], applySpecies: [], storeGroups: groups(['北區', 'ALLOW']) });
	add('partialitem', { name: ' PI-1 ', displayName: '分批商品一（名稱帶前後空白）' });
	add('partialitem', { name: 'PI-2', displayName: '分批商品二' });
}
/** 每張同步表的表格定義：後台以它把欄位代碼翻成中文，所以畫面上不會出現代碼 */
function seedTableDefinitions(): void {
	for (const table of cAllTables) {
		fake.tables['__table__'] = [...(fake.tables['__table__'] ?? []), { _createdAt: cCreated, name: table, displayName: `表格 ${table}` }];
		const fields: [string, string][] = cLabelFields[table] ?? [
			['name', '編號'],
			['displayName', '名稱'],
		];
		(fake.lines['__table__'] ??= {})[table] = {
			bodyFields: fields.map(([name, displayName]): FakeRecord =>
				name === 'target' ? { name, displayName, enumName: 'target' } : { name, displayName },
			),
			lineFields: [
				{ lineName: 'storeGroups', name: 'groupName', displayName: '門市群組' },
				{ lineName: 'storeGroups', name: 'effect', displayName: '效力', enumName: 'effect' },
				{ lineName: 'weekly', name: 'day', displayName: '星期' },
				{ lineName: 'effects', name: 'min', displayName: '門檻' },
				{ lineName: 'effects', name: 'discount', displayName: '折扣率' },
				{ lineName: 'stores', name: 'store', displayName: '門市' },
			],
			lines: [
				{ name: 'storeGroups', displayName: '門市群組' },
				{ name: 'weekly', displayName: '每週' },
				{ name: 'effects', displayName: '優惠內容' },
				{ name: 'stores', displayName: '門市' },
			],
			enums: [
				{ enumName: 'target', name: 'ALL', displayName: '全部會員' },
				{ enumName: 'effect', name: 'ALLOW', displayName: '允用' },
				{ enumName: 'effect', name: 'DENY', displayName: '禁用' },
			],
		};
	}
}
/** 料件檔：gzip 的 JSON 陣列，由假的 __file2__ 檔案紀錄指到控制埠下載；沒有 name 欄位的檔案紀錄會讓 Worker 的料件檔同步失敗 */
function seedItemFile(): Buffer {
	const items: unknown[] = Array.from({ length: cItemCount }, (_, index: number): unknown => ({
		_id: `item-${String(index).padStart(6, '0')}`,
		body: {
			name: `2${String(index).padStart(7, '0')}`,
			displayName: `測試料件 ${randomBytes(6).toString('hex')} 號`,
			price: 100 + (index % 900),
			labelPrice: 120 + (index % 900),
		},
		lines: { barCodes: [{ barCode: `4710${randomBytes(4).readUInt32BE().toString().padStart(10, '0')}` }] },
	}));
	const file: Buffer = gzipSync(Buffer.from(JSON.stringify(items), 'utf8'));
	add('__file2__', {
		name: 'offline_items_latest.json.gz',
		displayName: 'offline_items_latest.json.gz',
		url: `http://127.0.0.1:${cControlPort}/offline_items_latest.json.gz`,
		fileSize: file.byteLength,
		_updatedAt: cCreated,
	});
	return file;
}
/** 把 { "$date": "..." } 還原成 Date，其餘原樣遞迴 */
function revive(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(revive);
	if (value === null || typeof value !== 'object') return value;
	const entries: [string, unknown][] = Object.entries(value);
	const first: [string, unknown] | undefined = entries[0];
	if (entries.length === 1 && first?.[0] === '$date' && typeof first[1] === 'string') return new Date(first[1]);
	return Object.fromEntries(entries.map(([key, inner]: [string, unknown]): [string, unknown] => [key, revive(inner)]));
}
/** 讀完整個請求本文 */
async function readBody(req: IncomingMessage): Promise<string> {
	const chunks: Buffer[] = [];
	for await (const chunk of req) chunks.push(Buffer.from(chunk));
	return Buffer.concat(chunks).toString('utf8');
}
/** 控制埠的路由：料件檔下載、dump、count、upsert；upsert 找到同名紀錄就更新並刷新 _updatedAt（Worker 靠它偵測異動），找不到就新增 */
async function handleControl(req: IncomingMessage, res: ServerResponse, file: Buffer): Promise<void> {
	const url: URL = new URL(req.url ?? '/', `http://127.0.0.1:${cControlPort}`);
	if (url.pathname === '/offline_items_latest.json.gz') {
		res.setHeader('content-type', 'application/gzip');
		res.setHeader('content-length', String(file.byteLength));
		res.end(file);
		return;
	}
	if (url.pathname === '/ctl/dump') {
		const table: string = url.searchParams.get('table') ?? '';
		res.setHeader('content-type', 'application/json');
		res.end(JSON.stringify({ table: fake.tables[table] ?? [], lines: fake.lines[table] ?? {} }));
		return;
	}
	if (url.pathname === '/ctl/count') {
		res.end(String(fake.findCount()));
		return;
	}
	if (url.pathname === '/ctl/upsert' && req.method === 'POST') {
		const input: UpsertInput = JSON.parse(await readBody(req)) as UpsertInput;
		const record: FakeRecord = revive(input.record) as FakeRecord;
		const list: FakeRecord[] = (fake.tables[input.table] ??= []);
		const existing: FakeRecord | undefined = list.find((candidate: FakeRecord): boolean => candidate['name'] === record['name']);
		if (existing === void 0) list.push({ _createdAt: new Date(), ...record });
		else Object.assign(existing, record, input.touch === false ? {} : { _updatedAt: new Date() });
		if (input.lines !== void 0) (fake.lines[input.table] ??= {})[String(record['name'])] = revive(input.lines) as Record<string, FakeRecord[]>;
		res.setHeader('content-type', 'application/json');
		res.end(JSON.stringify({ ok: true, created: existing === void 0, now: new Date().toISOString() }));
		return;
	}
	res.statusCode = 404;
	res.end('not found');
}
/** 收到停止訊號：先關控制埠與假中台再結束，結束碼 0 */
function shutdown(): void {
	void control.close();
	void fake.close().then((): void => process.exit(0));
}

/** upsert 的請求本文 */
type UpsertInput = {
	/** 中台表名 */
	table: string;
	/** 表頭；name 是鍵 */
	record: Record<string, unknown>;
	/** 表身；有給就整組取代該筆的表身 */
	lines?: Record<string, FakeRecord[]>;
	/** 是否刷新 _updatedAt，預設 true；false 用來模擬「內容變了但 Worker 看不出來」 */
	touch?: boolean;
};
