#!/usr/bin/env python3
"""
RMMZ (RPG Maker MZ/MV) CommonEvents.json → WebGAL 剧本 (.txt) 转换器

读取游戏的 data/CommonEvents.json，把 H-scene 事件转换为 WebGAL 剧本：
  - 对话 101/401        →  角色:台词;
  - 显示图片 231         →  changeBg:<gallery_url>;   (CG 用 ExHentai gallery 外链)
  - 移动图片 232         →  切到对应图 (差分切换)
  - 白闪 224            →  flash:<hex> -duration=<ms>;   (默认开，--no-flash 关)
  - 淡入淡出 221/222     →  setTransition;
  - 选择 102/402         →  choose:...; + label:;
  - 条件 111/411/412     →  保留 true 分支，跳过 else
  - 切公共事件 117       →  目标 10 = CG 清除，转为 changeBg:none
  - label 118 / jump 119 →  label: / jumpLabel:
  - BGM 241 / BGS 245    →  bgm:<url>;    (默认关，--bgm 开)
  - SE 250 / 246 停      →  playEffect:<url>;   (默认关，--se 开)

音频 URL 来源（--bgm/--se 开启时）：
  - --audio-base <前缀>：文件名前缀拼接，如 https://cdn/audio/{name}.mp3
  - --audio-map <json>  ：{文件名: URL} 映射文件（如 R2/S3 bucket）

CG 文件名映射规则：游戏内 'HA1-3' → gallery 'HA1_3.png'
  gallery 图片名 = 游戏 img/pictures 文件名（- 转 _，去掉 ^ 差分后缀，加 .png）
"""
import json
import sys
import argparse
from pathlib import Path

# ── 配置 ──
GAME_DIR = Path("/mnt/c/Users/lumin/Downloads/otomi-games.com_KGB6FSSY0/RJ01353427/イルと貧乳の国")
CE_PATH = GAME_DIR / "data" / "CommonEvents.json"
CG_MAP_PATH = Path("/tmp/opencode/cg_map.json")
OUT_DIR = Path("/mnt/d/WorkPlace/WebGAL/packages/webgal/public/game/scene")

# 事件 ID → 输出文件名
EVENT_MAP = {
    25: "ha1", 26: "ha2", 27: "ha3",
    33: "hbstart", 34: "hb1", 35: "hb2",
    39: "t21", 40: "t22", 41: "t22inran",
    42: "hc1", 44: "hc3",
    54: "t3", 55: "hd1", 56: "hd2", 57: "hd3",
    60: "he1", 61: "he2", 63: "hf1", 65: "hg1",
}

def parse_args():
    ap = argparse.ArgumentParser(description="RMMZ CommonEvents → WebGAL 剧本转换器")
    ap.add_argument("--no-flash", action="store_true", help="不转换画面闪烁(224)")
    ap.add_argument("--bgm", action="store_true", help="转换 BGM(241)/BGS(245) 为 bgm 指令")
    ap.add_argument("--se", action="store_true", help="转换 SE(250) 为 playEffect 指令")
    ap.add_argument("--audio-base", default="", help="音频 URL 前缀，如 https://cdn.example.com/audio")
    ap.add_argument("--audio-map", default="", help="音频文件名→URL 的 JSON 映射文件")
    ap.add_argument("--cg-map", default=str(CG_MAP_PATH), help="CG 文件名→URL 映射 JSON")
    ap.add_argument("--out", default=str(OUT_DIR), help="输出目录")
    ap.add_argument("--events", default="", help="只转换指定事件ID，逗号分隔（默认全部）")
    return ap.parse_args()

# ── 加载 CG 映射 ──
def load_cg_map(cg_map_path):
    with open(cg_map_path, encoding="utf-8") as f:
        raw = json.load(f)  # {filename: {url, page}}
    return {name: info["url"] for name, info in raw.items()}

def cg_url(cg_map, rmmz_name):
    """游戏图名(HA1-3 / HA1-3^) → gallery URL"""
    alt = rmmz_name.replace("-", "_").replace("^", "") + ".png"
    url = cg_map.get(alt)
    return url, alt

# ── 主转换 ──
def audio_url_for(name, opts):
    """根据 opts 配置返回音频 URL（audio-base 拼接或 audio-map 查询）。无则 None。"""
    if not name:
        return None
    if opts.audio_map:
        audio_map = getattr(opts, "_audio_map_data", None)
        if audio_map is None:
            audio_map = {}
            try:
                with open(opts.audio_map, encoding="utf-8") as f:
                    audio_map = json.load(f)
            except Exception:
                pass
            opts._audio_map_data = audio_map
        url = audio_map.get(name)
        if url:
            return url
        # 也试带扩展名
        for ext in (".ogg", ".m4a", ".mp3", ".wav"):
            if audio_map.get(name + ext):
                return audio_map[name + ext]
    if opts.audio_base:
        return f"{opts.audio_base}/{name}.ogg"
    return None

