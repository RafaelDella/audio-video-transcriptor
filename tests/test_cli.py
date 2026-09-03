from pathlib import Path

from transcreve.cli import _format_for, _output_for, build_parser


def test_output_defaults_to_source_directory():
    args = build_parser().parse_args(["recording.m4a"])
    assert _output_for(Path("recording.m4a"), args) == Path("recording.txt")


def test_format_is_inferred_from_explicit_output():
    args = build_parser().parse_args(["recording.m4a", "-o", "captions.srt"])
    output = _output_for(Path("recording.m4a"), args)
    assert _format_for(output, args.format) == "srt"


def test_portuguese_aliases_are_supported():
    args = build_parser().parse_args(
        ["audio.m4a", "--saida", "texto.txt", "--modelo", "small", "--idioma", "pt"]
    )
    assert args.output == Path("texto.txt")
    assert args.model == "small"
    assert args.language == "pt"
