# Module RA — maintenance par réalité augmentée

**Spécification reconstituée** · remplace `prompt_claude_code_rda_ra.md` (perdu) · 21 septembre 2026

> ### Statut de ce document
>
> La spécification d'origine du module RA est perdue. Ce document la reconstitue à partir de trois
> sources vérifiables, et **uniquement** de celles-là :
>
> | Source | Ce qu'elle fonde |
> |---|---|
> | `rda-v2.ipynb` (55 cellules, exécuté) | les algorithmes — portage fidèle, cellule citée à chaque fois |
> | `rda-data/artefacts/` (11 fichiers, mesurés) | le contrat de données — aucun champ inventé |
> | `Specification_Base_Donnees_RDA_CAMRAIL_v2.pdf` (38 tables) | les conventions de schéma et le volet multimodal déjà spécifié |
>
> Tout ce qui ne vient pas de ces trois sources est signalé **[hypothèse]** et listé au §10.
> Ces points sont à trancher avant ou pendant la réalisation ; aucun n'est un détail d'implémentation.

---

## 1. Objet et périmètre

Le module RA ajoute au backend KALATI la maintenance assistée par réalité augmentée : un technicien
photographie un équipement, pose une question, et reçoit une réponse **citée** produite à partir de la
documentation à laquelle son habilitation lui donne accès — ou une abstention explicite.

Trois fonctions :

1. **Question citée** (texte seul ou texte + photo) — réponse ancrée dans les sources, ou abstention.
2. **Identification d'équipement** par photo — similarité image-image contre l'index visuel.
3. **Localisation d'un composant** sur une photo — boîte englobante produite par le modèle de vision.

**Hors périmètre** : tout entraînement. Le backend consomme des artefacts préparés hors ligne (Kaggle).
Le module ne réindexe rien et n'affine aucun modèle.

