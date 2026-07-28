"""schema initial des trois bases

Revision ID: 0001_schema_initial
Revises:
Create Date: 2026-07-25
"""

from alembic import op

revision = "0001_schema_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    nom_base = bind.engine.url.database or ""
    if "corpus" in nom_base:
        _upgrade_corpus()
    elif "identite" in nom_base:
        _upgrade_identite()
    else:
        _upgrade_intelligence()


def downgrade() -> None:
    bind = op.get_bind()
    nom_base = bind.engine.url.database or ""
    if "corpus" in nom_base:
        op.execute("DROP TABLE IF EXISTS taches_ingestion, termes_metier, figures, tableaux, passages, pages, habilitations_document, versions_document, documents CASCADE")
    elif "identite" in nom_base:
        op.execute("DROP TABLE IF EXISTS journal_acces_document, journal_audit, sessions, agents_groupes, agents_roles, postes_groupes, groupes_securite, roles, agents, postes, structures CASCADE")
    else:
        op.execute("DROP TABLE IF EXISTS resultats_evaluation, jeux_evaluation, versions_seuils, modeles_ia, signalements, analyses_passage, analyses_requete, citations, messages, conversations CASCADE")


def _upgrade_identite() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS structures (
          id_structure uuid PRIMARY KEY, code text UNIQUE NOT NULL, libelle text NOT NULL,
          type text NOT NULL, id_parent uuid REFERENCES structures(id_structure)
        );
        CREATE TABLE IF NOT EXISTS postes (
          id_poste uuid PRIMARY KEY, code text UNIQUE NOT NULL, libelle text NOT NULL,
          famille_metier text NOT NULL, niveau_hierarchique int NOT NULL, actif boolean NOT NULL DEFAULT true
        );
        CREATE TABLE IF NOT EXISTS agents (
          id_agent uuid PRIMARY KEY, matricule text UNIQUE NOT NULL, nom text NOT NULL, prenom text NOT NULL,
          courriel text UNIQUE NOT NULL, empreinte_mdp text NOT NULL, id_poste uuid REFERENCES postes(id_poste),
          id_structure uuid REFERENCES structures(id_structure), statut text NOT NULL, reference_annuaire text
        );
        CREATE TABLE IF NOT EXISTS roles (id_role int PRIMARY KEY, code text UNIQUE NOT NULL, libelle text NOT NULL);
        CREATE TABLE IF NOT EXISTS groupes_securite (
          id_groupe uuid PRIMARY KEY, code text UNIQUE NOT NULL, libelle text NOT NULL,
          niveau_confidentialite int NOT NULL, perimetre_metier text NOT NULL
        );
        CREATE TABLE IF NOT EXISTS postes_groupes (
          id_poste uuid REFERENCES postes(id_poste), id_groupe uuid REFERENCES groupes_securite(id_groupe),
          date_activation timestamptz NOT NULL, PRIMARY KEY(id_poste, id_groupe)
        );
        CREATE TABLE IF NOT EXISTS agents_roles (
          id_agent uuid REFERENCES agents(id_agent), id_role int REFERENCES roles(id_role),
          date_attribution timestamptz NOT NULL, PRIMARY KEY(id_agent, id_role)
        );
        CREATE TABLE IF NOT EXISTS agents_groupes (
          id_agent uuid REFERENCES agents(id_agent), id_groupe uuid REFERENCES groupes_securite(id_groupe),
          origine text NOT NULL, date_attribution timestamptz NOT NULL, date_expiration timestamptz,
          PRIMARY KEY(id_agent, id_groupe, origine)
        );
        CREATE TABLE IF NOT EXISTS sessions (
          id_session uuid PRIMARY KEY, id_agent uuid REFERENCES agents(id_agent), empreinte_jeton text UNIQUE NOT NULL,
          canal text NOT NULL, groupes_resolus jsonb NOT NULL, adresse_ip text, date_ouverture timestamptz NOT NULL,
          date_expiration timestamptz NOT NULL, date_revocation timestamptz
        );
        CREATE TABLE IF NOT EXISTS journal_audit (
          id_entree uuid PRIMARY KEY, horodatage timestamptz NOT NULL, ref_agent uuid, action text NOT NULL,
          entite_cible text, adresse_ip text, resultat text NOT NULL, detail jsonb NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE TABLE IF NOT EXISTS journal_acces_document (
          id_acces uuid PRIMARY KEY, id_agent uuid NOT NULL, ref_version uuid NOT NULL, ref_message uuid NOT NULL,
          horodatage timestamptz NOT NULL
        );
        """
    )


def _upgrade_corpus() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE TABLE IF NOT EXISTS documents (
          id_document uuid PRIMARY KEY, reference_kalati text UNIQUE NOT NULL, titre text NOT NULL,
          type_document text NOT NULL, perimetre_metier text NOT NULL, ref_structure uuid, supprime boolean NOT NULL DEFAULT false
        );
        CREATE TABLE IF NOT EXISTS versions_document (
          id_version uuid PRIMARY KEY, id_document uuid REFERENCES documents(id_document), indice text NOT NULL,
          date_effet date NOT NULL, date_abrogation date, statut text NOT NULL, empreinte_fichier char(64) NOT NULL,
          reference_stockage text NOT NULL, nb_pages int NOT NULL, UNIQUE(id_document, indice)
        );
        CREATE INDEX IF NOT EXISTS ix_versions_document_dates ON versions_document(date_effet, date_abrogation);
        CREATE TABLE IF NOT EXISTS habilitations_document (
          id_document uuid REFERENCES documents(id_document), ref_groupe uuid NOT NULL, niveau_minimum int NOT NULL,
          cache_terminal boolean NOT NULL DEFAULT false, PRIMARY KEY(id_document, ref_groupe)
        );
        CREATE TABLE IF NOT EXISTS pages (
          id_page uuid PRIMARY KEY, id_version uuid REFERENCES versions_document(id_version), numero int NOT NULL,
          texte_brut text NOT NULL, reference_image text, UNIQUE(id_version, numero)
        );
        CREATE TABLE IF NOT EXISTS passages (
          id_passage uuid PRIMARY KEY, id_version uuid REFERENCES versions_document(id_version), ordre int NOT NULL,
          type text NOT NULL, chemin_hierarchique text NOT NULL, page_debut int NOT NULL, page_fin int NOT NULL,
          texte text NOT NULL, vecteur vector(768), index_lexical tsvector, nb_jetons int NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_passages_vecteur_hnsw ON passages USING hnsw (vecteur vector_cosine_ops);
        CREATE INDEX IF NOT EXISTS ix_passages_index_lexical ON passages USING gin(index_lexical);
        CREATE TABLE IF NOT EXISTS tableaux (
          id_tableau uuid PRIMARY KEY, id_passage uuid UNIQUE REFERENCES passages(id_passage), contenu_markdown text NOT NULL,
          structure_json jsonb NOT NULL, nb_lignes int NOT NULL, nb_colonnes int NOT NULL
        );
        CREATE TABLE IF NOT EXISTS figures (
          id_figure uuid PRIMARY KEY, id_passage uuid UNIQUE REFERENCES passages(id_passage), reference_image text NOT NULL,
          legende_generee text, texte_ocr text, fiabilite_extraction double precision
        );
        CREATE TABLE IF NOT EXISTS termes_metier (
          id_terme uuid PRIMARY KEY, terme text UNIQUE NOT NULL, definition text NOT NULL, synonymes jsonb NOT NULL,
          ref_version_source uuid, perimetre_metier text NOT NULL, prononciations jsonb NOT NULL
        );
        CREATE TABLE IF NOT EXISTS taches_ingestion (
          id_tache uuid PRIMARY KEY, statut text NOT NULL, reference_stockage text NOT NULL, detail jsonb NOT NULL,
          date_creation timestamptz NOT NULL, date_fin timestamptz
        );
        ALTER TABLE passages ENABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS passages_groupes_agent ON passages;
        CREATE POLICY passages_groupes_agent ON passages
          FOR SELECT USING (
            current_setting('app.groupes_agent', true) IS NOT NULL
            AND EXISTS (
              SELECT 1
              FROM versions_document v
              JOIN habilitations_document h ON h.id_document = v.id_document
              WHERE v.id_version = passages.id_version
                AND h.ref_groupe::text = ANY(string_to_array(current_setting('app.groupes_agent', true), ','))
            )
          );
        DO $$ BEGIN CREATE ROLE rda_corpus_app LOGIN PASSWORD 'rda_corpus_app';
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        DO $$ BEGIN CREATE ROLE rda_corpus_ingestion LOGIN PASSWORD 'rda_corpus_ingestion';
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        GRANT USAGE ON SCHEMA public TO rda_corpus_app, rda_corpus_ingestion;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO rda_corpus_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO rda_corpus_ingestion;
        REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM rda_corpus_app, rda_corpus_ingestion;
        """
    )


