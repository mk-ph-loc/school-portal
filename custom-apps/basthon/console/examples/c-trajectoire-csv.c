// Une trajectoire calculée pas à pas, écrite dans un fichier CSV avec
// fprintf, puis proposée au téléchargement avec basthon_download
// (déclarée dans <basthon.h>) : le fichier s'ouvre dans un tableur.
#include <stdio.h>
#include <math.h>
#include <basthon.h>

#define V0 25.0        // vitesse initiale, en m/s
#define ANGLE 45.0     // angle de tir, en degrés
#define G 9.81         // pesanteur, en m/s²
#define DT 0.05        // pas de temps, en s

double vx = V0 * cos(ANGLE * M_PI / 180);
double vy = V0 * sin(ANGLE * M_PI / 180);

FILE *f = fopen("trajectoire.csv", "w");
// le point-virgule est le séparateur attendu par les tableurs français
fprintf(f, "t (s);x (m);y (m)\n");

int points = 0;
double t = 0, x = 0, y = 0, portee = 0, hauteur = 0;
while (y >= 0) {
    fprintf(f, "%.2f;%.3f;%.3f\n", t, x, y);
    points++;
    if (y > hauteur) hauteur = y;
    portee = x;
    // méthode d'Euler : on avance d'un pas de temps
    t += DT;
    x += vx * DT;
    y += vy * DT;
    vy -= G * DT;
}
fclose(f);

printf("%d points écrits dans trajectoire.csv\n", points);
printf("Flèche   : %.1f m\n", hauteur);
printf("Portée   : %.1f m\n", portee);
printf("Durée    : %.2f s\n", t);

// le fichier est enregistré par le navigateur, comme un téléchargement
basthon_download("trajectoire.csv");
