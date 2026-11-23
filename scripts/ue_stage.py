"""Run in an isolated UE editor commandlet, with UE_VFX_JOB pointing to a prepared job."""
import json
import math
import os
import re
from fractions import Fraction
from pathlib import Path

import unreal as u


def build(job_dir):
    read = lambda name: json.loads((job_dir / name).read_text(encoding="utf-8-sig"))
    job, setup = read("job.json"), read("stage.json")
    root = setup["package"]
    if not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+", root):
        raise ValueError("Set package to a fresh /Game/... review folder")
    map_name, sequence_name = root + "/L_Review", root + "/LS_Review"
    assets = u.EditorAssetLibrary
    if any(assets.does_asset_exist(p) for p in (map_name, sequence_name)):
        raise ValueError("Review already exists. Choose a fresh package for this revision.")
    system = u.load_asset(setup["system"])
    if not isinstance(system, u.NiagaraSystem):
        raise ValueError("Set system to an existing NiagaraSystem asset")
    w, h = job["size"]
    frames, rate = job["frames"], Fraction(job["fps"])
    trigger, width_cm = setup["trigger_frame"], float(setup["width_cm"])
    if not (0 <= trigger < frames and isinstance(trigger, int) and math.isfinite(width_cm) and width_cm > 0):
        raise ValueError("Invalid trigger_frame or width_cm")
    keys = setup["position_keys"]
    previous = -1
    for frame, x, y in keys:
        if not (isinstance(frame, int) and previous < frame < frames and math.isfinite(x) and math.isfinite(y)):
            raise ValueError("Keys must be sorted unique [frame, cropped_x_px, cropped_y_px] triples")
        previous = frame

    def position(x, y):
        return u.Vector((w * 0.5 - x) * width_cm / w, 0, (h * 0.5 - y) * width_cm / w)

    eas = u.get_editor_subsystem(u.EditorActorSubsystem)
    world = u.EditorLoadingAndSavingUtils.new_blank_map(False)
    camera = eas.spawn_actor_from_class(u.CameraActor, u.Vector(0, -max(800, width_cm * 2), 0),
                                        u.Rotator(0, 0, 90))
    cc = camera.get_component_by_class(u.CameraComponent)
    cc.set_editor_property("projection_mode", u.CameraProjectionMode.ORTHOGRAPHIC)
    cc.set_editor_property("ortho_width", width_cm)
    cc.set_editor_property("aspect_ratio", w / h)
    camera.set_editor_property("auto_activate_for_player", u.AutoReceiveInput.PLAYER0)
    origin = position(*keys[0][1:]) if keys else u.Vector()
    actor = eas.spawn_actor_from_class(u.NiagaraActor, origin)
    component = actor.get_component_by_class(u.NiagaraComponent)
    component.set_editor_property("auto_activate", False)
    component.set_asset(system)
    if not u.EditorLoadingAndSavingUtils.save_map(world, map_name):
        raise RuntimeError("Could not save review world")
    seq = u.AssetToolsHelpers.get_asset_tools().create_asset("LS_Review", root, u.LevelSequence,
                                                             u.LevelSequenceFactoryNew())
    seq.set_display_rate(u.FrameRate(rate.numerator, rate.denominator))
    seq.set_playback_start(0)
    seq.set_playback_end(frames)
    actor_binding = seq.add_possessable(actor)
    if keys:
        motion = actor_binding.add_track(u.MovieScene3DTransformTrack).add_section()
        motion.set_range(0, frames)
        channels = motion.get_all_channels()
        for frame, x, y in keys:
            point = position(x, y)
            for channel, value in zip(channels, (point.x, point.y, point.z)):
                channel.add_key(u.FrameNumber(frame), value, interpolation=u.MovieSceneKeyInterpolation.LINEAR)
    fx_binding = seq.add_possessable(component)
    fx_binding.set_parent(actor_binding)
    life = fx_binding.add_track(u.MovieSceneNiagaraSystemTrack).add_section()
    life.set_range(trigger, frames)
    life.set_section_evaluate_behavior(u.NiagaraSystemSpawnSectionEvaluateBehavior.NONE)
    camera_binding = seq.add_possessable(camera)
    cut = seq.add_track(u.MovieSceneCameraCutTrack).add_section()
    cut.set_range(0, frames)
    cut.set_camera_binding_id(seq.get_binding_id(camera_binding))
    sequence_actor = eas.spawn_actor_from_class(u.LevelSequenceActor, u.Vector())
    sequence_actor.set_sequence(seq)
    playback = sequence_actor.get_editor_property("playback_settings")
    playback.set_editor_property("auto_play", True)
    sequence_actor.set_editor_property("playback_settings", playback)
    if not assets.save_loaded_asset(seq, False) or not u.EditorLoadingAndSavingUtils.save_map(world, map_name):
        raise RuntimeError("Could not persist review sequence and map")
    print(f"VFX_STAGE_SAVED {map_name} {sequence_name} {frames} @ {rate}")


build(Path(os.environ["UE_VFX_JOB"]))

