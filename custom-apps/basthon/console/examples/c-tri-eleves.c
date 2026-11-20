// Tri d'un tableau de structures avec qsort.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct eleve {
    char nom[20];
    double moyenne;
} Eleve;

Eleve classe[] = {
    {"Ada", 17.5},
    {"Alan", 15.25},
    {"Grace", 18},
    {"Linus", 12.75},
    {"Margaret", 16},
};
int taille = sizeof(classe) / sizeof(classe[0]);

int par_moyenne(const void *a, const void *b) {
    const Eleve *e1 = a, *e2 = b;
    return (e1->moyenne < e2->moyenne) - (e1->moyenne > e2->moyenne);
}

qsort(classe, taille, sizeof(Eleve), par_moyenne);

for (int i = 0; i < taille; i++)
    printf("%d. %-10s %5.2f\n", i + 1, classe[i].nom, classe[i].moyenne);

// Dans la console, essayer par exemple : classe[0]
classe[0]
