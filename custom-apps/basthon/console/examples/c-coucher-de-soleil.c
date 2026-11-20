// Une image construite pixel par pixel, écrite au format PPM avec fprintf,
// affichée avec image_show (déclarée dans <image.h>), puis proposée au
// téléchargement avec basthon_download (déclarée dans <basthon.h>).
#include <stdio.h>
#include <math.h>
#include <image.h>
#include <basthon.h>

#define LARGEUR 400
#define HAUTEUR 300
#define HORIZON 180

FILE *f = fopen("coucher.ppm", "w");
// en-tête : format texte (P3), taille, valeur maximale d'une composante
fprintf(f, "P3\n%d %d\n255\n", LARGEUR, HAUTEUR);
for (int y = 0; y < HAUTEUR; y++) {
    for (int x = 0; x < LARGEUR; x++) {
        int r, v, b;
        // distance au soleil (son reflet dans la mer est symétrique)
        int ys = y < HORIZON ? y : 2 * HORIZON - y;
        double d = sqrt((x - 200) * (x - 200) + (ys - 150) * (ys - 150));
        if (y < HORIZON) {
            // le ciel : du violet (en haut) à l'orange (à l'horizon)
            double t = (double)y / HORIZON;
            r = 80 + 175 * t;
            v = 30 + 120 * t;
            b = 120 - 80 * t;
        } else {
            // la mer, plus sombre
            double t = (double)(y - HORIZON) / (HAUTEUR - HORIZON);
            r = 120 - 90 * t;
            v = 60 - 30 * t;
            b = 90 - 20 * t;
        }
        if (d < 45 && (y < HORIZON || (y / 4) % 2 == 0)) {
            // le soleil et son reflet (une ligne sur deux)
            r = 255;
            v = 220 - d;
            b = 80;
        }
        fprintf(f, "%d %d %d\n", r, v, b);
    }
}
fclose(f);
image_show("coucher.ppm");
// le fichier est enregistré par le navigateur, comme un téléchargement
basthon_download("coucher.ppm");
