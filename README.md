# RDA Backend CAMRAIL

Backend FastAPI d'un systeme de Recherche Documentaire Augmentee pour textes normatifs CAMRAIL.
Le service privilegie l'abstention a l'approximation et impose citations, filtrage RLS et journalisation.

## Lancement local

```bash
cp .env.example .env
docker compose up --build
```

Les donnees PostgreSQL restent sur des volumes Docker nommes. MinIO, Redis, les modeles et artefacts
sont montes depuis `KALATI_DATA`.

## Artefacts

Placez dans `${KALATI_DATA}/artefacts` les fichiers produits par la chaine externe:

- `passages.parquet`
- `embeddings.npy`
- `glossaire.json`
- `politique.json`
- `modeles.json`

Le backend les consomme au demarrage si les tables cibles sont vides. Aucun entrainement de modele
n'est effectue dans ce projet.

## Migrations

Les migrations Alembic contiennent les schemas des trois bases. En production, lancez Alembic pour
chaque URL cible avec la variable `RDA_ALEMBIC_BASE`:

```bash
RDA_ALEMBIC_BASE=identite alembic upgrade head
RDA_ALEMBIC_BASE=corpus alembic upgrade head
RDA_ALEMBIC_BASE=intelligence alembic upgrade head
```

## Tests

```bash
pip install -e ".[test]"
pytest
```

Les tests couvrent droits/RLS applicative de requete, versionnement, abstention, injection et recherche
hybride avec conservation des scores.

