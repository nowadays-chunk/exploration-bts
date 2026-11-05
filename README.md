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

## Mise en place MySQL

1. Créez une instance MySQL **8.0.16 ou plus récente**. Créez une base et un
   compte applicatif avec accès à cette base depuis la console de votre hébergeur:

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
3. Créez un environnement virtuel et installez les dépendances:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. Copiez `.env.example` vers `.env`, puis renseignez l'hôte, le port, le compte,
   le mot de passe, le nom de base et le chemin du CA. Le chargeur vérifie le
   certificat TLS et l'identité de l'hôte. Ne publiez pas `.env` et ne partagez
   pas les secrets.
5. Chargez la base:

   ```powershell
   python scripts\load_data.py
   ```

   Le script récupère les cinq fichiers RDA du dépôt public épinglé à un commit,
   valide les clés/formats, crée les tables puis importe les données dans une
   transaction. Chaque exécution remplace intégralement le contenu actuel des
   cinq tables. Le compte doit déjà avoir accès à la base `airdata`.
6. Exécutez les requêtes de [sql/02_analysis.sql](./sql/02_analysis.sql) dans
   votre client MySQL, puis vérifiez depuis Python:

   ```powershell
   python scripts\verify.py
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
