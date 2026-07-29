import asyncio
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel

from rda.config import obtenir_parametres


@dataclass(frozen=True)
class ResultatTranscription:
    transcription: str
    confiance: float


class ServiceTranscription:
    """Transcription locale voix vers texte avec faster-whisper."""

    def __init__(self) -> None:
        self._modele: WhisperModel | None = None

    def _charger_modele(self) -> WhisperModel:
        if self._modele is None:
            parametres = obtenir_parametres()
            parametres.stt_modeles_dir.mkdir(parents=True, exist_ok=True)
            self._modele = WhisperModel(
                parametres.stt_modele,
                device="cpu",
                compute_type="int8",
                download_root=str(parametres.stt_modeles_dir),
            )
        return self._modele

    async def transcrire(self, audio: bytes, suffixe: str = ".m4a") -> ResultatTranscription:
        with tempfile.TemporaryDirectory() as dossier:
            entree = Path(dossier) / f"question-source{suffixe}"
            sortie = Path(dossier) / "question-convertie.wav"
            entree.write_bytes(audio)
            try:
                return await asyncio.to_thread(self._transcrire_audio, entree)
            except Exception:
                await asyncio.to_thread(self._convertir_audio, entree, sortie)
                return await asyncio.to_thread(self._transcrire_audio, sortie)

    def _convertir_audio(self, entree: Path, sortie: Path) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(entree),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(sortie),
            ],
            check=True,
            timeout=30,
        )

    def _transcrire_audio(self, chemin: Path) -> ResultatTranscription:
        modele = self._charger_modele()
        segments, info = modele.transcribe(
            str(chemin),
            language="fr",
            beam_size=10,
            best_of=5,
            temperature=0.0,
            vad_filter=False,
            initial_prompt="Transcription courte en français.",
        )
        textes: list[str] = []
        confiances: list[float] = []
        for segment in segments:
            texte = segment.text.strip()
            if texte:
                textes.append(texte)
            if segment.avg_logprob is not None:
                confiances.append(max(0.0, min(1.0, 1.0 + float(segment.avg_logprob))))

        transcription = " ".join(textes).strip()
        confiance = sum(confiances) / len(confiances) if confiances else float(info.language_probability or 0.0)
        return ResultatTranscription(transcription=transcription, confiance=round(confiance, 4))
