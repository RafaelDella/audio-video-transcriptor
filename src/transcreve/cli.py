from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .config import PROFILES, profile
from .engine import Transcriber

FORMATS = ("txt", "srt", "vtt", "json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcreve",
        description="Transcricao local de audio com uso controlado de memoria.",
    )
    parser.add_argument("audio", nargs="+", type=Path, help="um ou mais arquivos de audio")
    parser.add_argument(
        "-o", "--output", "--saida", type=Path, help="saida (somente para um audio)"
    )
    parser.add_argument("--output-dir", "--diretorio-saida", type=Path)
    parser.add_argument("--format", "--formato", choices=FORMATS)
    parser.add_argument("--profile", "--perfil", choices=PROFILES, default="equilibrado")
    parser.add_argument("--model", "--modelo", help="modelo Whisper; substitui o perfil")
    parser.add_argument("--language", "--idioma", default="pt", help="codigo do idioma ou 'auto'")
    parser.add_argument("--device", "--dispositivo", choices=("cpu", "cuda", "auto"))
    parser.add_argument("--compute-type", help="ex.: int8, float16, auto")
    parser.add_argument("--chunk-minutes", "--minutos-por-bloco", type=int)
    parser.add_argument("--overlap-seconds", "--sobreposicao", type=float)
    parser.add_argument("--beam-size", type=int)
    parser.add_argument("--threads", "--processadores", type=int)
    parser.add_argument(
        "--vocabulary", "--vocabulario", default="", help="nomes e termos separados por virgula"
    )
    parser.add_argument("--no-vad", action="store_true", help="desativa deteccao de voz")
    parser.add_argument("--vad-threshold", type=float)
    parser.add_argument("--timestamps", action="store_true", help="timestamps no formato TXT")
    parser.add_argument("--no-resume", action="store_true", help="ignora checkpoint existente")
    parser.add_argument("--keep-checkpoint", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def _output_for(source: Path, args: argparse.Namespace) -> Path:
    if args.output:
        return args.output
    directory = args.output_dir or source.parent
    return directory / f"{source.stem}.{args.format or 'txt'}"


def _format_for(output: Path, requested: str | None) -> str:
    if requested:
        return requested
    suffix = output.suffix.lower().lstrip(".")
    return suffix if suffix in FORMATS else "txt"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output and len(args.audio) != 1:
        print("erro: --output aceita somente um arquivo de entrada", file=sys.stderr)
        return 2
    missing = [str(path) for path in args.audio if not path.is_file()]
    if missing:
        print(f"erro: arquivo(s) nao encontrado(s): {', '.join(missing)}", file=sys.stderr)
        return 2

    overrides = {
        "language": None if args.language == "auto" else args.language,
        "vocabulary": args.vocabulary,
    }
    optional = {
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "chunk_minutes": args.chunk_minutes,
        "overlap_seconds": args.overlap_seconds,
        "beam_size": args.beam_size,
        "threads": args.threads,
        "vad_threshold": args.vad_threshold,
    }
    overrides.update({key: value for key, value in optional.items() if value is not None})
    if args.no_vad:
        overrides["vad"] = False
    try:
        config = profile(args.profile, **overrides)
    except ValueError as error:
        parser.error(str(error))
    os.environ.setdefault("OMP_NUM_THREADS", str(config.threads))
    os.environ.setdefault("OPENBLAS_NUM_THREADS", str(config.threads))
    os.environ.setdefault("MKL_NUM_THREADS", str(config.threads))
    os.environ.setdefault("MALLOC_ARENA_MAX", "2")
    transcriber = Transcriber(config)

    def progress(event) -> None:
        if event.phase == "started":
            action = "Retomando" if event.skipped else "Transcrevendo"
            total = f"/{event.total_chunks} (estimado)" if event.total_chunks else ""
            print(
                f"{action} bloco {event.chunk_index + 1}{total}: "
                f"{event.start_seconds:.1f}s–{event.end_seconds:.1f}s",
                file=sys.stderr,
            )

    try:
        for source in args.audio:
            output = _output_for(source, args)
            format_name = _format_for(output, args.format)
            print(f"Entrada: {source}\nSaida: {output}\nModelo: {config.model}", file=sys.stderr)
            segments = transcriber.transcribe(
                source,
                output,
                format_name,
                args.timestamps,
                resume=not args.no_resume,
                keep_checkpoint=args.keep_checkpoint,
                progress=progress,
            )
            print(f"Concluido: {output} ({len(segments)} trechos)", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nInterrompido. Execute novamente para retomar do checkpoint.", file=sys.stderr)
        return 130
    except Exception as error:  # noqa: BLE001 - fronteira da aplicacao CLI
        print(f"erro: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
