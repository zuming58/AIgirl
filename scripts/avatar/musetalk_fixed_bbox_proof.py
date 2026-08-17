from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import cv2
import librosa
import numpy as np
import torch
from transformers import WhisperModel

from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.blending import get_image_blending, get_image_prepare_material
from musetalk.utils.face_parsing import FaceParsing
from musetalk.utils.utils import datagen, load_all_model


def parse_bbox(value: str) -> tuple[int, int, int, int]:
    parts = tuple(int(part.strip()) for part in value.split(","))
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be x1,y1,x2,y2")
    x1, y1, x2, y2 = parts
    if x2 <= x1 or y2 <= y1:
        raise argparse.ArgumentTypeError("bbox must have positive width and height")
    return parts


def read_frames(path: Path, limit: int) -> tuple[list[np.ndarray], float]:
    capture = cv2.VideoCapture(str(path))
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
    frames: list[np.ndarray] = []
    while len(frames) < limit:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(frame)
    capture.release()
    if not frames:
        raise RuntimeError(f"No frames could be read from {path}")
    while len(frames) < limit:
        frames.extend(frames[: min(len(frames), limit - len(frames))])
    return frames[:limit], source_fps


def start_encoder(output: Path, width: int, height: int, fps: int) -> subprocess.Popen:
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "12",
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def mouth_only_blend(
    frame: np.ndarray,
    generated_face: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    width = x2 - x1
    height = y2 - y1
    mask = np.zeros((height, width), dtype=np.uint8)
    center = (width // 2, int(height * 0.72))
    axes = (int(width * 0.27), int(height * 0.15))
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)
    blur = max(21, int(width * 0.07) | 1)
    alpha = cv2.GaussianBlur(mask, (blur, blur), 0).astype(np.float32) / 255.0
    alpha = alpha[:, :, None]
    result = frame.copy()
    original = result[y1:y2, x1:x2].astype(np.float32)
    generated = generated_face.astype(np.float32)
    result[y1:y2, x1:x2] = np.clip(
        generated * alpha + original * (1.0 - alpha), 0, 255
    ).astype(np.uint8)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MuseTalk 1.5 quality/speed proof using a stable fixed face ROI."
    )
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bbox", type=parse_bbox, required=True)
    parser.add_argument("--musetalk-root", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--extra-margin", type=int, default=10)
    parser.add_argument(
        "--blend-mode", choices=("mouth", "jaw"), default="mouth"
    )
    args = parser.parse_args()

    root = args.musetalk_root.resolve()
    models = root / "models"
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_video = output.with_name(f"{output.stem}.silent.mp4")

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    if device.type != "cuda":
        raise RuntimeError("This gate intentionally requires CUDA real-time inference.")

    audio_seconds = librosa.get_duration(path=str(args.audio))
    frame_count = max(1, int(audio_seconds * args.fps))
    frames, source_fps = read_frames(args.video, frame_count)
    height, width = frames[0].shape[:2]
    x1, y1, x2, y2 = args.bbox
    y2 = min(height, y2 + args.extra_margin)
    bbox = (x1, y1, x2, y2)

    print(
        f"gate-input frames={frame_count} source_fps={source_fps:.3f} "
        f"output={width}x{height}@{args.fps} bbox={bbox}"
    )

    load_started = time.perf_counter()
    vae, unet, pe = load_all_model(
        unet_model_path=str(models / "musetalkV15" / "unet.pth"),
        vae_type="sd-vae",
        unet_config=str(models / "musetalkV15" / "musetalk.json"),
        device=device,
    )
    vae.model_path = str(models / "sd-vae")
    # load_all_model resolves the VAE relative to cwd. The gate is launched from
    # the MuseTalk root, so this assignment documents the frozen model source.
    timesteps = torch.tensor([0], device=device)
    pe = pe.half().to(device).eval()
    vae.vae = vae.vae.half().to(device).eval()
    unet.model = unet.model.half().to(device).eval()

    audio_processor = AudioProcessor(feature_extractor_path=str(models / "whisper"))
    whisper = WhisperModel.from_pretrained(str(models / "whisper"))
    whisper = whisper.to(device=device, dtype=unet.model.dtype).eval()
    whisper.requires_grad_(False)
    parser_model = None
    if args.blend_mode == "jaw":
        parser_model = FaceParsing(left_cheek_width=90, right_cheek_width=90)
    print(
        f"models-loaded seconds={time.perf_counter() - load_started:.3f} "
        f"vram_gb={torch.cuda.memory_allocated() / 1024**3:.3f}"
    )

    prep_started = time.perf_counter()
    latents: list[torch.Tensor] = []
    for frame in frames:
        crop = frame[y1:y2, x1:x2]
        crop = cv2.resize(crop, (256, 256), interpolation=cv2.INTER_LANCZOS4)
        latents.append(vae.get_latents_for_unet(crop))
    mask = None
    mask_crop_box = None
    if args.blend_mode == "jaw":
        mask, mask_crop_box = get_image_prepare_material(
            frames[0], bbox, fp=parser_model, mode="jaw"
        )
    print(
        f"avatar-prepared seconds={time.perf_counter() - prep_started:.3f} "
        f"vram_gb={torch.cuda.memory_allocated() / 1024**3:.3f}"
    )

    audio_started = time.perf_counter()
    input_features, librosa_length = audio_processor.get_audio_feature(
        str(args.audio), weight_dtype=unet.model.dtype
    )
    chunks = audio_processor.get_whisper_chunk(
        input_features,
        device,
        unet.model.dtype,
        whisper,
        librosa_length,
        fps=args.fps,
        audio_padding_length_left=2,
        audio_padding_length_right=2,
    )
    print(
        f"audio-prepared frames={len(chunks)} "
        f"seconds={time.perf_counter() - audio_started:.3f}"
    )

    frames = frames[: len(chunks)]
    latents = latents[: len(chunks)]
    encoder = start_encoder(temp_video, width, height, args.fps)
    if encoder.stdin is None:
        raise RuntimeError("ffmpeg encoder stdin was not created")

    inference_started = time.perf_counter()
    core_seconds = 0.0
    frame_index = 0
    with torch.inference_mode():
        for whisper_batch, latent_batch in datagen(
            chunks, latents, batch_size=args.batch_size, device=str(device)
        ):
            torch.cuda.synchronize()
            core_started = time.perf_counter()
            audio_features = pe(whisper_batch.to(device))
            latent_batch = latent_batch.to(device=device, dtype=unet.model.dtype)
            prediction = unet.model(
                latent_batch,
                timesteps,
                encoder_hidden_states=audio_features,
            ).sample
            prediction = prediction.to(device=device, dtype=vae.vae.dtype)
            decoded = vae.decode_latents(prediction)
            torch.cuda.synchronize()
            core_seconds += time.perf_counter() - core_started
            for mouth_frame in decoded:
                original = frames[frame_index]
                resized = cv2.resize(
                    mouth_frame.astype(np.uint8),
                    (x2 - x1, y2 - y1),
                    interpolation=cv2.INTER_LANCZOS4,
                )
                if args.blend_mode == "jaw":
                    combined = get_image_blending(
                        original, resized, bbox, mask, mask_crop_box
                    )
                else:
                    combined = mouth_only_blend(original, resized, bbox)
                encoder.stdin.write(combined.tobytes())
                frame_index += 1

    encoder.stdin.close()
    return_code = encoder.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg video encoder exited with {return_code}")
    inference_seconds = time.perf_counter() - inference_started

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(temp_video),
            "-i",
            str(args.audio),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ],
        check=True,
    )
    temp_video.unlink(missing_ok=True)
    print(
        f"gate-result frames={frame_index} seconds={inference_seconds:.3f} "
        f"end_to_end_fps={frame_index / inference_seconds:.3f} "
        f"core_seconds={core_seconds:.3f} core_fps={frame_index / core_seconds:.3f} "
        f"peak_vram_gb={torch.cuda.max_memory_allocated() / 1024**3:.3f} "
        f"output={output}"
    )


if __name__ == "__main__":
    main()