**Relation à KALATI.** Le module RA est un projet distinct du backend KALATI existant ; ses exigences
divergent sur plusieurs points (schéma propre, services d'inférence propres, client mobile). Le principe
directeur est donc : **réutiliser l'authentification et les habilitations de KALATI, isoler tout le reste.**
Aucune route, table ou service KALATI existant ne change de comportement.

---

## 2. État mesuré des artefacts

Mesuré le 21 septembre 2026 sur `/mnt/kalati/RDA/rda-data/artefacts` (31 Mo).

| Fichier | Contenu mesuré |
|---|---|
| `elements.parquet` | **599 éléments** × 21 colonnes |
| `embeddings_texte.npy` | `(599, 768)` float32, normés (‖v‖ = 1,0000) |
| `embeddings_image.npy` | `(159, 768)` float32, normés |
| `index_visuel.json` | 159 identifiants — aligné sur `embeddings_image`, tous présents dans `elements` |
| `images/` | 159 fichiers PNG/JPG |
| `equipements.json` | **1 équipement** : `MOTEUR_WEG_W22` |
| `glossaire.json` | 51 termes métier → synonymes FR/EN |
| `politique.json` | seuils, poids, prompts, version 1 |
| `modeles.json` | registre des modèles et dimensions |
| `jeu_evaluation.json` | `eval_auto`, `eval_manuel`, `hors_corpus` |
| `resultats_evaluation.json` | résultats de la campagne Kaggle |
| `descriptions_cache.json` | cache des descriptions visuelles (141 Ko) |

Répartition des 599 éléments par type : `TEXTE` 359 · `FIGURE` 96 · `TABLEAU` 81 · `PAGE` 51 · `PHOTO` 12.
159 portent une image et une `description_json` ; 12 portent un `texte_ocr`.

Trois documents sources plus la photothèque, un seul groupe (`G_DMAT`), une seule famille
(`MATERIEL_NON_ROULANT`), aucune `date_abrogation` renseignée.

> **Deux conséquences à assumer.** Avec un seul équipement, l'identification par photo ne peut pas être
> démontrée (toute photo est attribuée au seul candidat) et aucun cloisonnement `G_DIF` réel n'est
> testable sur ces données. Les tests correspondants doivent donc s'appuyer sur des **éléments
> synthétiques injectés en base**, pas sur le corpus livré. Voir §9.

---

## 3. Contrat des artefacts

Le contrat est celui de la cellule 46 du notebook, vérifié contre les fichiers réels. **Aucun champ ne
doit être inventé, aucun rendu facultatif.** Le chargeur rejette l'artefact si une colonne manque.

### 3.1 `elements.parquet` — 21 colonnes, dans cet ordre

| Colonne | Type | Rôle |
|---|---|---|
| `id` | texte | identifiant stable, forme `<cle_doc>#<ordre:04d>` |
| `equipement_id` | texte | clé de filtrage envoyée par l'application RA |
| `equipement_nom` | texte | libellé affiché |
| `famille` | texte | détermine le seuil d'abstention (§6.4) |
| `direction` | texte | DMAT · DIF · … |
| `groupe` | texte | **groupe de sécurité requis** — pivot du cloisonnement |
| `cle_doc` | texte | identifiant du document source |
| `titre_doc` | texte | intitulé affiché dans le message d'abstention |
| `type_doc` | texte | MANUEL · CATALOGUE · PHOTO |
| `indice` | texte | indice de révision (`FR-07`, `Rev 06`, `EN`, `—`) |
| `date_effet` | texte ISO | entrée en vigueur — filtre de validité datée |
| `date_abrogation` | texte ISO ou nul | fin de validité |
| `chemin_hierarchique` | texte | « Titre II > Chapitre 3 > Art. 15 » |
| `page_debut` | entier ou nul | première page couverte |
| `page_fin` | entier ou nul | dernière page couverte |
| `type` | texte | TEXTE · TABLEAU · FIGURE · PAGE · PHOTO |
| `texte` | texte | contenu indexé et cité |
| `reference` | texte | référence lisible restituée au technicien |
| `texte_ocr` | texte ou nul | texte lu dans l'image |
| `chemin_image` | texte ou nul | **chemin relatif** `images/<nom>` |
| `description_json` | texte JSON ou nul | description structurée produite par le VLM à l'ingestion |

`description_json` suit le gabarit de `politique.prompt_description` : `type_visuel`, `titre`,
`description`, `composants`, `reperes`, `valeurs`, `anomalies`, `texte_lisible`.

### 3.2 Invariants vérifiés au chargement

Le chargeur **refuse** l'artefact si l'un de ces contrôles échoue :

1. `embeddings_texte.shape == (len(elements), 768)`
2. `embeddings_image.shape == (len(index_visuel), 768)`
3. tout identifiant d'`index_visuel` existe dans `elements` et y porte un `chemin_image` non nul
4. tout `chemin_image` référencé existe dans `images/`
5. les plongements sont normés (‖v‖ ∈ [0,99 ; 1,01])
6. `modeles.dimensions_texte == 768` et `modeles.dimensions_image == 768`

### 3.3 Règle de cohérence de l'encodeur texte

`modeles.json` déclare `encodeur_texte: "encodeur_affine (base intfloat/multilingual-e5-base)"`.
**Aucun poids d'encodeur affiné n'est livré dans les artefacts.**

Le chargeur tranche donc par la mesure, jamais par la déclaration :

1. ré-encoder un échantillon d'éléments (**[hypothèse]** : 32 éléments tirés au hasard, graine 42)
   avec l'encodeur de base `intfloat/multilingual-e5-base`, préfixe `passage: `, normalisation activée ;
2. comparer au vecteur stocké, cosinus élément par élément ;
3. si **tous** les cosinus sont ≥ 0,99 → l'encodeur de base reproduit l'index : on l'utilise pour les
   requêtes ;
4. sinon → l'index vient d'un encodeur affiné absent. Le chargement **échoue** avec un message nommant
   le cosinus médian observé et le poids attendu.

Ce contrôle est ce qui décide de l'encodeur texte utilisé à l'exécution. Une requête encodée par un
modèle différent de celui qui a produit l'index donne des scores dense silencieusement faux — d'où
l'échec franc plutôt qu'un repli.

> **Attendu** : ce contrôle **échouera** sur les artefacts actuels, l'index ayant été produit par un
> encodeur affiné non livré. C'est le comportement correct. Deux issues : récupérer les poids affinés,
> ou réexporter l'index depuis le notebook avec l'encodeur de base. Voir §10.

---

## 4. Architecture de déploiement

Deux services nouveaux dans le `docker-compose` existant, sur le réseau interne, **aucun port publié**.
Le service d'inférence texte de KALATI (`rda-inference`, Qwen2.5-1.5B) reste inchangé.

### 4.1 `ra-vision` — modèle vision-langage

Serveur llama.cpp CPU, image `ghcr.io/ggml-org/llama.cpp:server` (déjà utilisée par KALATI) :

```
-m /modeles/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf
--mmproj /modeles/mmproj-Qwen2.5-VL-3B-Instruct-f16.gguf
--host 0.0.0.0 --port 8080 --threads 4 --ctx-size 4096
```

Le contexte est porté à 4096 car une réponse avec images consomme bien plus que les 1024 de KALATI.
Montage : `/mnt/kalati/RDA/rda-data/modeles:/modeles:ro`.

### 4.2 `ra-encodeurs` — encodeurs et reclasseur

Service Python CPU dédié, trois modèles chargés une fois au démarrage :

| Rôle | Modèle | Sortie |
|---|---|---|
| texte | `intfloat/multilingual-e5-base` (ou affiné, §3.3) | 768 dims, normé |
| visuel | `google/siglip2-base-patch16-384` | 768 dims, normé |
| reclasseur | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | score brut (logit) |

Trois routes internes : `POST /encoder/texte`, `POST /encoder/image`, `POST /reclasser`, plus `GET /sante`.
Cache Hugging Face monté sur `/mnt/kalati/RDA/rda-data/hf-cache` — aucun téléchargement au démarrage
une fois le cache chaud.

Ce service isole **toute** la charge torch hors du conteneur API : l'API ne dépend que de `httpx`,
`numpy`, `pyarrow`, `rank_bm25` et `Pillow`.

### 4.3 Profils

Les deux piles doivent pouvoir démarrer séparément sur une machine à 19 Gio :
`docker compose --profile kalati` et `--profile ra`. Mesure d'empreinte exigée au §9.

---

## 5. Schéma de données `ra`

Schéma `ra` dans la base **corpus** existante (image `pgvector/pgvector:pg16` — pgvector déjà disponible,
aucun changement d'image nécessaire). Migration Alembic `0002`, suivant le patron d'aiguillage par nom de
base de `0001_schema_initial`.

Conventions reprises de la spécification de base v2.0 : PK en UUID, horodatage en TIMESTAMPTZ, références
inter-serveurs **logiques** (jamais de clé étrangère physique franchissant une frontière de serveur),
journal en ajout seul, aucun DELETE — les suppressions sont logiques.

| Table | Rôle |
|---|---|
| `ra.equipements` | référentiel : `equipement_id` (PK texte), nom, direction, famille, `groupe`, constructeur, modèle |
| `ra.elements` | les 21 colonnes du §3.1 + `vecteur_texte VECTOR(768)` + `vecteur_image VECTOR(768)` nullable |
| `ra.politique` | seuils versionnés — jamais modifiés en place, `numero_version` croissant |
| `ra.chargements` | traçabilité : version d'artefacts, empreinte SHA-256, encodeur retenu, horodatage, résultat du contrôle §3.3 |
| `ra.photos` | photos versées par les techniciens : référence d'objet MinIO, type MIME, agent, équipement, horodatage |
| `ra.journal` | un enregistrement par appel `/ra/*` — voir §5.1 |

**Un seul vecteur par ligne d'élément** plutôt que deux tables : un élément visuel porte à la fois un
vecteur texte (sur sa description) et un vecteur image. `vecteur_image` est nul pour les 440 éléments
non visuels.

### 5.1 `ra.journal`

Ajout seul, jamais modifié. Colonnes : `id_entree` UUID PK, `horodatage` TIMESTAMPTZ,
`ref_agent` UUID (référence logique vers `S4.agents`), `action` (`QUESTION` · `IDENTIFIER` · `LOCALISER` ·
`IMAGE` · `PHOTO`), `equipement_id`, `groupes_resolus` JSONB (habilitations **effectivement appliquées**),
`mode` (`EXTRACTIF` · `GENERATIF` · `ABSTENTION` · `NEUTRALISATION` · `CONVERSATION`), `confiance`,
`seuil_applique`, `nb_citations`, `latence_ms`, `resultat` (`SUCCES` · `REFUS` · `ERREUR`), `detail` JSONB.

Journaliser `groupes_resolus` est ce qui rend le cloisonnement **auditable après coup** : on peut prouver
pourquoi un agent a obtenu — ou n'a pas obtenu — une source donnée.

### 5.2 Index

`ivfflat` sur `vecteur_texte` et `vecteur_image` (cosinus), index B-tree sur
`(groupe, equipement_id, date_effet, date_abrogation)` pour que le filtre d'habilitation soit posé par le
moteur, non en post-traitement.

### 5.3 Filtrage au niveau ligne

Conformément au principe de la spécification v2.0 (« aucun passage hors habilitation ne peut être lu :
le filtre est posé par la politique de sécurité au niveau ligne, dans la même clause que la recherche,
non en post-traitement »), `ra.elements` porte une politique RLS lisant `app.groupes_agent`, posée par
`transaction_corpus_habilitee()` qui existe déjà dans `src/rda/infra/bases.py`.

La politique du module compare **du texte à du texte** :

```sql
groupe = ANY(string_to_array(current_setting('app.groupes_agent', true), ','))
```

`ra.elements.groupe` porte le code de l'artefact (`G_DMAT`) et `groupes_resolus` porte des codes
(§8.1) : la comparaison est directe, sans résolution d'UUID.

> **À signaler, sans le corriger.** La politique existante sur `passages` compare
> `h.ref_groupe::text` — un **UUID** — à `app.groupes_agent`, qui reçoit en pratique des **codes**
> (`DEMO_SECURITE`). Elle ne peut donc jamais correspondre, et une lecture de `passages` sous RLS
> renvoie zéro ligne. C'est un défaut latent de KALATI, antérieur au module RA. Le corriger
> changerait le comportement de KALATI : hors périmètre, mais à porter au dossier.

**[hypothèse]** La recherche du module s'exécute en mémoire (§6.1), pas en SQL. Le RLS est donc une
**seconde barrière**, pas la barrière principale : le filtre effectif est appliqué avant le scoring, en
Python. Le RLS protège les accès directs (`/ra/equipements/{id}/documents`, `/ra/images/…`) et garantit
qu'un défaut du filtre mémoire ne devient pas une fuite.

---

## 6. Logique métier

Portage fidèle du notebook. Chaque sous-section cite la cellule qui fait foi.

### 6.1 Index en mémoire

Au démarrage et après chaque chargement d'artefacts, l'API reconstruit en mémoire :

- `EMB_T` `(n, 768)` et `EMB_I` `(m, 768)`, tirés de la base ;
- `VIS_IDX` — positions des éléments visuels, et son inverse `VIS_POS` ;
- l'index **BM25 Okapi** sur les textes tokenisés.

Tokenisation (cellule 22) : minuscules, accents retirés (`NFKD`, combinantes supprimées), `\w+`, puis
retrait de 30 mots vides FR/EN — `le la les de des du un une et ou a au aux en dans pour par sur avec
est sont the of and to in for on is are`.

Empreinte mémoire des plongements : 599 × 768 × 4 o ≈ 1,8 Mo + 159 × 768 × 4 o ≈ 0,5 Mo. Négligeable.

### 6.2 Enrichissement de la requête (cellule 15)

Pour chaque terme du glossaire présent dans la question (comparaison sans accents, en minuscules), les
synonymes sont ajoutés ; réciproquement, si un synonyme de plus de 2 caractères apparaît, le terme
canonique est ajouté. Doublons retirés en conservant l'ordre. La question enrichie alimente les canaux
`dense` et `lexical` — **jamais** le canal `image_texte`, qui reçoit la question brute.

### 6.3 Recherche hybride à quatre canaux (cellule 25)

**Le filtre est appliqué avant le scoring**, par un masque booléen `autorise` :

```
groupe ∈ groupes_agent  ET  equipement_id == equipement (si fourni)
ET  type ∈ types (si fourni)  ET  applicable(élément, date_ref)
```

`applicable` : faux si `date_effet` est postérieure à la date de référence, faux si `date_abrogation`
est atteinte ou dépassée. Si aucun élément n'est autorisé, la recherche retourne une liste vide — et non
les résultats de tous les périmètres.

Quatre canaux, chacun classé sur les `k_recuperation = 30` meilleurs parmi les éléments autorisés :

| Canal | Calcul | Poids |
|---|---|---|
| `dense` | `EMB_T · encoder("query: " + question_enrichie)` | 1,0 |
| `lexical` | BM25 sur la question enrichie tokenisée | 1,0 |
| `image_texte` | `EMB_I · siglip_texte(question brute)` | 0,5 |
| `image_image` | `EMB_I · siglip_image(photo)` — seulement si photo fournie | 1,2 |

Les canaux visuels ne notent que les positions de `VIS_IDX` ; les autres restent à −∞.

**Fusion de rang réciproque** : `score(i) = Σ_canaux poids / (rrf_k + rang)` avec `rrf_k = 60`. Les
`k_recuperation` meilleurs sont retournés avec leur score de fusion et les scores par canal.

### 6.4 Délibération (cellules 27 et 32)

**Reclassement** — le reclasseur note les paires (question, texte tronqué à 1500 caractères), par lots
de 16. Les `k_final = 5` meilleurs sont conservés.

**Confiance** — calibrée sur les scores reclassés :

```
meilleur = σ(score du 1er)
appui    = moyenne des σ(score) des 3 premiers   (= meilleur si moins de 3 candidats)
confiance = 0,7 × meilleur + 0,3 × appui
```

La part d'`appui` pénalise le candidat isolé : une source unique bien notée, sans corroboration,
inspire moins confiance que trois sources concordantes.

**Seuil d'abstention** — par famille de l'élément de tête : `INFRASTRUCTURE` 0,72 ·
`MATERIEL_ROULANT` 0,68 · `MATERIEL_NON_ROULANT` 0,66 · défaut 0,65. Issu de
`tau = (C_err − C_sil) / (G + C_err)` : l'infrastructure est le périmètre où l'erreur coûte le plus.

**Enchaînement complet** (cellule 32) :

1. **Perception** — détection d'injection (`RE_INJECTION`) → mode `NEUTRALISATION`, refus immédiat.
   Civilité pure (`RE_CONVERSATION`) → mode `CONVERSATION`, réponse d'accueil.
   Photo fournie sans équipement précisé → identification (§6.6) ; si confiante, l'équipement est fixé.
2. **Recherche** — §6.3. Aucun candidat → `ABSTENTION` (« Aucun document accessible ne traite de ce
   sujet pour cet équipement »).
3. **Délibération** — `confiance < seuil` → `ABSTENTION`, avec les titres des 3 documents les plus
   proches, dédoublonnés en conservant l'ordre.
4. **Action** — `confiance ≥ seuil_generatif (0,75)` → `GENERATIF`, sinon `EXTRACTIF`.
5. **Vérification d'ancrage** — en mode génératif : si la phrase d'abstention apparaît dans la sortie,
   basculer en `ABSTENTION`. Puis extraire tous les `[n]` : **s'il n'y en a aucun, ou si l'un d'eux sort
   de la plage 1..k_final, replier en `EXTRACTIF`.** Une réponse non étayée n'est jamais restituée.
   Mode `EXTRACTIF` : les 900 premiers caractères de la meilleure source, suivis de `[1]`.

Les citations restituées portent rang, identifiant, type, référence, page, image et les scores par canal.

### 6.5 Génération (cellule 31)

Message système : `politique.prompt_systeme`, repris **mot pour mot** de l'artefact.

Contenu utilisateur, dans cet ordre :

1. jusqu'à `max_images_reponse = 2` images de sources, chacune suivie de « ↑ Image de la source [n]. » ;
2. si photo du technicien : l'image, suivie de « ↑ Photo prise sur le terrain par le technicien
   (contexte, non citable). » ;
3. le bloc « Sources : » — pour chaque source `[n] référence` puis le texte tronqué à 1200 caractères ;
4. « Question : … ».

`vlm_max_pixels_reponse = 501 760` px (640 × 28 × 28), `max_tokens_reponse = 512`, échantillonnage
désactivé, `repetition_penalty = 1,05`.

La photo du technicien est explicitement **non citable** : elle sert au cadrage de la question, jamais
de source. C'est ce qui empêche le modèle de « citer » ce que le technicien lui a montré.

### 6.6 Identification d'équipement (cellule 29)

1. Vecteur SigLIP2 de la photo, produit scalaire contre `EMB_I`.
2. Candidats filtrés par groupe ; `exclure` permet d'ignorer des chemins (évaluation en *leave-one-out*).
3. Les **5 meilleurs** votent : chaque voix pèse son score de similarité, cumulée par équipement.
4. `score` = meilleure similarité parmi les 5 pour l'équipement gagnant ;
   `second` = meilleure similarité parmi les 5 pour un **autre** équipement (0 si aucun).
5. Confiant si `score ≥ 0,72` **et** `score − second ≥ 0,03`.

Retour : `confiant`, `equipement_id`, `equipement_nom`, `score`, `ecart_second`, `votes`.
Index visuel vide → `confiant: false`, raison « aucun visuel indexé » ; aucun candidat autorisé →
raison « aucun visuel autorisé ».

### 6.7 Localisation (cellule 31)

Appel au VLM avec la photo (`vlm_max_pixels = 802 816` px) et la consigne, **en anglais** — formulation
native de Qwen2.5-VL, à conserver telle quelle :

```
Locate "<cible>" in the image and output its bbox coordinates in JSON format:
[{"bbox_2d": [x1, y1, x2, y2], "label": "..."}]. If it is not visible, output [].
```

`max_new_tokens = 200`. La réponse est extraite par `\[.*\]` en mode *dotall*, les virgules traînantes
sont réparées avant analyse JSON.

**Remise à l'échelle** — point le plus délicat du portage. Les coordonnées rendues par le modèle sont
exprimées dans l'image **redimensionnée** qu'il a vue, en patchs de 14 px :

```
h_modele = grille[0][1] × 14      w_modele = grille[0][2] × 14
fx = largeur_photo / w_modele     fy = hauteur_photo / h_modele
```

Chaque boîte est multipliée par `(fx, fy)` puis bornée aux dimensions de la photo.

> **Écart à lever.** En Python, `image_grid_thw` est retourné par le processeur. Avec llama.cpp en
> service HTTP, cette grille **n'est pas exposée**. Il faut donc la recalculer côté API en reproduisant
> le redimensionnement de Qwen2.5-VL (`smart_resize` : multiples de 28, bornés par `min_pixels` et
> `max_pixels`, rapport d'aspect préservé). `scripts/calibrer_localisation.py` valide ce calcul contre
> des boîtes de référence. Voir §10.

Une image annotée (rectangle rouge `(196, 30, 38)`, épaisseur `max(3, largeur/200)`, libellé au-dessus)
est produite et stockée ; la réponse porte son URL, les boîtes en pixels d'origine, et la sortie brute.

---

## 7. Routes

Montées sous **`/api/v1/ra`**, par cohérence avec les routeurs existants — tous montés sous `/api/v1`.
**[hypothèse]** : le prompt de travail indiquait `/ra`. Le client Capacitor étant neuf, le préfixe
complet ne coûte rien ; à confirmer.

Toutes les routes exigent l'authentification KALATI existante et journalisent dans `ra.journal`.

| Route | Rôle |
|---|---|
| `POST /ra/question` | question ± photo → réponse citée ou abstention (§6.4) |
| `POST /ra/localiser` | photo + cible → boîtes englobantes + image annotée (§6.7) |
| `GET /ra/equipements` | référentiel filtré par habilitation |
| `GET /ra/equipements/{id}/documents` | documents d'un équipement, filtrés |
| `POST /ra/equipements/{id}/photos` | versement d'une photo terrain |
| `GET /ra/images/{...}` | image d'une source — **contrôle d'accès obligatoire** |
| `GET /ra/admin/journal` | consultation du journal — administrateur |
| `GET /ra/admin/politique` | politique active et version — administrateur |

`GET /health` est étendu : état de `ra-vision` et `ra-encodeurs`, version d'artefacts, encodeur texte
retenu, nombre d'éléments chargés. La route n'est **pas** renommée `/sante` — KALATI expose `/health` et
le renommer serait une régression.

### 7.1 Photos

Multipart, **≤ 10 Mo**, `image/jpeg` · `image/png` · `image/webp`. Les photos Android arrivent en JPEG
avec une orientation EXIF : `ImageOps.exif_transpose` est appliqué **avant tout traitement**, sinon une
photo prise en portrait est encodée couchée et la similarité visuelle s'effondre. Conversion en RGB,
grand côté ramené à `max_cote_photo = 1600` px.

Stockage dans MinIO, bucket `ra-images` (MinIO est déjà en service pour KALATI). Les images ne sont
servies que par `GET /ra/images/…`, après vérification que le groupe de l'élément figure dans les
habilitations de la session.

### 7.2 Délais et erreurs

Une réponse avec image sur CPU prend **plusieurs dizaines de secondes**. Délais explicites vers
`ra-vision` (**[hypothèse]** : 120 s pour `/ra/question` avec image, 90 s pour `/ra/localiser`, 30 s
pour `ra-encodeurs`), configurables par `.env`. Un dépassement ou une indisponibilité produit une erreur
propre — jamais un plantage, jamais une réponse inventée. En mode `GENERATIF` seul le VLM est
indisponible : replier en `EXTRACTIF` plutôt que d'échouer.

### 7.3 CORS et client mobile

Origines autorisées, configurables par `.env` : `https://localhost`, `http://localhost`,
`capacitor://localhost`, `http://localhost:5173` et `http://<IP-LAN>:5173`. L'API écoute sur `0.0.0.0:8000`
et doit être joignable depuis un téléphone du réseau local.

---

## 8. Authentification et habilitations

> **L'authentification de KALATI n'est pas ce que le prompt de travail supposait.** Inspection faite
> le 21 septembre 2026, voici l'état réel — il change la conception de cette section.

### 8.1 État réel de l'authentification KALATI

| Attendu | Réel |
|---|---|
| habilitations en base (`sessions.groupes_resolus`) | `ServiceIdentite` est adossé à un **fichier JSON** (`/app/identite-demo/utilisateurs.json`) ; les tables `agents`, `sessions`, `groupes_securite` existent dans la migration mais **ne sont pas utilisées** |
| sessions persistées | `SESSIONS_DEMO`, dictionnaire **en mémoire** — perdu à chaque redémarrage, non partagé entre processus |
| dépendance d'authentification sur les routes métier | `POST /questions` n'est **pas authentifiée** : `obtenir_groupes_demo` lit un en-tête `X-Groupes-Agent` et retombe sur `["DEMO_SECURITE", "SECURITE"]` |
| `GET /auth/moi` | renvoie un profil figé, sans lire le jeton |
| habilitations en UUID | `groupes_resolus` contient des **codes texte** (`DEMO_SECURITE`, `groupes_poste`) |
| empreinte de mot de passe | SHA-256 non salé de `courriel:mot_de_passe:secret_jwt` — `bcrypt` et `argon2` sont déclarés en dépendance mais inutilisés |

Seules les routes `/admin/*` sont protégées, par `exiger_administrateur`.

### 8.2 Ce sur quoi le module RA se branche

Il n'existe pas de dépendance d'authentification réutilisable pour une route métier ; il faut en
écrire une. Elle réutilise **le mécanisme de jeton existant**, sans le modifier :

1. en-tête `Authorization: Bearer <jeton>` — même extraction que `exiger_administrateur` ;
2. `ServiceIdentite.agent_par_jeton_demo(jeton)` → l'`AgentSortie` de la session ;
3. `agent.groupes_resolus` → les habilitations appliquées au filtre du §6.3.

C'est bien « même jeton, même mécanisme » : un jeton obtenu par `POST /auth/connexion` ouvre les routes
`/ra/*`. La dépendance est **nouvelle et vit dans `app/ra/`** ; `obtenir_groupes_demo` n'est pas touché,
et le comportement de `POST /questions` ne change pas.

Contrairement à KALATI, **aucune route `/ra/*` n'accepte d'en-tête `X-Groupes-Agent`** : les
habilitations viennent de la session et d'elle seule. Accepter un en-tête reviendrait à laisser le
client choisir ses propres droits, ce qui viderait le cloisonnement de son sens.

### 8.3 Groupes RA

`groupes_resolus` contenant déjà des codes texte, `G_DMAT` et `G_DIF` s'y logent sans conversion et se
comparent directement au champ `groupe` des artefacts. **Aucune table, aucune colonne nouvelle** — c'est
un écart avec le prompt de travail (« table ou colonne de rattachement agent → groupes RA »), rendu
inutile par la forme des données.

Les comptes de test sont donc créés dans `utilisateurs.json`, avec `groupes_poste` renseigné.

### 8.4 Deux limites à porter au dossier

- **Les sessions ne survivent pas à un redémarrage** (dictionnaire en mémoire). Acceptable pour une
  démonstration ; à remplacer par les tables `sessions` avant tout usage réel.
- **L'empreinte de mot de passe est un SHA-256 non salé.** Le module RA n'aggrave pas la situation
  — il réutilise le mécanisme existant — mais les comptes de test qu'il crée en héritent.

Ces deux points relèvent de KALATI, pas du module RA ; les corriger sortirait du périmètre et romprait
la non-régression. Ils sont signalés, non traités.

Comptes de test créés par `scripts/creer_comptes_test_ra.py`, mots de passe dans `.env` :

| Compte | Groupes |
|---|---|
| `technicien.dmat@test` | `G_DMAT` |
| `technicien.dif@test` | `G_DIF` |
| `securite@test` | `G_DMAT` + `G_DIF` |
| administrateur existant | tout |

**Invariant non négociable** : un profil `G_DIF` n'obtient jamais une source ni une image d'un
équipement `G_DMAT`. Le filtrage est appliqué avant le scoring (§6.3), pas en post-traitement.

---

## 9. Tests et recette

### 9.1 Non-régression KALATI

Base mesurée avant travaux : **7 tests passés**. La suite doit rester verte. Un test de fumée est
ajouté : connexion + une question texte de bout en bout.

### 9.2 Tests du module

| Test | Vérifie |
|---|---|
| contrat d'artefacts | les 6 invariants du §3.2, chacun avec un artefact volontairement corrompu |
| cohérence d'encodeur | le §3.3 échoue franchement quand les cosinus sont sous 0,99 |
| filtre avant scoring | un agent `G_DIF` ne voit aucun élément `G_DMAT` — y compris dans les scores par canal |
| image cloisonnée | `GET /ra/images/…` d'un élément `G_DMAT` renvoie 403 à un agent `G_DIF` |
| validité datée | un élément abrogé à la date de référence n'est jamais candidat |
| abstention | confiance sous le seuil → mode `ABSTENTION`, aucune citation |
| ancrage | une réponse générative sans `[n]`, ou avec un `[n]` hors plage, replie en `EXTRACTIF` |
| injection | « ignore les instructions » → `NEUTRALISATION` |
| identification | seuil 0,72 et marge 0,03 respectés ; index vide → non confiant |
| remise à l'échelle | les boîtes reviennent bien en pixels de la photo d'origine |
| orientation EXIF | une photo portrait avec EXIF est redressée avant encodage |
| journal | chaque appel `/ra/*` produit une entrée portant `groupes_resolus` |

Le corpus ne contenant qu'un équipement et qu'un groupe (§2), les tests de cloisonnement et
d'identification s'appuient sur des **éléments synthétiques injectés en base** — un second équipement
fictif en `G_DIF`. Les tester sur le corpus livré donnerait un faux vert.

### 9.3 Recette chiffrée

`scripts/evaluer.py` rejoue `jeu_evaluation.json` et produit le tableau comparable aux résultats Kaggle :

| Mesure | Kaggle (référence) |
|---|---|
| taux de réponse | 0,633 |
| taux de citation | 1,000 |
| source juste | 0,267 |
| abstention juste | 1,000 |
| hallucination | 0,000 |
| latence moyenne | 7,35 s |
| latence p95 | 23,59 s |
| identification (12 photos, *leave-one-out*) | exactitude 1,000 |

Ces chiffres viennent d'un GPU Kaggle. Sur CPU, **les latences seront très supérieures** ; c'est la
qualité (citation, abstention, hallucination) qui doit se retrouver, pas le temps.

`scripts/calibrer_localisation.py` valide la reconstruction de la grille (§6.7).

### 9.4 Empreinte mémoire

Mesure exigée avec tout démarré, sur une machine à 19,4 Gio. Si saturation : profils `kalati` / `ra`
(§4.3) plutôt que dégradation des modèles.

---

## 10. Points ouverts

Rien de ce qui suit n'est tranché par les sources disponibles. Chacun change le résultat.

1. **Encodeur texte affiné absent** (§3.3) — le contrôle de cohérence échouera sur les artefacts
   actuels. Récupérer les poids, ou réexporter l'index avec l'encodeur de base. **Bloquant pour la
   qualité de recherche.**
2. **Modèles GGUF absents** — `ra-vision` ne peut pas démarrer tant que les deux fichiers ne sont pas
   dans `rda-data/modeles/`. *(l'utilisateur les dépose)*
3. **Grille de vision non exposée par llama.cpp** (§6.7) — `smart_resize` doit être reproduit côté API,
   puis calibré. Risque de boîtes décalées si le calcul diverge.
4. **Un seul équipement** (§2) — identification et cloisonnement non démontrables sur le corpus livré.
5. **Préfixe de routes** (§7) — `/api/v1/ra` retenu contre `/ra` indiqué par le prompt de travail.
6. **Échantillon du contrôle de cohérence** (§3.3) — 32 éléments, graine 42.
7. **Délais d'attente** (§7.2) — 120 s / 90 s / 30 s.
8. **RLS en seconde barrière** (§5.3) — la recherche étant en mémoire, le filtre effectif est en Python.
9. **Venv réparé** — le venv pointait vers `/home/jacquy-ngonga4/RAD-BACk/` (disque système saturé) ;
   `pyvenv.cfg`, 24 shebangs et le chemin éditable ont été repointés sur le disque externe. Une copie
   complète du dépôt subsiste sous `/home/jacquy-ngonga4/RAD-BACk/` (477 Mo de venv) — à supprimer si
   elle n'a plus d'usage.
10. **Chemins de déploiement** — le disque est monté sur `/mnt/kalati`, et non sur
    `/media/jacquy-ngonga4/juns3` comme l'indiquait le prompt de travail. Le compose et le `.env`
    pointent déjà correctement ; **aucune migration de chemin n'est à faire.**
11. **Écart assumé au portage fidèle : filtre d'injection.** La regex de la cellule 31 s'achève par
    `ignore\s+(all|previous)\s+instructions`, qui exige `instructions` immédiatement après `all`
    **ou** `previous`. Elle laisse donc passer « ignore all previous instructions », la formulation
    d'injection la plus répandue. Les deux qualificatifs ont été rendus facultatifs et cumulables.
    Aucune mesure de la campagne d'évaluation n'est affectée ; le notebook devrait être corrigé de
    la même façon.
12. **Disque système saturé.** `/` est à 96 % (3,4 Go libres). Le cache BuildKit atterrit dans
    `/var/lib/docker`, sur `/`, bien que `Docker Root Dir` pointe sur le disque externe — un build
    de `ra-encodeurs` a déjà rempli la partition et échoué en ENOSPC. `liberer-espace.sh`
    (à la racine de `RDA/`, à lancer avec sudo) purge les journaux et déplace le SDK Android.
