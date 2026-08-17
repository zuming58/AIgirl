"""Build a restrained, loopable LivePortrait idle motion template.

The template keeps the mouth frozen, synthesizes two natural bilateral blinks
from an official motion template, and preserves only a very small head nod.
"""

from __future__ import annotations

import argparse
import copy
import math
import pickle
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


EYE_KEYPOINTS = (11, 13, 15, 16, 18)


def smoothstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def seam_weight(index: int, frame_count: int, seam_frames: int) -> float:
    if seam_frames <= 0:
        return 1.0
    head = smoothstep(index / seam_frames)
    tail = smoothstep((frame_count - 1 - index) / seam_frames)
    return min(head, tail)


def damp_rotation(base: np.ndarray, current: np.ndarray, amount: float) -> np.ndarray:
    base_matrix = base.reshape(3, 3)
    current_matrix = current.reshape(3, 3)
    relative = base_matrix.T @ current_matrix
    rotation_vector = Rotation.from_matrix(relative).as_rotvec() * amount
    result = base_matrix @ Rotation.from_rotvec(rotation_vector).as_matrix()
    return result.astype(np.float32).reshape(1, 3, 3)


def gaussian_pulse(index: int, center: int, sigma: float) -> float:
    return math.exp(-0.5 * ((index - center) / sigma) ** 2)


def build_template(
    source_path: Path,
    output_path: Path,
    pose_strength: float,
    blink_strength: float,
    seam_frames: int,
) -> None:
    with source_path.open("rb") as handle:
        source = pickle.load(handle)

    motion = source["motion"]
    frame_count = len(motion)
    fps = int(source["output_fps"])
    if frame_count < 30:
        raise ValueError("The source template is too short for an idle loop.")

    rotation_key = "R_d" if "R_d" in motion[0] else "R"
    base = motion[0]
    base_expression = np.asarray(base["exp"], dtype=np.float32)
    base_translation = np.asarray(base["t"], dtype=np.float32)
    base_scale = np.asarray(base["scale"], dtype=np.float32)

    eye_ratios = np.asarray(
        source.get("c_d_eyes_lst", source.get("c_eyes_lst")), dtype=np.float32
    ).squeeze()
    if eye_ratios.ndim != 2 or eye_ratios.shape[1] != 2:
        raise ValueError("The source template does not contain bilateral eye ratios.")

    # Pick an actual bilateral blink from the source, avoiding the loop edges.
    candidate_start = max(seam_frames, 1)
    candidate_end = max(candidate_start + 1, frame_count - seam_frames)
    local_scores = eye_ratios[candidate_start:candidate_end].mean(axis=1)
    blink_frame = candidate_start + int(np.argmin(local_scores))
    blink_expression = np.asarray(motion[blink_frame]["exp"], dtype=np.float32)
    blink_delta = np.zeros_like(base_expression)
    blink_delta[:, EYE_KEYPOINTS, :] = (
        blink_expression[:, EYE_KEYPOINTS, :]
        - base_expression[:, EYE_KEYPOINTS, :]
    )

    # Two calm blinks in an approximately five-second loop.
    blink_centers = (round(frame_count * 0.34), round(frame_count * 0.74))
    blink_sigma = max(1.8, fps * 0.075)
    output_motion: list[dict[str, np.ndarray]] = []
    output_eye_ratios: list[np.ndarray] = []
    output_lip_ratios: list[np.ndarray] = []

    source_lips = source.get("c_d_lip_lst", source.get("c_lip_lst"))
    base_lip_ratio = np.asarray(source_lips[0], dtype=np.float32)
    base_eye_ratio = np.asarray(eye_ratios[0], dtype=np.float32)
    blink_eye_ratio = np.asarray(eye_ratios[blink_frame], dtype=np.float32)

    for index, frame in enumerate(motion):
        seam = seam_weight(index, frame_count, seam_frames)
        pulse = max(
            gaussian_pulse(index, center, blink_sigma) for center in blink_centers
        )
        pulse *= seam * blink_strength

        idle_frame = copy.deepcopy(frame)
        idle_frame[rotation_key] = damp_rotation(
            np.asarray(base[rotation_key], dtype=np.float32),
            np.asarray(frame[rotation_key], dtype=np.float32),
            pose_strength * seam,
        )
        # Keep the mouth, cheeks, jaw and gaze at the source-neutral state.
        idle_frame["exp"] = (base_expression + blink_delta * pulse).astype(np.float32)
        idle_frame["t"] = (
            base_translation
            + (np.asarray(frame["t"], dtype=np.float32) - base_translation)
            * pose_strength
            * 0.25
            * seam
        ).astype(np.float32)
        idle_frame["scale"] = (
            base_scale
            + (np.asarray(frame["scale"], dtype=np.float32) - base_scale)
            * pose_strength
            * 0.15
            * seam
        ).astype(np.float32)
        output_motion.append(idle_frame)
        output_eye_ratios.append(
            (base_eye_ratio + (blink_eye_ratio - base_eye_ratio) * pulse).astype(
                np.float32
            )
        )
        output_lip_ratios.append(base_lip_ratio.copy())

    output = {
        "n_frames": frame_count,
        "output_fps": fps,
        "motion": output_motion,
        "c_d_eyes_lst": output_eye_ratios,
        "c_d_lip_lst": output_lip_ratios,
        "xinyu_metadata": {
            "kind": "idle",
            "mouth_frozen": True,
            "blink_count": len(blink_centers),
            "pose_strength": pose_strength,
            "source_template": source_path.name,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(output, handle, protocol=pickle.HIGHEST_PROTOCOL)

    print(f"Created {output_path}")
    print(
        f"frames={frame_count} fps={fps} blink_source_frame={blink_frame} "
        f"pose_strength={pose_strength} blink_strength={blink_strength}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--pose-strength", type=float, default=0.12)
    parser.add_argument("--blink-strength", type=float, default=0.82)
    parser.add_argument("--seam-frames", type=int, default=12)
    args = parser.parse_args()
    build_template(
        args.source,
        args.output,
        args.pose_strength,
        args.blink_strength,
        args.seam_frames,
    )


if __name__ == "__main__":
    main()
