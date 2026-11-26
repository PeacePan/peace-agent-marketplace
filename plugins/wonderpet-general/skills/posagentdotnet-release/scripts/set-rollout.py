#!/usr/bin/env python3
"""改寫 Online Update manifest.json 的 rollout（灰度）欄位，其餘欄位原樣保留。

make-release.sh 沒有灰度參數，產出的 manifest 一律是「全部門市、percent=100」，
要限定門市就得改這個欄位。用這支腳本改，比手改 JSON 不容易出錯，也不依賴 jq（本機沒裝）。

用法：
  set-rollout.py <manifest.json> --stores POS0039FTEST[,POS0001,...] [--percent 100]
  set-rollout.py <manifest.json> --all      還原為全部門市（stores=null、percent=100）

規則來源：publish-release.sh 的 manifest 檢查
  - stores 必須是 null（全部門市）或非空字串陣列
  - percent 必須是 0~100 的整數
白名單只填門市代號本身；比對時不分大小寫，且比對的是機台 appsettings.json 的 Update:StoreId。
"""

import argparse
import json
import os
import sys
import tempfile
from typing import List, Optional


def parse_stores(raw: str) -> List[str]:
    """把逗號分隔的門市代號轉成去除空白、去重（保留順序）的清單，有空項目就視為錯誤。"""
    items: List[str] = [part.strip() for part in raw.split(",")]
    if not items or any(not item for item in items):
        raise ValueError("--stores 含有空的門市代號（逗號前後不可留空）")
    seen: List[str] = []
    for item in items:
        if item.lower() not in [s.lower() for s in seen]:
            seen.append(item)
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(description="改寫 manifest.json 的 rollout 欄位")
    parser.add_argument("manifest", help="manifest.json 路徑（通常是 dist/release/<版本>/manifest.json）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stores", help="限定門市，逗號分隔，例如 POS0039FTEST,POS0001")
    group.add_argument("--all", action="store_true", help="全部門市（stores=null、percent=100）")
    parser.add_argument("--percent", type=int, default=100, help="灰度百分比 0~100，預設 100")
    args = parser.parse_args()

    if args.all and args.percent != 100:
        print("✗ --all 代表全量推送，不可搭配 --percent", file=sys.stderr)
        return 2
    if not 0 <= args.percent <= 100:
        print(f"✗ --percent 必須是 0~100 的整數（收到 {args.percent}）", file=sys.stderr)
        return 2

    stores: Optional[List[str]] = None
    if args.stores is not None:
        try:
            stores = parse_stores(args.stores)
        except ValueError as error:
            print(f"✗ {error}", file=sys.stderr)
            return 2

    try:
        with open(args.manifest, encoding="utf-8") as handle:
            manifest = json.load(handle)
    except (OSError, ValueError) as error:
        print(f"✗ 讀取或解析 {args.manifest} 失敗：{error}", file=sys.stderr)
        return 1

    if not isinstance(manifest, dict) or "version" not in manifest:
        print("✗ 這不像 make-release.sh 產出的 manifest（缺少 version 欄位）", file=sys.stderr)
        return 1

    manifest["rollout"] = {"stores": stores, "percent": args.percent}

    # 先寫暫存檔再取代，避免寫到一半被中斷而留下壞掉的 manifest。
    directory = os.path.dirname(os.path.abspath(args.manifest))
    fd, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, args.manifest)
    except OSError as error:
        os.unlink(temp_path)
        print(f"✗ 寫入失敗：{error}", file=sys.stderr)
        return 1

    scope = "全部門市" if stores is None else "限定門市 " + ", ".join(stores)
    print(f"✓ {args.manifest}：版本 {manifest['version']}，rollout = {scope}，percent = {args.percent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
