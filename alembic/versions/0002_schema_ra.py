"""schema ra du module de maintenance par realite augmentee

Revision ID: 0002_schema_ra
Revises: 0001_schema_initial
Create Date: 2026-09-21

Ne s'applique qu'a la base corpus ; les deux autres bases sont laissees intactes, selon le meme
aiguillage par nom de base que la migration initiale.
"""

from alembic import op

revision = "0002_schema_ra"
down_revision = "0001_schema_initial"
branch_labels = None
depends_on = None


def _est_corpus() -> bool:
    return "corpus" in (op.get_bind().engine.url.database or "")


def upgrade() -> None:
    if _est_corpus():
        _upgrade_corpus()


def downgrade() -> None:
    if _est_corpus():
        op.execute("DROP SCHEMA IF EXISTS ra CASCADE")


def _upgrade_corpus() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE SCHEMA IF NOT EXISTS ra;

        -- Referentiel des equipements. La cle est celle de l'artefact (« MOTEUR_WEG_W22 ») et non
        -- un UUID : c'est elle que l'application RA envoie comme filtre, et elle est stable.
        CREATE TABLE IF NOT EXISTS ra.equipements (
          equipement_id text PRIMARY KEY,
          nom           text NOT NULL,
          direction     text NOT NULL,
          famille       text NOT NULL,
          groupe        text NOT NULL,
          constructeur  text,
          modele        text,
          fiche_presente boolean NOT NULL DEFAULT false,
          date_versement timestamptz NOT NULL DEFAULT now()
        );

        -- Les 21 colonnes du contrat d'artefact, reprises sans renommage ni omission, plus les
        -- deux plongements. vecteur_image est nul pour les elements non visuels.
        CREATE TABLE IF NOT EXISTS ra.elements (
          id                  text PRIMARY KEY,
          equipement_id       text NOT NULL REFERENCES ra.equipements(equipement_id),
          equipement_nom      text NOT NULL,
          famille             text NOT NULL,
          direction           text NOT NULL,
          groupe              text NOT NULL,
          cle_doc             text NOT NULL,
          titre_doc           text NOT NULL,
          type_doc            text NOT NULL,
          indice              text,
          date_effet          date,
          date_abrogation     date,
          chemin_hierarchique text NOT NULL,
          page_debut          int,
          page_fin            int,
          type                text NOT NULL,
          texte               text NOT NULL,
          reference           text NOT NULL,
          texte_ocr           text,
          chemin_image        text,
          description_json    jsonb,
          vecteur_texte       vector(768) NOT NULL,
          vecteur_image       vector(768),
          ordre               int NOT NULL
        );

        -- L'ordre reproduit la position dans elements.parquet : il permet de reconstruire les
        -- matrices en memoire et l'index BM25 dans le meme ordre que les plongements exportes.
        CREATE UNIQUE INDEX IF NOT EXISTS ix_ra_elements_ordre ON ra.elements(ordre);
        CREATE INDEX IF NOT EXISTS ix_ra_elements_filtre
          ON ra.elements(groupe, equipement_id, date_effet, date_abrogation);
        CREATE INDEX IF NOT EXISTS ix_ra_elements_type ON ra.elements(type);
        CREATE INDEX IF NOT EXISTS ix_ra_elements_vecteur_texte
          ON ra.elements USING hnsw (vecteur_texte vector_cosine_ops);
        CREATE INDEX IF NOT EXISTS ix_ra_elements_vecteur_image
          ON ra.elements USING hnsw (vecteur_image vector_cosine_ops);

        -- Seuils versionnes, jamais modifies en place : numero_version croissant.
        CREATE TABLE IF NOT EXISTS ra.politique (
          numero_version   int PRIMARY KEY,
          seuils_abstention jsonb NOT NULL,
          seuil_generatif  double precision NOT NULL,
          k_recuperation   int NOT NULL,
          k_final          int NOT NULL,
          rrf_k            int NOT NULL,
          poids_canaux     jsonb NOT NULL,
          max_images_reponse int NOT NULL,
          seuil_identification double precision NOT NULL,
          marge_identification double precision NOT NULL,
          vlm_max_pixels_reponse int NOT NULL,
          phrase_abstention text NOT NULL,
          prompt_systeme   text NOT NULL,
          prompt_description text NOT NULL,
          date_activation  date NOT NULL,
          active           boolean NOT NULL DEFAULT true
        );

        -- Glossaire du module : terme canonique -> synonymes. Distinct de termes_metier, qui porte
        -- le glossaire ferroviaire de KALATI avec definitions et prononciations.
        CREATE TABLE IF NOT EXISTS ra.glossaire (
          terme     text PRIMARY KEY,
          synonymes jsonb NOT NULL
        );

        -- Tracabilite des chargements d'artefacts : c'est ici qu'on prouve quel encodeur a produit
        -- l'index effectivement en service, et avec quel resultat au controle de coherence.
        CREATE TABLE IF NOT EXISTS ra.chargements (
          id_chargement    uuid PRIMARY KEY,
          horodatage       timestamptz NOT NULL DEFAULT now(),
          version_artefacts text NOT NULL,
          empreinte        char(64) NOT NULL,
          encodeur_texte   text NOT NULL,
          encodeur_visuel  text NOT NULL,
          cosinus_median   double precision,
          controle_reussi  boolean NOT NULL,
          nb_elements      int NOT NULL,
          nb_visuels       int NOT NULL,
          detail           jsonb NOT NULL DEFAULT '{}'::jsonb
        );

        -- Photos versees par les techniciens. Le fichier est dans MinIO ; seule la reference l'est ici.
        CREATE TABLE IF NOT EXISTS ra.photos (
          id_photo      uuid PRIMARY KEY,
          ref_agent     text NOT NULL,
          equipement_id text REFERENCES ra.equipements(equipement_id),
          ref_objet     text NOT NULL,
          type_mime     text NOT NULL,
          taille_octets int NOT NULL,
          largeur       int,
          hauteur       int,
          horodatage    timestamptz NOT NULL DEFAULT now(),
          supprimee     boolean NOT NULL DEFAULT false
        );

        -- Journal du module, en ajout seul. groupes_resolus y est conserve : c'est ce qui rend le
        -- cloisonnement auditable apres coup — on peut prouver pourquoi un agent a obtenu, ou non,
        -- une source donnee.
        CREATE TABLE IF NOT EXISTS ra.journal (
          id_entree       uuid PRIMARY KEY,
          horodatage      timestamptz NOT NULL DEFAULT now(),
          ref_agent       text,
          action          text NOT NULL,
          equipement_id   text,
          groupes_resolus jsonb NOT NULL,
          mode            text,
          confiance       double precision,
          seuil_applique  double precision,
          nb_citations    int,
          latence_ms      int,
          resultat        text NOT NULL,
          adresse_ip      text,
          detail          jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS ix_ra_journal_horodatage ON ra.journal(horodatage DESC);
        CREATE INDEX IF NOT EXISTS ix_ra_journal_agent ON ra.journal(ref_agent, horodatage DESC);

        -- Cloisonnement au niveau ligne. Contrairement a la politique sur passages, la comparaison
        -- est texte contre texte : ra.elements.groupe porte le code de l'artefact (« G_DMAT ») et
        -- groupes_resolus porte des codes, pas des UUID.
        ALTER TABLE ra.elements ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS ra_elements_groupes_agent ON ra.elements;
        CREATE POLICY ra_elements_groupes_agent ON ra.elements
          FOR SELECT USING (
            current_setting('app.groupes_agent', true) IS NOT NULL
            AND groupe = ANY(string_to_array(current_setting('app.groupes_agent', true), ','))
          );

        ALTER TABLE ra.photos ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS ra_photos_agent ON ra.photos;
        CREATE POLICY ra_photos_agent ON ra.photos
          FOR SELECT USING (
            current_setting('app.ref_agent', true) IS NOT NULL
            AND ref_agent = current_setting('app.ref_agent', true)
          );

        GRANT USAGE ON SCHEMA ra TO rda_corpus_app, rda_corpus_ingestion;
        GRANT SELECT ON ALL TABLES IN SCHEMA ra TO rda_corpus_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ra TO rda_corpus_ingestion;

        -- Exception etroite au principe « le corpus est en lecture seule pour la chaine
        -- conversationnelle » : le journal et le depot de photos sont les deux seules tables ou
        -- l'application ecrit, et seulement en INSERT. Les tables de connaissance restent en
        -- lecture seule pour elle, et personne n'a le droit DELETE.
        GRANT INSERT ON ra.journal, ra.photos TO rda_corpus_app;
        REVOKE DELETE ON ALL TABLES IN SCHEMA ra FROM rda_corpus_app, rda_corpus_ingestion;
        """
    )
