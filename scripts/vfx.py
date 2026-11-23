"""Prepare a reference and compare independent UE renders on its frame clock."""
import argparse
import json
import math
import subprocess
import sys
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw


def ffmpeg(*args, capture=False):
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                           "-n", *map(str, args)], check=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def inspect(path):
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,sample_aspect_ratio:"
        "stream_side_data=rotation:frame=best_effort_timestamp_time", "-of", "json", str(path)])
    data = json.loads(raw)
    stream = data["streams"][0]
    pts = [float(f["best_effort_timestamp_time"]) for f in data["frames"]]
    if not pts or any(b <= a for a, b in zip(pts, pts[1:])):
        raise ValueError("Missing frames or non-increasing timestamps")
    rate_text = stream["avg_frame_rate"]
    rate = Fraction(rate_text if rate_text != "0/0" else stream["r_frame_rate"])
    if rate <= 0:
        raise ValueError("Missing nominal frame rate")
    constant = all(abs((p - pts[0]) - i / float(rate)) <= 0.0011 for i, p in enumerate(pts))
    return stream, pts, rate, constant


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sheet(video, count, fps, dest):
    frames = sorted({round(i * (count - 1) / 11) for i in range(12)})
    expr = "+".join(f"eq(n\\,{i})" for i in frames)
    with TemporaryDirectory() as temp:
        ffmpeg("-i", video, "-vf", f"select={expr},scale=240:144:force_original_aspect_ratio=decrease,"
               "pad=240:144:(ow-iw)/2:(oh-ih)/2", "-fps_mode", "passthrough",
               "-start_number", 0, Path(temp) / "%03d.png")
        canvas = Image.new("RGB", (4 * 240, math.ceil(len(frames) / 4) * 166), "#191b20")
        draw = ImageDraw.Draw(canvas)
        for k, frame in enumerate(frames):
            x, y = (k % 4) * 240, (k // 4) * 166
            with Image.open(Path(temp) / f"{k:03d}.png") as tile:
                canvas.paste(tile, (x, y))
            draw.text((x + 5, y + 146), f"F{frame}    {frame / float(fps):.3f} s", fill="white")
        canvas.save(dest)


def prepare(args):
    ref = args.source.resolve(strict=True)
    stream, pts, rate, constant = inspect(ref)
    if not constant and not args.fps:
        raise ValueError("Variable frame timing. Choose the UE display rate with --fps, e.g. 30 or 24000/1001.")
    fps = Fraction(args.fps) if args.fps else rate
    if fps <= 0 or fps > 1000:
        raise ValueError("Invalid target fps")
    width, height = stream["width"], stream["height"]
    rotation = next((s["rotation"] for s in stream.get("side_data_list", []) if "rotation" in s), 0)
    if rotation % 180:
        width, height = height, width
    if stream.get("sample_aspect_ratio", "1:1") not in ("1:1", "N/A", "0:1"):
        raise ValueError("Convert anamorphic footage to square pixels before measuring coordinates.")
    x, y, w, h = args.crop or (0, 0, width, height)
    if min(x, y) < 0 or min(w, h) < 1 or x + w > width or y + h > height:
        raise ValueError(f"Crop outside {width}x{height}; expected X Y WIDTH HEIGHT")
    start = args.start
    end = args.end if args.end is not None else len(pts)
    if not 0 <= start < end <= len(pts):
        raise ValueError(f"Frame range must lie in [0, {len(pts)})")
    dest = args.job
    dest.mkdir(parents=True, exist_ok=False)
    filters = [f"trim=start_frame={start}:end_frame={end}", "setpts=PTS-STARTPTS",
               f"crop={w}:{h}:{x}:{y}:exact=1", "setsar=1"]
    if not constant or fps != rate:
        filters.append(f"fps={fps}")
    video = dest / "reference.mkv"
    ffmpeg("-i", ref, "-map", "0:v:0", "-vf", ",".join(filters), "-an", "-c:v", "ffv1",
           "-fps_mode", "cfr", "-r", str(fps), video)
    _, ref_pts, ref_rate, uniform = inspect(video)
    count = len(ref_pts)
    if not uniform or ref_rate != fps or (constant and fps == rate and count != end-start):
        raise ValueError("Prepared reference did not preserve the target clock")
    sheet(video, count, fps, dest / "keyframes.jpg")
    write_json(dest / "job.json", dict(source=str(ref), source_frames=len(pts), source_rate=str(rate),
               source_cfr=constant, source_range=[start, end], source_start_seconds=pts[start],
               crop_xywh=[x, y, w, h], fps=str(fps), frames=count, size=[w, h]))
    write_json(dest / "stage.json", dict(system="", package="", width_cm=500,
               trigger_frame=0, position_keys=[]))
    (dest / "match.md").write_text(
        f"# 特效复刻记录\n\n参考文件 `{ref.name}`，源帧区间 [{start}, {end})。"
        f"裁切 XYWH 为 {x}, {y}, {w}, {h}。评审时间轴为 {count} 帧，{fps} fps。\n\n"
        "## 对照记录\n\n| 项目 | 参考 | UE 实拍 | 差异与下一次调整 |\n"
        "| --- | --- | --- | --- |\n"
        "| 触发帧、首个可见帧 | | | |\n| 峰值帧、主轮廓 | | | |\n"
        "| 停止发射帧、最后可见帧 | | | |\n| 位置、宽度、速度、颜色 | | | |\n\n"
        "## 交付\n\n- UE 版本与工程路径\n- 系统、材质、关卡与序列\n"
        "- 相机、曝光、触发与复位方法\n- 可调参数及单位\n- 最终 take、残余差异与推测\n",
        encoding="utf-8")
    print(f"{count} frames @ {fps} fps | {w}x{h} | {dest.resolve()}")


H264 = ["-c:v", "libx264", "-crf", "17", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart"]


def verify_clock(path, job):
    stream, pts, fps, constant = inspect(path)
    if not constant or len(pts) != job["frames"] or fps != Fraction(job["fps"]):
        raise ValueError(f"{path.name}: {len(pts)} frames @ {fps}, CFR={constant}; "
                         f"expected {job['frames']} @ {job['fps']}. Check capture range and clock.")
    return stream


def pack(args):
    """Pack one fresh MRQ PNG sequence, rejecting gaps and unexpected frame counts."""
    job = json.loads((args.job / "job.json").read_text(encoding="utf-8"))
    files = {}
    for path in args.folder.glob("*.png"):
        if not path.stem.isascii() or not path.stem.isdigit():
            raise ValueError("Use {frame_number_rel} as the MRQ file name")
        number = int(path.stem)
        if number in files:
            raise ValueError(f"Duplicate frame {number}")
        files[number] = path
    if sorted(files) != list(range(job["frames"])):
        raise ValueError(f"Expected frames 0..{job['frames'] - 1}, found {len(files)} PNG files")
    first = files[0]
    pattern = f"%0{len(first.stem)}d.png"
    if any(path.name != pattern % frame for frame, path in files.items()):
        raise ValueError("Inconsistent number padding")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-framerate", job["fps"], "-start_number", 0, "-i", args.folder / pattern,
           "-frames:v", job["frames"], "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
           *H264, args.out)
    verify_clock(args.out, job)
    print(args.out.resolve())


def compare(args):
    job = json.loads((args.job / "job.json").read_text(encoding="utf-8"))
    ref = args.job / "reference.mkv"
    verify_clock(ref, job)
    take = args.render.resolve(strict=True)
    if take.samefile(ref) or (Path(job["source"]).exists() and take.samefile(job["source"])):
        raise ValueError("Supply the independent Unreal render")
    ue = verify_clock(take, job)
    width, height = job["size"]
    if abs((ue["width"] / ue["height"]) / (width / height) - 1) > 0.01:
        raise ValueError("UE camera/output aspect differs by more than 1%; match the framing")
    w = max(2, width + width % 2)
    h = max(2, height + height % 2)
    dest = args.out
    dest.mkdir(parents=True, exist_ok=False)
    clean = dest / "UE.mp4"
    ffmpeg("-i", take, "-map", "0:v:0", "-an", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1",
           *H264, clean)
    header = Image.new("RGB", (w * 2, 26), "#191b20")
    draw = ImageDraw.Draw(header)
    for x, label in [(8, "REFERENCE"), (w + 8, "UNREAL ENGINE")]:
        draw.text((x, 6), label, fill="white")
    with TemporaryDirectory() as temp:
        bar = Path(temp) / "header.png"
        header.save(bar)
        # Verified CFR inputs may still have different codec time bases (e.g. 1/1000
        # vs. 1/15360). Assign the same exact timestamp to both copies of frame N.
        rate = Fraction(job["fps"])
        common = (f"scale={w}:{h},setsar=1,settb=expr={rate.denominator}/{rate.numerator},"
                  "setpts=N")
        graph = (f"[0:v]{common}[a];[1:v]{common}[b];[a][b]hstack,pad=iw:ih+26:0:26[body];"
                 "[body][2:v]overlay=eof_action=repeat[out]")
        ffmpeg("-i", ref, "-i", take, "-i", bar, "-filter_complex", graph, "-map", "[out]",
               "-an", "-frames:v", job["frames"], "-r", job["fps"], *H264, dest / "comparison.mp4")
    for path in [clean, dest / "comparison.mp4"]:
        verify_clock(path, job)
    sheet(dest / "comparison.mp4", job["frames"], Fraction(job["fps"]), dest / "comparison.jpg")
    write_json(dest / "timing.json", dict(render=str(take), frames=job["frames"], fps=job["fps"],
               reference_left=True, timing_verified=True))
    print(dest.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    prep = subs.add_parser("prepare", help="measure a new reference and create a fresh job")
    prep.add_argument("source", type=Path)
    prep.add_argument("job", type=Path)
    prep.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "W", "H"))
    prep.add_argument("--start", type=int, default=0, help="first source frame, zero based")
    prep.add_argument("--end", type=int, help="exclusive source frame")
    prep.add_argument("--fps", help="target rational rate, required for VFR input")
    png = subs.add_parser("pack", help="encode a verified MRQ PNG sequence as a clean MP4")
    png.add_argument("job", type=Path)
    png.add_argument("folder", type=Path)
    png.add_argument("out", type=Path)
    comp = subs.add_parser("compare", help="verify an independent render and deliver a side-by-side")
    comp.add_argument("job", type=Path)
    comp.add_argument("render", type=Path)
    comp.add_argument("out", type=Path, help="new take directory")
    args = parser.parse_args()
    {"prepare": prepare, "pack": pack, "compare": compare}[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, KeyError, IndexError) as error:
        sys.exit(str(error))