def convert_event(ev, cg_map, opts, log):
    """把单个事件 list 转为 WebGAL 行。返回 str 列表。"""
    cmds = ev["list"]
    out = []
    current_cg = None
    pic_map = {}  # pic_id -> 图名（231 建立，232 切换用）

    # 预处理：收集 label 名，用于跳转去重
    labels = set()
    for c in cmds:
        if c["code"] == 118:
            labels.add(c["parameters"][0])

    i = 0
    while i < len(cmds):
        c = cmds[i]
        code = c["code"]
        p = c["parameters"]

        if code == 0:
            i += 1
            continue

        elif code == 101:  # 对话开始
            speaker = p[4] if len(p) > 4 else ""
            i += 1
            texts = []
            while i < len(cmds) and cmds[i]["code"] == 401:
                texts.append(cmds[i]["parameters"][0])
                i += 1
            full = "\n".join(texts)
            if speaker:
                out.append(f"{speaker}:{full};")
            else:
                out.append(f":{full};")
            continue

        elif code == 231:  # 显示图片
            pic_id = p[0]
            name = p[1]
            pic_map[pic_id] = name
            url, alt = cg_url(cg_map, name)
            if url:
                # 连续 changeBg 块压缩：只保留第一张（后续由 232 差分切换）
                if not (out and out[-1].startswith("changeBg:")):
                    out.append(f"changeBg:{url};")
                current_cg = name
            else:
                log.write(f"  !! 图 {name} → gallery 无 {alt}\n")
            i += 1
            continue

        elif code == 232:  # 移动图片 → 切到对应图（差分切换）
            pic_id = p[0]
            target = pic_map.get(pic_id)
            if target:
                url, alt = cg_url(cg_map, target)
                if url:
                    if out and out[-1].startswith("changeBg:"):
                        out[-1] = f"changeBg:{url};"
                    else:
                        out.append(f"changeBg:{url};")
                    current_cg = target
                else:
                    log.write(f"  !! 232 图 {target} → gallery 无 {alt}\n")
            i += 1
            continue

        elif code == 224:  # 白闪 [[r,g,b,a], frames, wait]
            if opts.no_flash:
                i += 1
                continue
            if len(p) >= 2:
                rgba, frames, wait = p[0], p[1], (p[2] if len(p) > 2 else False)
                r, g, b = rgba[0], rgba[1], rgba[2]
                ms = frames * 1000 / 60
                hexc = f"#{r:02x}{g:02x}{b:02x}"
                out.append(f"flash:{hexc} -duration={int(ms)};")
            i += 1
            continue

        elif code == 241:  # BGM
            if opts.bgm:
                audio_url = audio_url_for(p[0].get("name", "") if p else "", opts)
                if audio_url:
                    out.append(f"bgm:{audio_url};")
            i += 1
            continue

        elif code == 245:  # BGS（循环环境音）→ bgm
            if opts.bgm:
                name = p[0].get("name", "") if p and isinstance(p[0], dict) else ""
                audio_url = audio_url_for(name, opts)
                if audio_url:
                    out.append(f"bgm:{audio_url};")
            i += 1
            continue

        elif code == 246:  # 停止 BGS → bgm:none
            if opts.bgm:
                out.append("bgm:none;")
            i += 1
            continue

        elif code == 250:  # SE → playEffect
            if opts.se:
                name = p[0].get("name", "") if p else ""
                audio_url = audio_url_for(name, opts)
                if audio_url:
                    out.append(f"playEffect:{audio_url};")
            i += 1
            continue

        elif code in (221, 222):  # 淡出/淡入 → setTransition
            i += 1
            continue

        elif code in (357, 355, 108, 408, 233, 234, 205, 212, 301, 351):
            i += 1  # 脚本/注释/其它：跳过
            continue

        elif code == 102:  # 选项
            choices_raw = [x for x in p[0] if x]
            # 收集分支：跳过后面的 402/403/404 序列
            seg_prefix = f"event{ev['id']}"
            entries = []
            for idx, text in enumerate(choices_raw):
                seg = f"{seg_prefix}_c{idx}"
                entries.append(f"{text}:{seg}")
            out.append("choose:" + "|".join(entries) + ";")
            # 扫描分支结构，把 402 内容作为独立段落（label 包裹）
            # 先找 402 边界
            branch_bodies = {}  # idx -> list of cmds
            j = i + 1
            while j < len(cmds):
                jc = cmds[j]
                if jc["code"] == 402:
                    idx = jc["parameters"][0]
                    branch_bodies[idx] = []
                    j += 1
                    while j < len(cmds) and cmds[j]["code"] not in (402, 403, 404, 0):
                        branch_bodies[idx].append(cmds[j])
                        j += 1
                    continue
                elif jc["code"] in (403, 404):
                    j += 1
                    continue
                elif jc["code"] == 0 and jc["indent"] <= i:
                    break
                else:
                    j += 1
            i = j
            # 输出分支段落
            for idx, text in enumerate(choices_raw):
                seg = f"{seg_prefix}_c{idx}"
                out.append(f"label:{seg};")
                body = branch_bodies.get(idx, [])
                sub = convert_sub(body, cg_map, opts, log, ev["id"])
                out.extend(sub)
            continue

        elif code == 111:  # 条件分支：true 分支由主循环顺序处理
            # 只记录条件类型，不做处理；主循环遇到 411 时跳过 else 分支体
            i += 1
            continue

        elif code == 411:  # else 分支：跳过 else 体直到同级 412
            else_indent = c["indent"]
            i += 1
            while i < len(cmds):
                ic = cmds[i]
                if ic["code"] == 412 and ic["indent"] <= else_indent:
                    break
                i += 1
            i += 1  # 跳过 412
            continue

        elif code in (412, 404, 403):  # endif/选项结束标记
            i += 1
            continue

        elif code == 118:  # label
            name = p[0]
            out.append(f"label:{name};")
            i += 1
            continue

        elif code == 119:  # jump
            target = p[0]
            if target in labels:
                out.append(f"jumpLabel:{target};")
            else:
                out.append(f"; label-jump to {target}")
            i += 1
            continue

        elif code == 117:  # 切公共事件
            target = p[0]
            if target == 10:
                out.append("; --- CG 表示終わり（清除图片） ---")
                out.append("changeBg:none;")
            else:
                out.append(f"; --- 公共事件 {target} ---")
            i += 1
            continue

        elif code in (121, 122):  # 开关/变量操作 → 忽略
            i += 1
            continue

        else:
            i += 1  # 其它命令跳过

    return out

