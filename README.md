# Base des vols de New York (nycflights13)

Projet pédagogique **MySQL 8.0.16+** basé sur les données publiques
[nycflights13](https://github.com/tidyverse/nycflights13). Il crée les tables
`airlines`, `airports`, `planes`, `weather` et `flights` dans la base `airdata`,
vérifie les clés et les nomenclatures, puis conserve les références absentes
sans inventer leurs métadonnées.

> Supabase héberge PostgreSQL, pas MySQL. Pour cette version, utilisez un
> service MySQL comme Azure Database for MySQL, AWS RDS for MySQL, ou une
> installation MySQL 8.0.16+.

## Modèle relationnel

- `planes (1) -> (N) flights`, via `tailnum` (nullable lorsqu'il manque dans la source).
- `airlines (1) -> (N) flights`, via `carrier`.
- `airports (1) -> (N) flights`, via `origin` et `dest`.
- `airports (1) -> (N) weather`, via `origin`.
- Les compagnies et les aéroports sont en relation plusieurs-à-plusieurs,
  observée à travers les vols.
- PK de `flights`: `(year, month, day, hour, carrier, flight)`.
  Le seul numéro `flight` n'est pas unique.
- La clé météo proposée `(year, month, day, hour, origin)` a 3 collisions
  (heure locale 01:00 répétée lors du changement d'heure d'hiver). La PK
  réellement imposée est donc `(year, month, day, hour, origin, time_hour)`;
  `time_hour` distingue les deux instants UTC sans supprimer de mesure.
- `airports.faa`, `airlines.carrier` et `planes.tailnum` sont des identifiants
  naturels; les contraintes CHECK et le script Python vérifient leur format.
  Les immatriculations source sont alphanumériques (maximum 6 caractères):
  le jeu contient aussi `D942DN`, qui ne suit pas le format US `N...`.

## Mise en place MySQL

1. Créez une instance MySQL **8.0.16 ou plus récente**. Créez une base et un
   compte de chargement avec accès à cette base depuis la console de votre hébergeur:

   ```sql
   CREATE DATABASE airdata CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
   CREATE USER 'airdata_loader'@'%' IDENTIFIED BY 'use-a-unique-secret';
   GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
       ON airdata.* TO 'airdata_loader'@'%';
   ```

   Restreignez l'hôte/réseau autorisé selon les capacités du fournisseur. Pour
   un déploiement durable, séparez le compte de migration (DDL) du compte
   applicatif, qui ne devrait recevoir que les droits nécessaires.
2. Téléchargez le certificat CA TLS fourni par l'hébergeur et notez son chemin.
   Activez les connexions TLS côté hébergeur et autorisez uniquement votre
   adresse IP ou réseau.

### MySQL local sans TLS (développement uniquement)

Pour une base MySQL sur cette machine, définissez `MYSQL_HOST=localhost` et
`MYSQL_SSL_DISABLED=true` dans `.env`. Le chargeur et le tableau de bord
n'exigent alors ni certificat ni configuration TLS côté MySQL. Cette option
est réservée à une connexion locale; ne l'utilisez jamais avec une base distante.

3. Créez un environnement virtuel et installez les dépendances:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. Copiez `.env.example` vers `.env`, puis renseignez l'hôte, le port, le compte,
   le mot de passe et le nom de base. Pour une base distante, configurez aussi
   `MYSQL_SSL_CA` avec le certificat CA de l'hébergeur; le certificat et le nom
   d'hôte seront vérifiés. Pour MySQL local, utilisez plutôt
   `MYSQL_SSL_DISABLED=true`. Ne publiez pas `.env` et ne partagez pas les secrets.
5. Chargez la base depuis un seul script:

   ```powershell
   python scripts\load_data.py
   ```

   Le script récupère les cinq fichiers RDA du dépôt public épinglé à un commit,
   valide les clés/formats, crée les tables puis importe les données dans une
   transaction. Il n'efface pas une base déjà remplie: si les tables ne sont pas
   vides, il s'arrête. Pour remplacer volontairement les données existantes,
   utilisez `python scripts\load_data.py --replace`. Le compte doit déjà avoir
   accès à la base `airdata`.
6. Exécutez les requêtes de [sql/02_analysis.sql](./sql/02_analysis.sql) dans
   votre client MySQL, puis vérifiez depuis Python:

   ```powershell
   python scripts\verify.py
   ```

Les requêtes d'exploration correspondant aux questions du sujet sont dans
[sql/explotartion.sql](./sql/explotartion.sql).

## Tableau de bord Flask

L'application [app.py](./app.py) lit les tables MySQL et fournit:

- des indicateurs de vols opérés, annulations, retard moyen et retards d'au
  moins 15 minutes;
- des tendances mensuelles et des comparaisons par aéroport, compagnie et
  destination, avec des résultats visuels sans dépendance de graphique externe;
- une comparaison historique des retards et annulations selon les précipitations
  observées à l'origine (association descriptive, non causale);
- un estimateur de risque historique pour un aéroport, une route, une compagnie,
  un mois et une heure donnés. Le risque correspond aux annulations ou aux
  départs retardés d'au moins 15 minutes. Il se base sur les vols antérieurs
  comparables, élargit l'échantillon si nécessaire et lisse le taux sur le taux
  historique de l'aéroport de départ.

L'estimation n'est pas un modèle prédictif validé ni une prévision temps réel:
le jeu ne contient que l'année 2013 et l'application n'intègre pas la météo
actuelle, les événements ou les ressources opérationnelles. Le volume
d'observations et la confiance sont affichés pour aider à interpréter le
résultat.

Une fois la base chargée et `.env` configuré, lancez le serveur de développement
local:

```powershell
python app.py
```

Puis ouvrez `http://127.0.0.1:5000`. Pour servir l'application avec Waitress:

```powershell
waitress-serve --listen=127.0.0.1:8000 app:app
```

### Pages et routes

- **`GET /` — Tableau de bord** ([templates/dashboard.html](./templates/dashboard.html)):
  vue d'ensemble des vols programmés/opérés et annulations, évolution mensuelle,
  trafic et retards par aéroport d'origine, indicateurs par compagnie et
  destination, comparaison selon les précipitations et formulaire d'estimation
  du risque historique.
- **Formulaire de risque (`GET /?predict=1...`)** — reste sur la page d'accueil
  et affiche le taux estimé, le nombre de vols comparables, le périmètre retenu,
  le niveau de confiance et le retard moyen historique.
- **`GET /health` — Santé de l'application**: vérifie l'accès MySQL. Répond
  `{"status":"ok"}` si la base répond, sinon HTTP 503 avec un diagnostic.
- **Page d'indisponibilité MySQL**
  ([templates/database_error.html](./templates/database_error.html)): affichée
  avec HTTP 503 sur `/` lorsque la configuration, le serveur MySQL ou le
  certificat TLS empêche l'accès aux données.
- **`/static/style.css`**: styles adaptatifs pour écran large et mobile; aucun
  compte ni service externe de graphiques n'est requis.

### Démarrer en local (Windows)

Depuis la racine du projet, après le chargement de MySQL et la configuration de
`.env`:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python app.py
```

Ouvrir `http://127.0.0.1:5000`; arrêter avec `Ctrl+C`. Pour les tests sans base:

```powershell
python -m unittest discover -s tests -v
```

Pour un serveur WSGI local:

```powershell
waitress-serve --listen=127.0.0.1:8000 app:app
```

Puis ouvrir `http://127.0.0.1:8000`. Waitress n'active pas HTTPS à lui seul:
pour l'accès public, le placer derrière un reverse proxy HTTPS ou un service
d'hébergement WSGI configuré avec TLS.

Pour une exposition publique, utilisez un hébergeur WSGI/reverse proxy avec
HTTPS, secrets d'environnement et règles réseau MySQL restrictives. Le compte
MySQL de l'application n'a besoin que de `SELECT`. Créez un utilisateur séparé
et remplissez `APP_MYSQL_USER` / `APP_MYSQL_PASSWORD` dans `.env`; le chargeur
continue d'utiliser `MYSQL_USER` / `MYSQL_PASSWORD`:

```sql
CREATE USER 'airdata_dashboard'@'%' IDENTIFIED BY 'use-another-unique-secret';
GRANT SELECT ON airdata.* TO 'airdata_dashboard'@'%';
```

Restreignez `%` à l'hôte ou au réseau d'application lorsque possible.
`MYSQL_SSL_DISABLED=true` est réservé à un MySQL local de développement,
jamais à une connexion distante.

Les tests de l'interface et de la gestion des erreurs, sans connexion MySQL:

```powershell
python -m unittest discover -s tests -v
```

## Anomalies et traitement retenu

- `flight` seul n'est pas unique; la clé composite demandée est contrôlée avant
  l'import et imposée par MySQL.
- Les quatre aéroports `BQN`, `PSE`, `SJU`, `STT`, absents de `airports` mais
  référencés par les vols, sont ajoutés avec leur nom et sans coordonnées
  fabriquées. `metadata_source='flight_reference'` les distingue des données
  source.
- Les `tailnum` présents dans `flights` mais absents de `planes` deviennent des
  fiches de référence avec les autres champs à NULL. Cela préserve les valeurs
  source et permet la FK sans inventer de caractéristiques d'avion.
- Un `tailnum` NULL dans la source reste NULL. La relation est donc une FK
  nullable, et le nombre de vols sans immatriculation est rapporté séparément.
- La clé météo supposée dans le sujet n'est pas unique dans les données brutes:
  l'heure 01:00 du 3 novembre 2013 apparaît deux fois pour chacun des trois
  aéroports météo. L'horodatage `time_hour` permet de préserver les six mesures
  et de définir une clé primaire valide.
- Un nouveau code d'aéroport absent des quatre références documentées bloque
  l'import; il faut l'auditer avant de compléter la table.

## Sécurité

Le projet utilise une connexion MySQL chiffrée avec validation du certificat CA
et du nom d'hôte. Conservez les secrets hors du dépôt (`.env` est ignoré par
Git), activez MFA et les restrictions réseau disponibles, et utilisez des
comptes dédiés avec privilèges minimaux. Le compte de chargement fourni dans
l'exemple a besoin de droits DDL; ne le réutilisez pas dans une application.
N'exposez pas MySQL directement sur Internet sans filtrage réseau et TLS.

La création des fichiers et le chargement sont reproductibles; le déploiement
effectif nécessite votre instance MySQL, sa configuration réseau et son
certificat CA TLS.
