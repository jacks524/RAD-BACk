"""politique de securite au niveau ligne pour la chaine d'ingestion

Revision ID: 0004_ra_rls_ingestion
Revises: 0003_ra_rechargement
Create Date: 2026-09-21

La migration 0002 active la securite au niveau ligne sur « ra.elements » avec une seule politique,
en lecture. Or des qu'elle est activee, PostgreSQL refuse toute operation qu'aucune politique
n'autorise : le chargement des artefacts echouait donc sur « new row violates row-level security
policy ».

La politique de lecture reste inchangee et continue de cloisonner les agents par groupe. On ajoute
une politique distincte, reservee au role d'ingestion, qui n'est jamais celui des requetes : ce
role alimente l'index, il ne repond a personne. Le cloisonnement des lecteurs n'en est pas affecte.

Le meme defaut existe sur « passages », cote KALATI, mais il n'est pas corrige ici : ce serait
changer le comportement d'un composant hors du perimetre de ce module.
"""

from alembic import op

revision = "0004_ra_rls_ingestion"
down_revision = "0003_ra_rechargement"
branch_labels = None
depends_on = None


def _est_corpus() -> bool:
    return "corpus" in (op.get_bind().engine.url.database or "")


def upgrade() -> None:
    if _est_corpus():
        op.execute(
            """
            DROP POLICY IF EXISTS ra_elements_ingestion ON ra.elements;
            CREATE POLICY ra_elements_ingestion ON ra.elements
              FOR ALL TO rda_corpus_ingestion
              USING (true) WITH CHECK (true);

            DROP POLICY IF EXISTS ra_photos_ingestion ON ra.photos;
            CREATE POLICY ra_photos_ingestion ON ra.photos
              FOR ALL TO rda_corpus_ingestion
              USING (true) WITH CHECK (true);

            -- L'application verse les photos des techniciens et ecrit le journal : sans
            -- politique d'insertion, ces deux ecritures seraient refusees de la meme facon.
            DROP POLICY IF EXISTS ra_photos_depot ON ra.photos;
            CREATE POLICY ra_photos_depot ON ra.photos
              FOR INSERT TO rda_corpus_app
              WITH CHECK (true);
            """
        )


def downgrade() -> None:
    if _est_corpus():
        op.execute(
            """
            DROP POLICY IF EXISTS ra_elements_ingestion ON ra.elements;
            DROP POLICY IF EXISTS ra_photos_ingestion ON ra.photos;
            DROP POLICY IF EXISTS ra_photos_depot ON ra.photos;
            """
        )
