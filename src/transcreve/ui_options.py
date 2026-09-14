"""Labels and validation shared by the desktop interface."""

PROFILE_HELP = {
    "economico": "Modelo base. Usa menos memória e tende a terminar mais rápido; pode perder detalhes.",
    "equilibrado": "Modelo small. Ponto de partida para a maioria dos arquivos.",
    "qualidade": "Modelo medium. Pode reconhecer melhor falas difíceis, com mais tempo e memória.",
    "maximo": "Modelo large-v3. Maior demanda de memória e processamento; indicado para GPU.",
}
PROFILE_LABELS = {
    "economico": "Econômico",
    "equilibrado": "Equilibrado",
    "qualidade": "Qualidade",
    "maximo": "Máximo",
}
MODEL_DETAILS = {
    "economico": {"parameters_millions": 74,
                  "description": "Mais leve para CPU e transcrições rápidas. Pode perder palavras em áudio difícil."},
    "equilibrado": {"parameters_millions": 244,
                   "description": "Boa escolha geral entre clareza, memória e tempo de processamento."},
    "qualidade": {"parameters_millions": 769,
                  "description": "Mais capacidade para falas difíceis, com maior uso de memória e tempo."},
    "maximo": {"parameters_millions": 1550,
                "description": "Maior modelo disponível aqui. É pesado em CPU e se beneficia de GPU."},
}
FORMAT_HELP = {
    "txt": "Texto simples, sem marcações de tempo.",
    "srt": "Legendas com tempo, para vídeos e editores.",
    "vtt": "Legendas WebVTT para reprodução na web.",
    "json": "Trechos com tempos e texto em formato estruturado.",
}


def valid_output_stem(name: str) -> bool:
    """Keep output names as safe single-file stems on Windows and other platforms."""
    if not name or name != name.strip(" ."):
        return False
    if any(character in name for character in '<>:"/\\|?*'):
        return False
    if any(ord(character) < 32 for character in name):
        return False
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    return name.split(".")[0].upper() not in reserved
