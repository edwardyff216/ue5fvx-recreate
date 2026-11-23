"""Create an MRQ preset for one take. Invoked by review.py inside Unreal."""
import json
import os
from pathlib import Path

import unreal as u

job_dir = Path(os.environ["UE_VFX_JOB"])
take = os.environ["UE_VFX_TAKE"]
job = json.loads((job_dir / "job.json").read_text(encoding="utf-8-sig"))
root = json.loads((job_dir / "stage.json").read_text(encoding="utf-8-sig"))["package"]
name = "MRQ_" + take
assets = u.EditorAssetLibrary
if not assets.does_asset_exist(root + "/LS_Review") or assets.does_asset_exist(root + "/" + name):
    raise ValueError("Build the review first and choose an unused take name.")
preset = u.AssetToolsHelpers.get_asset_tools().create_asset(
    name, root, u.MoviePipelinePrimaryConfig, u.MoviePipelinePrimaryConfigFactory())
output = preset.find_or_add_setting_by_class(u.MoviePipelineOutputSetting)
output.set_editor_property("output_directory", u.DirectoryPath(str(job_dir / take / "png")))
output.set_editor_property("file_name_format", "{frame_number_rel}")
output.set_editor_property("output_resolution", u.IntPoint(*job["size"]))
output.set_editor_property("override_existing_output", False)
preset.find_or_add_setting_by_class(u.MoviePipelineDeferredPassBase)
preset.find_or_add_setting_by_class(u.MoviePipelineImageSequenceOutput_PNG)
aa = preset.find_or_add_setting_by_class(u.MoviePipelineAntiAliasingSetting)
aa.set_editor_property("temporal_sample_count", 1)
aa.set_editor_property("spatial_sample_count", 1)
aa.set_editor_property("engine_warm_up_count", 0)
aa.set_editor_property("render_warm_up_count", 0)
aa.set_editor_property("use_camera_cut_for_warm_up", False)
if not assets.save_loaded_asset(preset, False):
    raise RuntimeError("MRQ preset did not save")
print("VFX_PRESET_SAVED", root + "/" + name)