def _upgrade_intelligence() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
          id_conversation uuid PRIMARY KEY, ref_agent uuid NOT NULL, titre text, date_creation timestamptz NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
          id_message uuid PRIMARY KEY, id_conversation uuid REFERENCES conversations(id_conversation), role text NOT NULL,
          question text, contenu text NOT NULL, mode text, confiance double precision, seuil double precision,
          perimetre text, date_reference date, date_creation timestamptz NOT NULL
        );
        CREATE TABLE IF NOT EXISTS citations (
          id_citation uuid PRIMARY KEY, id_message uuid REFERENCES messages(id_message), rang int NOT NULL,
          reference_normative text NOT NULL, extrait_affiche text NOT NULL, id_passage uuid NOT NULL,
          id_version uuid NOT NULL, page int NOT NULL, UNIQUE(id_message, rang)
        );
        CREATE TABLE IF NOT EXISTS analyses_requete (
          id_analyse uuid PRIMARY KEY, ref_message uuid NOT NULL, requete_normalisee text NOT NULL,
          requete_etendue text NOT NULL, perimetre_detecte text NOT NULL, mode_propose text NOT NULL,
          score_confiance double precision NOT NULL, ref_version_seuils uuid, nb_candidats int NOT NULL,
          latence_ms int NOT NULL, date_analyse timestamptz NOT NULL
        );
        CREATE TABLE IF NOT EXISTS analyses_passage (
          id_analyse_passage uuid PRIMARY KEY, id_analyse uuid REFERENCES analyses_requete(id_analyse),
          ref_passage uuid NOT NULL, score_dense double precision NOT NULL, score_lexical double precision NOT NULL,
          score_fusion double precision NOT NULL, rang int NOT NULL, retenu boolean NOT NULL
        );
        CREATE TABLE IF NOT EXISTS signalements (
          id_signalement uuid PRIMARY KEY, ref_message uuid NOT NULL, type_probleme text NOT NULL,
          commentaire text, statut text NOT NULL, date_creation timestamptz NOT NULL
        );
        CREATE TABLE IF NOT EXISTS modeles_ia (
          id_modele uuid PRIMARY KEY, nom text NOT NULL, type text NOT NULL, version text NOT NULL,
          quantisation text, empreinte text NOT NULL, consommation_w double precision,
          date_activation timestamptz NOT NULL, date_retrait timestamptz
        );
        CREATE TABLE IF NOT EXISTS versions_seuils (
          id_version uuid PRIMARY KEY, numero_version text NOT NULL, perimetre_metier text NOT NULL,
          seuil_abstention double precision NOT NULL, k_recuperation int NOT NULL, poids_dense double precision NOT NULL,
          poids_lexical double precision NOT NULL, nb_citations_min int NOT NULL, date_activation timestamptz NOT NULL,
          UNIQUE(numero_version, perimetre_metier)
        );
        CREATE TABLE IF NOT EXISTS jeux_evaluation (id_jeu uuid PRIMARY KEY, nom text NOT NULL, donnees jsonb NOT NULL);
        CREATE TABLE IF NOT EXISTS resultats_evaluation (
          id_resultat uuid PRIMARY KEY, id_jeu uuid REFERENCES jeux_evaluation(id_jeu),
          metriques jsonb NOT NULL, date_execution timestamptz NOT NULL
        );
        CREATE EXTENSION IF NOT EXISTS pgcrypto;
        CREATE OR REPLACE FUNCTION verifier_message_generatif_cite() RETURNS trigger AS $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM messages m
            WHERE m.mode = 'GENERATIF'
              AND NOT EXISTS (SELECT 1 FROM citations c WHERE c.id_message = m.id_message)
          ) THEN
            RAISE EXCEPTION 'message generatif sans citation';
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        DROP TRIGGER IF EXISTS tg_message_generatif_cite ON messages;
        CREATE CONSTRAINT TRIGGER tg_message_generatif_cite
          AFTER INSERT OR UPDATE ON messages
          DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION verifier_message_generatif_cite();
        INSERT INTO versions_seuils
          (id_version, numero_version, perimetre_metier, seuil_abstention, k_recuperation, poids_dense, poids_lexical, nb_citations_min, date_activation)
        VALUES
          (gen_random_uuid(), 'initiale', 'SECURITE', 0.72, 60, 0.5, 0.5, 1, now()),
          (gen_random_uuid(), 'initiale', 'TRANSPORT', 0.68, 60, 0.5, 0.5, 1, now()),
          (gen_random_uuid(), 'initiale', 'RH', 0.55, 60, 0.5, 0.5, 1, now()),
          (gen_random_uuid(), 'initiale', 'JURIDIQUE', 0.55, 60, 0.5, 0.5, 1, now()),
          (gen_random_uuid(), 'initiale', 'FINANCE', 0.45, 60, 0.5, 0.5, 1, now()),
          (gen_random_uuid(), 'initiale', 'COMMERCIAL', 0.40, 60, 0.5, 0.5, 1, now()),
          (gen_random_uuid(), 'initiale', 'DEFAUT', 0.60, 60, 0.5, 0.5, 1, now())
        ON CONFLICT DO NOTHING;
        DO $$ BEGIN CREATE ROLE rda_intelligence_app LOGIN PASSWORD 'rda_intelligence_app';
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        GRANT USAGE ON SCHEMA public TO rda_intelligence_app;
        GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO rda_intelligence_app;
        REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM rda_intelligence_app;
        """
    )
