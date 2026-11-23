# ue5fvx复刻 · ue-vfx-recreate

一个用于 **在 Unreal Engine 5 中按参考视频/截图复刻可编辑游戏特效** 的 Agent Skill。
流程：参考素材 → 可测量描述 → Niagara/材质实现 → 独立 UE 评审关卡 → MRQ 实拍 → 与参考逐帧对照 → 交付。

## 目录

| 路径 | 作用 |
| --- | --- |
| `SKILL.md` | 技能入口：触发条件与 6 步工作流 |
| `references/effect-families.md` | 特效分类表（拖尾、冲击环、持续场、光束、刀光、屏幕特效）及 `match.md` 记录模板 |
| `references/runbook.md` | 脚本用法与 UE 出片操作手册 |
| `scripts/vfx.py` | 系统 Python：`prepare` 截取参考并建任务目录，`pack` 校验 PNG 序列并编码，`compare` 生成左参考右 UE 的对照片 |
| `scripts/review.py` | 调用 UnrealEditor-Cmd：`stage` 搭建预览关卡，`render` 新建 take 并离屏渲染 |
| `scripts/ue_stage.py` | UE 内 Python：生成正交相机、Niagara Actor、Level Sequence 与触发轨 |
| `scripts/ue_preset.py` | UE 内 Python：为单个 take 创建 MRQ PNG 预设 |
| `agents/openai.yaml` | 显示名与默认提示词 |

## 依赖

Python 3.10+、Pillow、FFmpeg/ffprobe；UE5（启用 PythonScriptPlugin、SequencerScripting、Niagara、MovieRenderPipeline）。

## 快速开始

```powershell
python scripts/vfx.py prepare ref.mp4 D:/VfxReview/MyFX/v01
# 编辑 v01/stage.json 指向你的 Niagara System
python scripts/review.py stage  D:/VfxReview/MyFX/v01 --editor <UnrealEditor-Cmd.exe> --project <Review.uproject>
python scripts/review.py render D:/VfxReview/MyFX/v01 --editor <UnrealEditor-Cmd.exe> --project <Review.uproject> --take Take01
```

详见 `references/runbook.md`。
