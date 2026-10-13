"""核对国服回收站配置，按生效奖池生成正文附录；默认只读。"""

import argparse
import base64
import copy
import datetime as dt
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "meta/回收站/new_recycle_data.json"
STATE = ROOT / "meta/回收站/产物配置.json"
DOC = ROOT / "docs/1-基础设定/设施与进驻/回收站机制.md"
REPO = "Kengxxiao/ArknightsGameData"
EXCEL = "zh_CN/gamedata/excel/"
API = f"https://api.github.com/repos/{REPO}"
CN = dt.timezone(dt.timedelta(hours=8))
HEADING = "## 附录：产物池明细"
RECYCLE_KEYS = (
    "recycleData", "recycleRoomConsts", "recycleRoomOutputPoolDatas",
    "recycleRoomOutputPoolContentDatas", "recycleRoomInputItemDatas",
)
GRADES = {1: "绿色", 2: "蓝色", 3: "紫色", 4: "金色"}


def read_json(path):
    raw = Path(path).read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def canonical(value):
    # 解包文件使用 PascalCase、枚举整数和 float32；公开 JSON 使用 camelCase。
    if isinstance(value, dict):
        return {(k if k == k.upper() else k[:1].lower() + k[1:]): canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return round(value, 6) if isinstance(value, float) else value


def make_snapshot(building, names, origin, extracted=False):
    s = building["sections"] if extracted else building
    data = {k: canonical(s[k]) for k in RECYCLE_KEYS}
    room = canonical(s["Rooms"]["RECYCLE"] if extracted else s["rooms"]["RECYCLE"])
    unlocks = canonical(s["RoomUnlockConds"] if extracted else {
        p["unlockCondId"]: s["roomUnlockConds"][p["unlockCondId"]] for p in room["phases"]
    })
    if extracted:
        room["id"], room["category"] = "RECYCLE", "FUNCTION"
        for phase in room["phases"]:
            for item in phase["buildCost"]["items"]:
                item["type"] = {3: "MATERIAL"}[item["type"]]
        for cond in unlocks.values():
            for required in cond["number"].values():
                required["type"] = {2048: "TRAINING", 1: "CONTROL"}[required["type"]]
    data["room"], data["unlocks"] = room, unlocks
    ids = set(data["recycleRoomInputItemDatas"])
    for pool in data["recycleRoomOutputPoolContentDatas"].values():
        for item in pool["items"]:
            ids.add(item["itemId"])
    items = {}
    for item_id in sorted(ids):
        item = names[item_id]
        rarity = item["rarity"]
        if isinstance(rarity, str):
            rarity = int(re.fullmatch(r"TIER_(\d+)", rarity)[1]) - 1
        if rarity not in GRADES or not item["name"] or "|" in item["name"] or "\n" in item["name"]:
            raise ValueError(f"材料品级或名称需人工校对：{item_id}")
        items[item_id] = {"name": item["name"], "rarity": rarity}
    return {"schema_version": 1, "origin": origin, "data": data, "items": items}


def load_snapshot(path):
    obj, digest = read_json(path)
    if "sections" in obj:
        return make_snapshot(obj, obj["sections"]["ItemNames"], {
            "kind": "user-extracted", "snapshot_sha256": digest,
            "source_sha256": obj["source_sha256"],
            "reference_url": obj["reference_url"],
            "reference_sha256": obj["reference_sha256"],
        }, extracted=True)
    if obj.get("schema_version") != 1:
        raise ValueError("产物配置快照 schema_version 需人工迁移")
    return obj


def parse_time(value):
    when = dt.datetime.fromisoformat(value)
    return when if when.tzinfo else when.replace(tzinfo=CN)


def select_pools(snapshot, when):
    data = snapshot["data"]
    timestamp = when.timestamp()
    active = [p for p in data["recycleRoomOutputPoolDatas"].values()
              if p["itemPoolStartTime"] <= timestamp <= p["itemPoolEndTime"]]
    if len(active) != 1:
        raise ValueError(f"指定时点命中 {len(active)} 个普通池，需核对时间或奖池配置")
    config = active[0]
    result = []
    for pool_id in [config["itemPoolId"], config["extraPoolId"]]:
        rows = data["recycleRoomOutputPoolContentDatas"][pool_id]["items"]
        seen = set()
        for row in rows:
            if set(row) != {"itemId", "targetTags", "weight", "count", "extraPoolValueChange", "isNew"}:
                raise ValueError(f"奖池条目结构变化：{pool_id}")
            item_id = row["itemId"]
            if item_id in seen:
                raise ValueError(f"奖池存在重复材料：{pool_id}/{item_id}")
            seen.add(item_id)
            if item_id not in snapshot["items"]:
                raise ValueError(f"缺少材料名称：{item_id}")
            for key, minimum in [("weight", 1), ("count", 1), ("extraPoolValueChange", 0)]:
                if type(row[key]) is not int or row[key] < minimum:
                    raise ValueError(f"无效 {key}：{pool_id}/{item_id}")
        if not rows:
            raise ValueError(f"奖池为空：{pool_id}")
        result.append({r["itemId"]: r for r in rows})
    return config, result


def baseline_pools(snapshot, when):
    # 上次接受的池可能已过期；基线仍对应上次生成正文时的有效池。
    return select_pools(snapshot, parse_time(snapshot.get("selected_at", when.isoformat())))


def mechanism_changes(before, after, old_pools, new_pools):
    changed = [k for k in ("recycleData", "recycleRoomConsts", "recycleRoomInputItemDatas", "room", "unlocks")
               if before["data"][k] != after["data"][k]]
    if old_pools[0]["extraPoolRequirement"] != new_pools[0]["extraPoolRequirement"]:
        changed.append("extraPoolRequirement")
    fuel_ids = before["data"]["recycleRoomInputItemDatas"].keys() & after["data"]["recycleRoomInputItemDatas"].keys()
    if any(before["items"][i] != after["items"][i] for i in fuel_ids):
        changed.append("投料材料名称/品级")
    for index, label in enumerate(["普通池", "特殊池"]):
        old_rows, new_rows = old_pools[1][index], new_pools[1][index]
        if old_rows.keys() != new_rows.keys():
            changed.append(label + "产物范围（需同步核对 SS 无限兑换材料口径）")
        def rules(snapshot, rows):
            return sorted({(snapshot["items"][i]["rarity"], r["count"], r["extraPoolValueChange"])
                           for i, r in rows.items()})
        if rules(before, old_rows) != rules(after, new_rows):
            changed.append(label + "品级/数量/积分规则")
        if any(old_rows[i]["targetTags"] != new_rows[i]["targetTags"] for i in old_rows.keys() & new_rows.keys()):
            changed.append(label + "targetTags")
    return changed


def probability(weight, total):
    value = Decimal(weight) * 100 / Decimal(total)
    shown = f"{value:.6f}"
    if Decimal(shown) == 0:
        return "<0.000001%"
    shown = shown.rstrip("0").rstrip(".")
    whole, _, fraction = shown.partition(".")
    return whole + "." + fraction.ljust(2, "0") + "%"


def render_appendix(snapshot, pools):
    _, (normal, special) = pools
    totals = [sum(r["weight"] for r in p.values()) for p in [normal, special]]
    ids = sorted(normal.keys() | special.keys(), key=lambda i: (snapshot["items"][i]["rarity"], i))
    if any(r["count"] != 1 for p in [normal, special] for r in p.values()):
        raise ValueError("附录的每项数量说明需随配置调整")
    lines = [HEADING, "", f"普通池 **{len(normal)} 项**，特殊池 **{len(special)} 项**；"
             f"总权重分别为 **{totals[0]}**、**{totals[1]}**。每个条目产出 **1 份**材料。", "",
             "> 池内概率 = 该材料权重 ÷ 所在池总权重。普通池与特殊池分别归一化。", "",
             "「—」表示该材料在对应池中无条目。", "",
             "| 品级 | 材料 | 普通池权重 | 普通池概率 | 普通池积分 | 特殊池权重 | 特殊池概率 |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for item_id in ids:
        item = snapshot["items"][item_id]
        cells = [GRADES[item["rarity"]], item["name"]]
        row = normal.get(item_id)
        cells += [str(row["weight"]), probability(row["weight"], totals[0]), str(row["extraPoolValueChange"])] if row else ["—"] * 3
        row = special.get(item_id)
        cells += [str(row["weight"]), probability(row["weight"], totals[1])] if row else ["—"] * 2
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def describe_changes(before, after, old_pools, new_pools):
    changes = []
    for index, label in enumerate(["普通池", "特殊池"]):
        old, new = old_pools[1][index], new_pools[1][index]
        for item_id in sorted(old.keys() | new.keys()):
            if old.get(item_id) != new.get(item_id) or before["items"].get(item_id) != after["items"].get(item_id):
                changes.append({"池": label, "材料": after["items"].get(item_id, before["items"].get(item_id)),
                                "原条目": old.get(item_id), "新条目": new.get(item_id)})
    if old_pools[0] != new_pools[0]:
        changes.append({"奖池生效配置": [old_pools[0], new_pools[0]]})
    return changes


def fetch_json(url, raw=False):
    headers = {"User-Agent": "arknights-base-vault", "Accept-Encoding": "gzip",
               "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json"}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            content = gzip.decompress(content)
    obj = json.loads(content)
    if raw and obj.get("encoding") == "base64":
        content = base64.b64decode(obj["content"])
        obj = json.loads(content)
    return obj, hashlib.sha256(content).hexdigest()


def fetch_snapshot(ref):
    if ref:
        commit, _ = fetch_json(API + "/commits/" + urllib.parse.quote(ref, safe=""))
    else:
        commits, _ = fetch_json(API + "/commits?" + urllib.parse.urlencode({"path": EXCEL + "building_data.json", "per_page": 1}))
        commit = commits[0]
    sha = commit["sha"]
    files, objects = {}, {}
    for name in ["building_data.json", "item_table.json"]:
        print(f"读取 {name} @ {sha[:12]}", flush=True)
        obj, digest = fetch_json(API + "/contents/" + EXCEL + name + "?ref=" + sha, raw=True)
        files[EXCEL + name], objects[name] = {"sha256": digest}, obj
    return make_snapshot(objects["building_data.json"], objects["item_table.json"]["items"], {
        "kind": "github", "repository": REPO, "commit": sha,
        "commit_date": commit["commit"]["committer"]["date"], "files": files,
    })


def replace_appendix(text, appendix, date):
    if text.count(HEADING) != 1:
        raise ValueError("正文附录标题应恰好出现一次")
    prefix, old = text.split(HEADING)
    if re.search(r"^## ", old, re.M):
        raise ValueError("附录应位于正文末尾")
    result = prefix + appendix
    return re.sub(r"(?m)^updated: \d{4}-\d{2}-\d{2}$", "updated: " + date, result, count=1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fetch", action="store_true", help="经 GitHub API 读取上游")
    mode.add_argument("--snapshot", type=Path, help="读取解包或规范化快照")
    mode.add_argument("--building-data", type=Path, help="读取已下载的上游 building_data.json")
    parser.add_argument("--item-table", type=Path)
    parser.add_argument("--commit", help="本地上游文件对应的完整 commit SHA")
    parser.add_argument("--ref", help="联网模式指定上游 commit 或 ref；省略则解析建筑文件最新 commit")
    parser.add_argument("--as-of", default=dt.datetime.now(CN).isoformat(timespec="seconds"), help="奖池选择时点，默认北京时间；建议显式传入带时区时间")
    parser.add_argument("--write", action="store_true", help="写入产物配置快照与正文附录")
    args = parser.parse_args(argv)
    if args.ref and not args.fetch:
        parser.error("--ref 与 --fetch 搭配使用")
    if (args.item_table or args.commit) and not args.building_data:
        parser.error("--item-table / --commit 与 --building-data 搭配使用")
    when = parse_time(args.as_of)
    before = load_snapshot(STATE if STATE.exists() else ORIGINAL)
    if args.fetch:
        after = fetch_snapshot(args.ref)
    elif args.building_data:
        if not args.item_table or not args.commit or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
            parser.error("本地上游模式须提供 --item-table 和完整 --commit SHA")
        building, building_hash = read_json(args.building_data)
        items, item_hash = read_json(args.item_table)
        after = make_snapshot(building, items["items"], {
            "kind": "github-local", "repository": REPO, "commit": args.commit,
            "files": {EXCEL + "building_data.json": {"sha256": building_hash},
                      EXCEL + "item_table.json": {"sha256": item_hash}},
        })
    else:
        after = load_snapshot(args.snapshot) if args.snapshot else copy.deepcopy(before)
    old_pools, new_pools = baseline_pools(before, when), select_pools(after, when)
    changes = describe_changes(before, after, old_pools, new_pools)
    blockers = mechanism_changes(before, after, old_pools, new_pools)
    appendix = render_appendix(after, new_pools)
    current = DOC.read_text(encoding="utf-8")
    updated = replace_appendix(current, appendix, when.astimezone(CN).date().isoformat())
    print(json.dumps({"时点": when.isoformat(), "普通池": new_pools[0]["itemPoolId"],
                      "特殊池": new_pools[0]["extraPoolId"], "材料变化": changes,
                      "需人工核对的机制变化": blockers, "附录一致": current.split(HEADING, 1)[-1] == appendix.split(HEADING, 1)[-1]}, ensure_ascii=False, indent=2))
    if args.write:
        if blockers:
            raise ValueError("机制发生变化，已保留现有正文与快照；请先校对机制与生成规则")
        after["selected_at"] = when.isoformat()
        state_text = json.dumps(after, ensure_ascii=False, indent=2) + "\n"
        for path, content in [(STATE, state_text), (DOC, updated)]:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                path.write_text(content, encoding="utf-8")
                print(f"已更新 {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError) as error:
        print(f"更新终止：{error}", file=sys.stderr)
        sys.exit(2)
