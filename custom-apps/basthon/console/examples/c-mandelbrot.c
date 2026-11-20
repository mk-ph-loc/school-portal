// L'ensemble de Mandelbrot, pixel par pixel, avec <canvas.h>.
// Le dessin s'affiche à la fin du programme, et le nombre de pixels
// dans l'ensemble donne une estimation de son aire (environ 1,506).
#include <stdio.h>
#include <canvas.h>

#define LARGEUR 600
#define HAUTEUR 400
#define MAX 200

// Nombre d'itérations de z -> z² + c avant que |z| dépasse 2 (MAX si jamais).
int iterations(double cx, double cy) {
    double x = 0, y = 0;
    int n = 0;
    while (n < MAX && x * x + y * y <= 4) {
        double xt = x * x - y * y + cx;
        y = 2 * x * y + cy;
        x = xt;
        n++;
    }
    return n;
}

int dedans = 0;  // nombre de pixels dans l'ensemble
canvas_create(LARGEUR, HAUTEUR);
for (int py = 0; py < HAUTEUR; py++)
    for (int px = 0; px < LARGEUR; px++) {
        // le pixel (px, py) correspond au point c = cx + i cy
        double cx = -2.2 + 3.0 * px / LARGEUR;
        double cy = 1.0 - 2.0 * py / HAUTEUR;
        int n = iterations(cx, cy);
        if (n == MAX) {
            canvas_set_pixel(px, py, 0, 0, 0);
            dedans++;
        } else {
            // une palette (bleu, blanc, orange) parcourue toutes les 50 itérations
            double t = (n % 50) / 50.0;
            canvas_set_pixel(px, py, 255 * 36 * (1 - t) * t * t * t,
                             255 * 15 * (1 - t) * (1 - t) * t * t,
                             255 * 17 * (1 - t) * (1 - t) * (1 - t) * t);
        }
    }
// chaque pixel est un rectangle de (3 / LARGEUR) x (2 / HAUTEUR)
double aire = dedans * (3.0 / LARGEUR) * (2.0 / HAUTEUR);
printf("%d pixels sur %d dans l'ensemble : aire d'environ %.3f\n", dedans,
       LARGEUR * HAUTEUR, aire);
