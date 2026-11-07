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


---

# Module RA — maintenance par realite augmentee

Extension du backend : questions sur un equipement avec photo facultative, reponse citee produite
par un modele vision-langage, identification d'equipement par photo, localisation d'un composant.

Le module est **distinct de KALATI** : ses propres artefacts, ses propres services d'inference, son
propre schema. Il ne reutilise de KALATI que l'authentification. `docker compose up` demarre KALATI
seul, exactement comme avant.

Specification complete : [docs/spec-module-ra.md](docs/spec-module-ra.md).

## Demarrage

```bash
docker compose up                    # KALATI seul, comportement inchange
docker compose --profile ra up       # KALATI + les deux services du module RA
```

Les deux services ajoutes n'exposent aucun port : ils ne sont joignables que depuis le reseau interne.

| Service | Role | Memoire |
|---|---|---|
| `ra-vision` | Qwen2.5-VL-3B servi par llama.cpp | 6 Go |
| `ra-encodeurs` | e5 + SigLIP2 + reclasseur, CPU | 5 Go |

### Prerequis

Deposer dans `${RA_DATA}/modeles` les deux fichiers GGUF, sans quoi `ra-vision` ne demarre pas :

- `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf`
- `mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf`

Ils se recuperent depuis `ggml-org/Qwen2.5-VL-3B-Instruct-GGUF` sur Hugging Face (~2,5 Go).

## Chargement des artefacts

```bash
docker compose exec rda-agent \
  python -m rda.ra.chargement.charger_artefacts --dossier /ra-data/artefacts
```

La commande verifie le contrat des artefacts, **controle la coherence de l'encodeur**, puis ecrit
dans le schema `ra`.

Le controle de coherence reencode 32 elements avec l'encodeur reellement en service et compare au
vecteur stocke. Si les cosinus descendent sous 0,99, l'index et les requetes ne vivent pas dans le
meme espace vectoriel : tous les scores denses sont alors faux, sans que rien ne le signale. Le
chargement echoue donc franchement.

```bash
# verifier sans rien ecrire
python -m rda.ra.chargement.charger_artefacts --dossier /ra-data/artefacts --controle-seul
```

> **Les artefacts livres echouent ce controle.** `modeles.json` declare un encodeur affine dont les
> poids n'ont jamais ete livres. Deux issues : fournir ces poids a `ra-encodeurs`, ou reexporter
> l'index avec l'encodeur de base :
>
> ```bash
> python scripts/reexporter_index_texte.py --dossier /ra-data/artefacts
> ```
>
> Le reexport passe par `ra-encodeurs`, donc l'index et les requetes utilisent le meme modele par
> construction. L'index visuel n'est pas touche : SigLIP2 n'a pas ete affine.

## Comptes de test

```bash
docker compose exec rda-agent python scripts/creer_comptes_test_ra.py
```

| Compte | Groupes |
|---|---|
| `technicien.dmat@test` | `G_DMAT` |
| `technicien.dif@test` | `G_DIF` |
| `securite@test` | `G_DMAT` + `G_DIF` |

Mots de passe dans `.env` (`RDA_RA_MDP_*`). Le script est idempotent et ne touche pas aux autres
comptes.

## Routes

Montees sous `/api/v1/ra`, toutes authentifiees par le jeton KALATI et journalisees dans `ra.journal`.

| Route | Role |
|---|---|
| `POST /question` | question ± photo -> reponse citee ou abstention |
| `POST /localiser` | photo + cible -> boites englobantes |
| `GET /equipements` | referentiel filtre par habilitation |
| `GET /equipements/{id}/documents` | documents d'un equipement |
| `POST /equipements/{id}/photos` | versement d'une photo terrain |
| `GET /images/{chemin}` | image d'une source, sous controle d'acces |
| `GET /admin/journal` | journal du module (administrateur) |
| `GET /admin/politique` | seuils actifs (administrateur) |

`GET /health` est etendu : etat des deux services, nombre d'elements, encodeur en service, version
d'artefacts. Son contrat KALATI est preserve — `statut` garde sa valeur.

Contrairement a `POST /questions` de KALATI, **aucune route `/ra/*` n'accepte l'en-tete
`X-Groupes-Agent`**. Les habilitations viennent de la session et d'elle seule : laisser le client
annoncer ses groupes reviendrait a le laisser choisir ses droits.

## Acces depuis un telephone

L'API ecoute sur `0.0.0.0:8000`. Pour y acceder depuis un telephone du reseau local :

```bash
ip route get 1.1.1.1 | grep -oP 'src \K[\d.]+'   # adresse LAN du PC
sudo ufw allow 8000/tcp                          # si ufw est actif
```

Ajouter l'origine du serveur de developpement du front a `RDA_ORIGINES_CORS` dans `.env`. Les
origines Capacitor (`capacitor://localhost`, `https://localhost`, `http://localhost`) y sont deja.

Alternative sans reseau, pour un telephone branche en USB — elle evite pare-feu et sous-reseaux :

```bash
adb reverse tcp:8000 tcp:8000    # le telephone atteint le PC via http://localhost:8000
```

## Recette

```bash
# proprietes de la remise a l'echelle des boites, sans aucun service
python scripts/calibrer_localisation.py --auto

# rejoue le jeu d'evaluation ; services requis
python scripts/evaluer.py --dossier /ra-data/artefacts --n 30
```

Les chiffres de reference viennent d'un GPU Kaggle : **sur CPU les latences seront tres
superieures**. Ce sont les mesures de qualite qui doivent se retrouver — taux de citation 1,000,
abstention juste 1,000, hallucination 0,000.

## Limites connues

- **Latence.** Une reponse avec image sur CPU prend plusieurs dizaines de secondes. Les delais
  d'attente sont larges a dessein et configurables dans `.env`.
- **Un seul equipement dans le corpus livre.** L'identification par photo n'est pas demontrable :
  toute photo est attribuee au seul candidat, et l'ecart au second vaut mecaniquement le score.
  Elle devient significative a partir de deux equipements.
- **Aucun cloisonnement reel testable sur les donnees livrees** : tout le corpus est en `G_DMAT`.
  Les tests de cloisonnement s'appuient sur des elements synthetiques.
- **Sessions en memoire.** Elles ne survivent pas a un redemarrage de l'API. Limite heritee de
  KALATI, hors perimetre du module.