def convert_sub(cmds, cg_map, opts, log, evid):
    """转换分支体（无 label/jump 处理的简化版）"""
    out = []
    pic_map = {}
    i = 0
    while i < len(cmds):
        c = cmds[i]
        code = c["code"]
        p = c["parameters"]
        if code == 101:
            speaker = p[4] if len(p) > 4 else ""
            i += 1
            texts = []
            while i < len(cmds) and cmds[i]["code"] == 401:
                texts.append(cmds[i]["parameters"][0])
                i += 1
            full = "\n".join(texts)
            out.append(f"{speaker}:{full};" if speaker else f":{full};")
        elif code == 231:
            pic_id = p[0]
            name = p[1]
            pic_map[pic_id] = name
            url, alt = cg_url(cg_map, name)
            if url:
                if not (out and out[-1].startswith("changeBg:")):
                    out.append(f"changeBg:{url};")
            i += 1
        elif code == 232:
            target = pic_map.get(p[0])
            if target:
                url, alt = cg_url(cg_map, target)
                if url:
                    if not (out and out[-1].startswith("changeBg:")):
                        out.append(f"changeBg:{url};")
            i += 1
        elif code == 224:
            if not opts.no_flash:
                rgba, frames = p[0], p[1]
                ms = frames * 1000 / 60
                hexc = f"#{rgba[0]:02x}{rgba[1]:02x}{rgba[2]:02x}"
                out.append(f"flash:{hexc} -duration={int(ms)};")
            i += 1
        elif code == 241:
            if opts.bgm:
                name = p[0].get("name", "") if p and isinstance(p[0], dict) else ""
                url = audio_url_for(name, opts)
                if url:
                    out.append(f"bgm:{url};")
            i += 1
        elif code == 250:
            if opts.se:
                name = p[0].get("name", "") if p and isinstance(p[0], dict) else ""
                url = audio_url_for(name, opts)
                if url:
                    out.append(f"playEffect:{url};")
            i += 1
        elif code == 117:
            if p[0] == 10:
                out.append("changeBg:none;")
            i += 1
        else:
            i += 1
    return out

# ── 主流程 ──
def main():
    opts = parse_args()
    common = json.load(open(CE_PATH, encoding="utf-8"))
    cg_map = load_cg_map(opts.cg_map)
    out_dir = Path(opts.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if opts.events:
        wanted = {int(x.strip()) for x in opts.events.split(",") if x.strip()}
    else:
        wanted = set(EVENT_MAP.keys())

    flag_note = []
    if opts.no_flash:
        flag_note.append("no-flash")
    if opts.bgm:
        flag_note.append("bgm")
    if opts.se:
        flag_note.append("se")

    for evid, out_name in sorted(EVENT_MAP.items()):
        if evid not in wanted:
            continue
        ev = next((e for e in common if e and e["id"] == evid), None)
        if not ev:
            print(f"SKIP event {evid}: not found", file=sys.stderr)
            continue
        log = open("/dev/null", "w")
        lines = convert_event(ev, cg_map, opts, log)
        log.close()

        # 文件头注释 + 内容
        content = [f"; {ev['name']} (RMMZ event {evid}) -> WebGAL", "; 由 rmmz2webgal.py 转换"]
        if flag_note:
            content.append(f"; 选项: {' '.join(flag_note)}")
        content += lines
        content.append("end;")
        outfile = out_dir / f"{out_name}.txt"
        outfile.write_text("\n".join(content) + "\n", encoding="utf-8")
        print(f"{out_name}.txt: {len(lines)} 行", file=sys.stderr)

if __name__ == "__main__":
    main()
