"""droit de rechargement des artefacts pour la chaine d'ingestion

Revision ID: 0003_ra_rechargement
Revises: 0002_schema_ra
Create Date: 2026-09-21

La migration 0002 revoquait DELETE a tous les roles, en suivant le principe « aucun composant
applicatif n'a le droit DELETE ; les suppressions metier sont logiques ». Ce principe vise la
chaine conversationnelle, et il reste entier pour elle.

Mais recharger les artefacts n'est pas une suppression metier : c'est une reingestion, qui
remplace l'index en bloc. Sans ce droit, « charger_artefacts » echoue sur « permission denied for
table elements », et la seule alternative — un upsert — laisserait trainer les lignes d'une
version d'artefacts plus fournie que la suivante, donc un index incoherent avec les matrices
reconstruites en memoire.

Le droit est donc accorde a « rda_corpus_ingestion » seul, et sur les deux tables de contenu
seulement. « rda_corpus_app », qui sert les requetes des agents, n'obtient DELETE nulle part :
ni sur le contenu, ni sur le journal, ni sur les photos.
"""

from alembic import op

revision = "0003_ra_rechargement"
down_revision = "0002_schema_ra"
branch_labels = None
depends_on = None


def _est_corpus() -> bool:
    return "corpus" in (op.get_bind().engine.url.database or "")


def upgrade() -> None:
    if _est_corpus():
        op.execute(
            """
            GRANT DELETE ON ra.elements, ra.equipements, ra.glossaire
              TO rda_corpus_ingestion;
            REVOKE DELETE ON ALL TABLES IN SCHEMA ra FROM rda_corpus_app;
            """
        )


def downgrade() -> None:
    if _est_corpus():
        op.execute("REVOKE DELETE ON ALL TABLES IN SCHEMA ra FROM rda_corpus_ingestion")
