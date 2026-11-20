-- Le système solaire : les planètes et quelques-uns de leurs satellites.
-- Le script crée la base et affiche le résultat de sa dernière requête ;
-- d'autres requêtes s'écrivent ensuite dans la console (idées à la fin).

CREATE TABLE planetes (
    nom TEXT PRIMARY KEY,
    type TEXT,             -- tellurique ou géante
    distance_ua REAL,      -- distance moyenne au Soleil (1 UA = 150 millions de km)
    diametre_km INTEGER,
    revolution_jours REAL  -- durée d'un tour autour du Soleil
);

CREATE TABLE satellites (
    nom TEXT PRIMARY KEY,
    planete TEXT REFERENCES planetes(nom),
    diametre_km INTEGER
);

INSERT INTO planetes VALUES
    ('Mercure', 'tellurique', 0.39, 4879, 88),
    ('Vénus', 'tellurique', 0.72, 12104, 225),
    ('Terre', 'tellurique', 1.00, 12742, 365.25),
    ('Mars', 'tellurique', 1.52, 6779, 687),
    ('Jupiter', 'géante', 5.20, 139820, 4333),
    ('Saturne', 'géante', 9.58, 116460, 10759),
    ('Uranus', 'géante', 19.2, 50724, 30687),
    ('Neptune', 'géante', 30.05, 49244, 60190);

INSERT INTO satellites VALUES
    ('Lune', 'Terre', 3474),
    ('Phobos', 'Mars', 22),
    ('Déimos', 'Mars', 12),
    ('Io', 'Jupiter', 3643),
    ('Europe', 'Jupiter', 3122),
    ('Ganymède', 'Jupiter', 5268),
    ('Callisto', 'Jupiter', 4821),
    ('Titan', 'Saturne', 5150),
    ('Encelade', 'Saturne', 504),
    ('Titania', 'Uranus', 1578),
    ('Triton', 'Neptune', 2707);

-- La durée de l'année (en années terrestres) et le diamètre (comparé à
-- celui de la Terre) de chaque planète, et sa taille en barres : un carré
-- pour 8 000 km de diamètre.
SELECT nom,
       ROUND(revolution_jours / 365.25, 1) AS annee,
       ROUND(diametre_km * 1.0 / (SELECT diametre_km FROM planetes WHERE nom = 'Terre'), 2) AS diametre,
       substr('■■■■■■■■■■■■■■■■■■■■', 1, diametre_km / 8000 + 1) AS taille
FROM planetes
ORDER BY distance_ua;

-- Des requêtes à essayer dans la console :
--
-- Les planètes géantes :
--   SELECT nom, diametre_km FROM planetes WHERE type = 'géante';
--
-- Le nombre de satellites (de la table) de chaque planète, avec une jointure :
--   SELECT p.nom, COUNT(s.nom) AS satellites
--   FROM planetes AS p LEFT JOIN satellites AS s ON s.planete = p.nom
--   GROUP BY p.nom ORDER BY satellites DESC;
--
-- Les satellites plus grands que Mercure :
--   SELECT nom, planete, diametre_km FROM satellites
--   WHERE diametre_km > (SELECT diametre_km FROM planetes WHERE nom = 'Mercure');
--
-- La troisième loi de Kepler : période² / distance³ est (presque) la même
-- pour toutes les planètes !
--   SELECT nom, ROUND(revolution_jours * revolution_jours
--                     / (distance_ua * distance_ua * distance_ua)) AS kepler
--   FROM planetes;
