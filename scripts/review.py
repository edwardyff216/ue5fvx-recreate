"""Build a frontal Niagara review stage or render a new take in an isolated Unreal project."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from vfx import pack, compare


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["stage", "render"])
    p.add_argument("job", type=Path)
    p.add_argument("--editor", required=True, type=Path, help="UnrealEditor-Cmd executable")
    p.add_argument("--project", required=True, type=Path, help="isolated review .uproject")
    p.add_argument("--take", default="Take01", help="new take name for rendering")
    args = p.parse_args()
    job = args.job.resolve(strict=True)
    setup = json.loads((job / "stage.json").read_text(encoding="utf-8-sig"))
    root = setup["package"]
    if not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+", root):
        p.error("Set a fresh /Game/... package in stage.json")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", args.take):
        p.error("Use an alphanumeric take name beginning with a letter")
    base = [str(args.editor.resolve(strict=True)), str(args.project.resolve(strict=True))]
    env = dict(os.environ, UE_VFX_JOB=str(job), UE_VFX_TAKE=args.take)
    flags = ["-unattended", "-nosound", "-nop4",
             "-enableplugins=PythonScriptPlugin,SequencerScripting,Niagara,MovieRenderPipeline"]
    here = Path(__file__).resolve().parent

    def commandlet(script, log, marker):
        subprocess.run([*base, "-run=pythonscript", "-script=" + (here / script).as_posix(),
                        "-nullrhi", *flags, "-abslog=" + str(log)], env=env,
                       stdout=subprocess.DEVNULL, check=True)
        if marker not in log.read_text(encoding="utf-8-sig", errors="replace"):
            raise RuntimeError(f"Missing {marker} in {log}")

    if args.action == "stage":
        commandlet("ue_stage.py", job / "stage.log", "VFX_STAGE_SAVED")
        print(root + "/L_Review", root + "/LS_Review")
        return
    take = job / args.take
    take.mkdir(exist_ok=False)
    commandlet("ue_preset.py", take / "preset.log", "VFX_PRESET_SAVED")
    log = take / "render.log"
    preset = "MRQ_" + args.take
    subprocess.run([*base, root + "/L_Review", "-game", "-RenderOffscreen", *flags,
                    "-LevelSequence=" + root + "/LS_Review.LS_Review",
                    "-MoviePipelineConfig=" + root + "/" + preset + "." + preset,
                    "-abslog=" + str(log)], env=env, stdout=subprocess.DEVNULL, check=True)
    movie = take / "capture.mp4"
    pack(argparse.Namespace(job=job, folder=take / "png", out=movie))
    compare(argparse.Namespace(job=job, render=movie, out=take / "delivery"))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))

