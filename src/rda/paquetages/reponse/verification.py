import re

from rda.commun.types import ModeReponse
from rda.paquetages.reponse.reclassement import PassageReclasse


def verifier_ancrage(mode: ModeReponse, reponse: str, retenus: list[PassageReclasse]) -> bool:
    if mode == ModeReponse.ABSTENTION:
        return True
    if not retenus:
        return False
    if mode == ModeReponse.GENERATIF:
        citations = {int(x) for x in re.findall(r"\[(\d+)\]", reponse)}
        return bool(citations) and citations.issubset(set(range(1, len(retenus[:3]) + 1)))
    return "[1]" in reponse or "Source:" in reponse

